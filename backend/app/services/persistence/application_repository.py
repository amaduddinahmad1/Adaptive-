"""
app/services/persistence/application_repository.py

Writes the results of a JD/CV/eligibility pipeline run to Postgres. This is
the first code in the codebase that actually inserts into candidates,
job_postings, or applications -- the tables have existed since the initial
Alembic migration, but nothing previously wrote to them.

get_or_create_candidate() looks up by email (unique) rather than always
inserting, so re-running the pipeline for the same person doesn't create a
duplicate Candidate row.

create_job_posting() always inserts a new row -- no dedup against an
existing posting with the same raw_jd_text. Deliberate scope decision, not
an oversight: what should count as "the same" posting (exact text match?
fuzzy?) is a real design question, left open until repeat runs against the
same JD make it worth solving.

create_interview_result() persists the interview stage's output, linked to
an already-eligible Application. final_report/interview_plan convert
cleanly via dataclasses.asdict() into a dict (they're single dataclass
instances). qa_transcript and gap_analysis are naturally lists (a list of
per-question turns; a list of GapAnalysisEntry) but the interview_results
table declares both columns as JSONB typed Optional[dict] (see
app/models/interview_result.py, re-confirmed by reading it directly before
writing this) -- so both are wrapped in a single-key dict ({"turns": [...]},
{"entries": [...]}) to match the declared column type, not passed as a bare
list.

All functions take a Session and do not commit -- the caller commits once
after every step succeeds, so a failure partway through a pipeline run
never leaves an orphaned Candidate/JobPosting/Application with no row
pointing to it.

generate_interview_token() (Phase 1 of the interview-invitation email
feature) follows the same discipline. It's deliberately a plain, reusable
function rather than logic embedded in any one script: today its only
caller is scripts/run_pipeline_smoketest.py, but the real production
trigger will eventually be a live application-submission API endpoint
(not yet built) calling this exact same function once overall_eligible is
known to be True.
"""
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.core.interview_config import (
    DEFAULT_INTERVIEW_QUESTION_COUNT,
    normalize_interview_question_count,
)
from app.models.application import (
    HIRING_DECISION_PENDING,
    HIRING_DECISION_REJECTED,
    Application,
)
from app.models.candidate import Candidate
from app.models.interview_result import InterviewResult
from app.models.job_posting import JobPosting
from app.schemas.applicant import ApplicantIdentity
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile
from app.services.eligibility.eligibility_engine import (
    ApplicationDetails,
    EligibilityResult,
    RecruiterConstraints,
)
from app.services.interview_intelligence.models import FinalAssessmentReport, GapAnalysisEntry, InterviewPlan
from sqlalchemy.orm import Session

INTERVIEW_TOKEN_TTL_HOURS = 48


def get_or_create_candidate(db: Session, identity: ApplicantIdentity) -> Candidate:
    existing = db.query(Candidate).filter(Candidate.email == identity.email).first()
    if existing is not None:
        existing.full_name = identity.full_name
        if identity.phone is not None:
            existing.phone = identity.phone
        return existing

    candidate = Candidate(
        full_name=identity.full_name,
        email=identity.email,
        phone=identity.phone,
    )
    db.add(candidate)
    db.flush()  # populate candidate.id without committing yet
    return candidate


def create_job_posting(
    db: Session,
    job_title: str,
    raw_jd_text: str,
    parsed_profile: JobRequirementProfile,
    interview_question_count: int = DEFAULT_INTERVIEW_QUESTION_COUNT,
    created_by_user_id: Optional[int] = None,
) -> JobPosting:
    job_posting = JobPosting(
        job_title=job_title,
        raw_jd_text=raw_jd_text,
        parsed_profile=parsed_profile.model_dump(mode="json"),
        interview_question_count=normalize_interview_question_count(
            interview_question_count
        ),
        created_by_user_id=created_by_user_id,
    )
    db.add(job_posting)
    db.flush()
    return job_posting


def create_application(
    db: Session,
    candidate: Candidate,
    job_posting: JobPosting,
    candidate_profile: CandidateProfile,
    application_details: ApplicationDetails,
    constraints: RecruiterConstraints,
    eligibility_result: EligibilityResult,
) -> Application:
    application = Application(
        candidate_id=candidate.id,
        job_posting_id=job_posting.id,
        candidate_profile=candidate_profile.model_dump(mode="json"),
        job_profile_snapshot=job_posting.parsed_profile,
        joining_availability=application_details.joining_availability,
        salary_expectation=application_details.salary_expectation,
        recruiter_max_notice_period_days=constraints.max_notice_period_days,
        recruiter_salary_min=constraints.salary_min,
        recruiter_salary_max=constraints.salary_max,
        eligibility_result=eligibility_result.model_dump(mode="json"),
        overall_eligible=eligibility_result.overall_eligible,
        hiring_decision=HIRING_DECISION_PENDING,
    )
    db.add(application)
    db.flush()
    return application


