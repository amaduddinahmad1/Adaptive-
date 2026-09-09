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
"""

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

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
