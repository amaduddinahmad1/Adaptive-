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
"""
from dataclasses import asdict
from typing import List

from app.models.application import Application
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


def get_or_create_candidate(db: Session, identity: ApplicantIdentity) -> Candidate:
    existing = db.query(Candidate).filter(Candidate.email == identity.email).first()
    if existing is not None:
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
) -> JobPosting:
    job_posting = JobPosting(
        job_title=job_title,
        raw_jd_text=raw_jd_text,
        parsed_profile=parsed_profile.model_dump(mode="json"),
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