def create_interview_result(
    db: Session,
    application: Application,
    final_report: FinalAssessmentReport,
    interview_plan: InterviewPlan,
    qa_transcript: List[dict],
    gap_analysis: List[GapAnalysisEntry],
) -> InterviewResult:
    interview_result = InterviewResult(
        application_id=application.id,
        final_report=asdict(final_report),
        recommendation=final_report.recommendation,
        interview_eligibility_result=final_report.eligibility_result,
        problem_solving_performance=final_report.problem_solving_performance,
        communication_performance=final_report.communication_performance,
        interview_plan=asdict(interview_plan),
        qa_transcript={"turns": qa_transcript},
        gap_analysis={"entries": [asdict(entry) for entry in gap_analysis]},
    )
    db.add(interview_result)
    db.flush()
    return interview_result


def generate_interview_token(db: Session, application: Application) -> Application:
    """
    Generates and sets a fresh interview_token/token_expires_at pair on an
    already-eligible Application, so the candidate can be emailed a
    single-use interview link (app/services/notifications/email_service.py,
    a later step in this same feature, is the actual sender).

    Refuses to run in two cases, both real footguns rather than hypothetical
    edge cases:

    - application.overall_eligible is False: mirrors the same re-verification
      discipline as scripts/run_interview_for_application.py's eligibility
      check, kept even though callers are expected to only invoke this on an
      eligible application, as a safety net against a race condition or a
      caller bug rather than trusting the caller alone.
    - application already has an active (unexpired, unused) token: silently
      overwriting it would invalidate a link that may already be sitting in
      the candidate's inbox. Regenerating an expired or already-used token is
      fine and expected (e.g. a candidate requesting a fresh link).

    Same discipline as every other function in this module: flushes only, so
    the token is visible on `application` immediately without ending the
    caller's transaction -- the caller commits once, after every step in its
    pipeline succeeds.
    """
    if not application.overall_eligible:
        raise ValueError(
            f"Application {application.id} is not eligible (overall_eligible=False) -- "
            "refusing to generate an interview token."
        )

    if application.interview_token is not None and not application.token_used:
        if application.token_expires_at and not interview_invitation_is_expired(application):
            raise ValueError(
                f"Application {application.id} already has an active, unexpired interview "
                "token -- refusing to overwrite it. Regenerating an expired/used token is fine."
            )

    application.interview_token = secrets.token_urlsafe(32)
    application.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=INTERVIEW_TOKEN_TTL_HOURS)
    application.token_used = False
    db.flush()
    return application


def get_application_by_interview_token(db: Session, token: str) -> Optional[Application]:
    """Look up an Application by its invitation token. Returns None if missing."""
    if not token:
        return None
    return (
        db.query(Application)
        .filter(Application.interview_token == token)
        .first()
    )


def interview_invitation_is_expired(application: Application) -> bool:
    """True when a token expiry is present and has already passed."""
    expires_at = application.token_expires_at
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def mark_interview_token_used(db: Session, application: Application) -> Application:
    """Marks the invitation as consumed when the interview actually starts."""
    application.token_used = True
    db.flush()
    return application


def mark_invitation_sent(db: Session, application: Application) -> Application:
    """
    Records that the interview invitation email was actually sent.
    Deliberately separate from generate_interview_token() and called only
    after app.services.notifications.email_service.send_interview_invitation()
    returns without raising -- email_sent_at must never be set optimistically,
    since it's the field a future retry mechanism would use to find
    "eligible but not yet notified" applications (the same role
    overall_eligible plays for run_interview_for_application.py's own
    "eligible but not yet interviewed" query). Flushes only, caller commits.
    """
    application.email_sent_at = datetime.now(timezone.utc)
    db.flush()
    return application


def set_application_hiring_decision(
    db: Session,
    application: Application,
    decision: str,
) -> Application:
    """Persist a recruiter hiring decision without deleting any records.

    Currently only rejection is supported. Repeating reject is idempotent.
    """
    normalized = (decision or "").strip().lower()
    if normalized != HIRING_DECISION_REJECTED:
        raise ValueError("Unsupported hiring decision")
    if application.hiring_decision == HIRING_DECISION_REJECTED:
        return application
    application.hiring_decision = HIRING_DECISION_REJECTED
    db.flush()
    return application
