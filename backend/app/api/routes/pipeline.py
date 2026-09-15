"""
app/api/routes/pipeline.py

Exposes the JD + CV Intelligence & Eligibility Engine pipeline (Days 1-5)
as a standalone FastAPI service: JD parsing, CV parsing, experience
matching, and the combined eligibility decision.

All four handlers are plain `def`, not `async def` — parse_job_description
and parse_cv call Gemini's generate_content synchronously under the hood
(confirmed in gemini_provider.py), so FastAPI must run them in its thread
pool rather than on the event loop. Declaring these `async def` while
calling a blocking Gemini request inside would stall every concurrent
request behind it.

/check-eligibility takes only job_profile, candidate, application, and
constraints from the client — classified_reqs is deliberately not a
request field, since it's a pure server-side normalization of job_profile
(classify_requirements) that no client could independently supply.

None of the four endpoints expose a `today` override: it exists on the
underlying functions purely for test determinism, and a public API has no
legitimate reason to let a client pretend it's a different date.

POST /submit-application is the persistence counterpart: it runs the same
JD/CV/eligibility sequence and then writes Candidate, JobPosting, and
Application rows. It is the only handler in this file that touches the
database. It does not create an InterviewResult — that belongs to a later
voice-pipeline integration, after an interview actually runs.
"""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.applicant import ApplicantIdentity
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile
from app.services.cv_intelligence.cv_parser import parse_cv
from app.services.eligibility.eligibility_engine import (
    ApplicationDetails,
    EligibilityResult,
    RecruiterConstraints,
    check_eligibility,
)
from app.services.eligibility.experience_matcher import (
    ExperienceMatchResult,
    match_all_experience_requirements,
)
from app.services.jd_intelligence.jd_parser import parse_job_description
from app.services.jd_intelligence.requirement_classifier import classify_requirements
from app.services.persistence.application_repository import (
    create_application,
    create_job_posting,
    get_or_create_candidate,
)

router = APIRouter()


class AnalyzeJDRequest(BaseModel):
    jd_text: str


class AnalyzeCVRequest(BaseModel):
    cv_text: str


@router.post("/analyze-jd", response_model=JobRequirementProfile)
def analyze_jd(request: AnalyzeJDRequest) -> JobRequirementProfile:
    return parse_job_description(request.jd_text)


@router.post("/analyze-cv", response_model=CandidateProfile)
def analyze_cv(request: AnalyzeCVRequest) -> CandidateProfile:
    return parse_cv(request.cv_text)


@router.post("/match-experience", response_model=List[ExperienceMatchResult])
def match_experience_endpoint(
    job_profile: JobRequirementProfile,
    candidate: CandidateProfile,
) -> List[ExperienceMatchResult]:
    return match_all_experience_requirements(job_profile, candidate)


@router.post("/check-eligibility", response_model=EligibilityResult)
def check_eligibility_endpoint(
    job_profile: JobRequirementProfile,
    candidate: CandidateProfile,
    application: ApplicationDetails,
    constraints: RecruiterConstraints,
) -> EligibilityResult:
    classified_reqs = classify_requirements(job_profile)
    return check_eligibility(job_profile, classified_reqs, candidate, application, constraints)


class SubmitApplicationRequest(BaseModel):
    jd_text: str
    job_title: str
    cv_text: str
    applicant_identity: ApplicantIdentity
    application_details: ApplicationDetails
    recruiter_constraints: RecruiterConstraints


class SubmitApplicationResponse(BaseModel):
    candidate_id: int
    job_posting_id: int
    application_id: int
    overall_eligible: bool
    eligibility_result: EligibilityResult


@router.post("/submit-application", response_model=SubmitApplicationResponse)
def submit_application(
    request: SubmitApplicationRequest,
    db: Session = Depends(get_db),
) -> SubmitApplicationResponse:
    try:
        job_profile = parse_job_description(request.jd_text)
        job_posting = create_job_posting(
            db,
            job_title=request.job_title,
            raw_jd_text=request.jd_text,
            parsed_profile=job_profile,
        )
        candidate_profile = parse_cv(request.cv_text)
        candidate = get_or_create_candidate(db, request.applicant_identity)
        classified_reqs = classify_requirements(job_profile)
        eligibility_result = check_eligibility(
            job_profile,
            classified_reqs,
            candidate_profile,
            request.application_details,
            request.recruiter_constraints,
        )
        application = create_application(
            db,
            candidate=candidate,
            job_posting=job_posting,
            candidate_profile=candidate_profile,
            application_details=request.application_details,
            constraints=request.recruiter_constraints,
            eligibility_result=eligibility_result,
        )
        candidate_id = candidate.id
        job_posting_id = job_posting.id
        application_id = application.id
        db.commit()
    except Exception:
        db.rollback()
        raise

    return SubmitApplicationResponse(
        candidate_id=candidate_id,
        job_posting_id=job_posting_id,
        application_id=application_id,
        overall_eligible=eligibility_result.overall_eligible,
        eligibility_result=eligibility_result,
    )
