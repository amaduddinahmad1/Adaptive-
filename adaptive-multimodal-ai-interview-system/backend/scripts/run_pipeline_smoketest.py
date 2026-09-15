"""
run_pipeline_smoketest.py

Full JD->CV->eligibility pipeline run against a real CV file, ending with a
real write to Postgres (candidates, job_postings, applications) -- the
first time anything in this codebase has actually persisted a pipeline
result. Deliberately stops after eligibility: the interview step is a
separate follow-up run, proposed and approved only after seeing whether
this candidate comes back eligible for this JD.

Chain: parse_job_description() -> parse_cv() -> classify_requirements()
-> check_eligibility() -> get_or_create_candidate()/create_job_posting()/
create_application() [app/services/persistence/application_repository.py],
committed once at the end so a failure partway through never leaves an
orphaned Candidate or JobPosting row.
"""

import argparse
import io
import sys
from pathlib import Path

# Windows' console defaults to a legacy codepage (not UTF-8), which mangles
# characters like the em dash used in eligibility report lines (rendered as
# "?" instead of "--"). Wrapping stdout/stderr in an explicit UTF-8
# TextIOWrapper fixes this for terminal output; it has no effect on what
# gets written to the database, which was always correct UTF-8 regardless.
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import get_db, get_engine
from app.integrations.llm.factory import get_default_provider
from app.schemas.applicant import ApplicantIdentity
from app.services.cv_intelligence.cv_parser import parse_cv
from app.services.cv_intelligence.extraction import CVExtractionError
from app.services.cv_intelligence.extraction.docx_extractor import extract_text_from_docx
from app.services.cv_intelligence.extraction.pdf_extractor import extract_text_from_pdf
from app.services.eligibility.eligibility_engine import (
    ApplicationDetails,
    RecruiterConstraints,
    check_eligibility,
    format_eligibility_report,
)
from app.services.jd_intelligence.jd_parser import parse_job_description
from app.services.jd_intelligence.requirement_classifier import classify_requirements
from app.services.persistence.application_repository import (
    create_application,
    create_job_posting,
    get_or_create_candidate,
)

DEFAULT_JD_FIXTURE_PATH = BACKEND_ROOT / "tests" / "sample_data" / "sample_jd_ai_engineer_intern_v3.txt"
DEFAULT_CV_PATH = BACKEND_ROOT / "scripts" / "Amad Ud Din CV Lahore.pdf"

# Approved recruiter-side constraints for this JD: $70,000 is a ceiling, not
# a floor ("up to X" reading of a posted intern salary), so salary_min is
# None and only salary_max is set.
RECRUITER_CONSTRAINTS = RecruiterConstraints(
    max_notice_period_days=30,
    salary_min=None,
    salary_max=70000.0,
)


def _extract_cv_text(cv_path: Path) -> str:
    if cv_path.suffix.lower() == ".pdf":
        return extract_text_from_pdf(str(cv_path))
    if cv_path.suffix.lower() == ".docx":
        return extract_text_from_docx(str(cv_path))
    raise CVExtractionError(f"Unsupported CV file type: {cv_path.suffix}")


def _prompt_float(prompt: str) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("Please enter a number (e.g. 70000).")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the JD->CV->eligibility pipeline smoke test.")
    parser.add_argument(
        "--cv-path",
        type=Path,
        default=DEFAULT_CV_PATH,
        help=(
            "Path to the CV file (PDF or DOCX). A relative path resolves against "
            f"scripts/. Defaults to {DEFAULT_CV_PATH.name}."
        ),
    )
    parser.add_argument(
        "--jd-path",
        type=Path,
        default=DEFAULT_JD_FIXTURE_PATH,
        help=(
            "Path to the JD fixture text file. A relative path resolves against "
            f"tests/sample_data/. Defaults to {DEFAULT_JD_FIXTURE_PATH.name}."
        ),
    )
    return parser.parse_args()


def _check_database_target() -> None:
    """
    Fails loudly, before anything else runs, if DATABASE_URL resolves to no
    database name (e.g. a trailing '/' with nothing after it) -- psycopg
    silently connects to a database named after the user in that case
    (e.g. 'postgres'), which looks like a working connection right up until
    every table lookup fails. Never prints the password: engine.url.database/
    host/port carry no credentials.
    """
    engine = get_engine()
    db_name = engine.url.database
    print(f"Connecting to database: {db_name!r} on {engine.url.host}:{engine.url.port}")
    assert db_name, (
        "DATABASE_URL has no database name configured (empty after the final '/') -- "
        "fix .env before proceeding."
    )


def main() -> None:
    args = _parse_args()
    cv_path = args.cv_path if args.cv_path.is_absolute() else BACKEND_ROOT / "scripts" / args.cv_path
    jd_path = args.jd_path if args.jd_path.is_absolute() else BACKEND_ROOT / "tests" / "sample_data" / args.jd_path

    _check_database_target()

    print(f"JD fixture: {jd_path}")
    jd_text = jd_path.read_text(encoding="utf-8")
    jd_profile = parse_job_description(jd_text)
    print("Parsed JobRequirementProfile OK.")

    print(f"CV file: {cv_path}")
    cv_text = _extract_cv_text(cv_path)
    candidate_profile = parse_cv(cv_text)
    print("Parsed CandidateProfile OK.")

    classified = classify_requirements(jd_profile)

    print("\nApplicant identity (not parsed from the CV -- supplied directly):")
    full_name = input("Full name: ").strip()
    email = input("Email: ").strip()
    phone = input("Phone (optional, press Enter to skip): ").strip() or None
    identity = ApplicantIdentity(full_name=full_name, email=email, phone=phone)

    print("\nApplication details:")
    joining_availability = input("Joining availability (e.g. 'immediate', '2 weeks'): ").strip()
    salary_expectation = _prompt_float("Salary expectation (annual, numeric only): ")
    application_details = ApplicationDetails(
        joining_availability=joining_availability,
        salary_expectation=salary_expectation,
    )

    print(
        f"\nRecruiter constraints for this JD: max notice {RECRUITER_CONSTRAINTS.max_notice_period_days} days, "
        f"salary ceiling ${RECRUITER_CONSTRAINTS.salary_max:,.0f} (no floor)."
    )

    eligibility_result = check_eligibility(
        jd_profile=jd_profile,
        classified_reqs=classified,
        candidate=candidate_profile,
        application=application_details,
        constraints=RECRUITER_CONSTRAINTS,
        provider=get_default_provider(),  # opts in to the semantic skill-inference layer
    )

    print("\n" + "=" * 90)
    print("ELIGIBILITY REPORT")
    print("=" * 90)
    print(format_eligibility_report(eligibility_result))
    print(f"\noverall_eligible = {eligibility_result.overall_eligible}")

    print("\n" + "=" * 90)
    print("PERSISTING TO DATABASE")
    print("=" * 90)
    db = next(get_db())
    try:
        candidate = get_or_create_candidate(db, identity)
        job_posting = create_job_posting(db, jd_profile.job_title, jd_text, jd_profile)
        application = create_application(
            db,
            candidate,
            job_posting,
            candidate_profile,
            application_details,
            RECRUITER_CONSTRAINTS,
            eligibility_result,
        )
        db.commit()
        print(f"Committed: candidate_id={candidate.id}, job_posting_id={job_posting.id}, application_id={application.id}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\n" + "=" * 90)
    print("RE-QUERYING FROM THE DATABASE TO CONFIRM THE WRITE LANDED")
    print("=" * 90)
    verify_db = next(get_db())
    try:
        from app.models.application import Application
        from app.models.candidate import Candidate
        from app.models.job_posting import JobPosting

        row_candidate = verify_db.get(Candidate, candidate.id)
        row_job_posting = verify_db.get(JobPosting, job_posting.id)
        row_application = verify_db.get(Application, application.id)

        print(f"candidates:     id={row_candidate.id}, email={row_candidate.email}")
        print(f"job_postings:   id={row_job_posting.id}, job_title={row_job_posting.job_title}")
        print(f"applications:   id={row_application.id}, overall_eligible={row_application.overall_eligible}")
    finally:
        verify_db.close()


if __name__ == "__main__":
    main()
