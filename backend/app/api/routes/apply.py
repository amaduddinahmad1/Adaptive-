"""
Candidate application endpoints (Phase 4B).

This is the production trigger described by application_repository: apply to an
already-persisted JobPosting, reuse CV parsing / eligibility / persistence, and
if overall_eligible is True call the existing generate_interview_token +
send_interview_invitation + mark_invitation_sent path.

It does not create a second invitation system and does not re-parse JDs.
Eligibility uses classify_requirements plus check_eligibility with
get_default_provider() so unmatched mandatory skills/technologies can be
judged by the existing semantic matcher.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.integrations.llm.factory import get_default_provider
from app.models.application import application_is_rejected
from app.models.candidate import Candidate
from app.models.interview_result import InterviewResult
from app.models.job_posting import JobPosting
from app.schemas.applicant import ApplicantIdentity
from app.schemas.job import JobRequirementProfile
from app.services.cv_intelligence.cv_parser import parse_cv
from app.services.cv_intelligence.extraction import CVExtractionError
from app.services.cv_intelligence.extraction.extract import (
    SUPPORTED_CV_SUFFIXES,
    extract_cv_text,
)
from app.services.eligibility.eligibility_engine import (
    ApplicationDetails,
    RecruiterConstraints,
    check_eligibility,
)
from app.services.jd_intelligence.requirement_classifier import classify_requirements
from app.services.notifications.email_service import EmailServiceError, send_interview_invitation
from app.services.persistence.application_repository import (
    create_application,
    generate_interview_token,
    get_application_by_interview_token,
    get_or_create_candidate,
    interview_invitation_is_expired,
    mark_invitation_sent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["candidate-apply"])

MAX_CV_BYTES = 10 * 1024 * 1024
_CANDIDATE_INPUT_ERROR = "Please check your name, email, salary, and availability."
_CV_UNREADABLE = (
    "We could not read text from the uploaded CV. Please upload a text-based PDF or DOCX file."
)
_CV_UNSUPPORTED = "Please upload a PDF or DOCX resume (maximum 10 MB)."
_CV_TOO_LARGE = "The resume must be 10 MB or smaller."
_JOB_NOT_READY = "This job posting is not available for applications yet."


class PublicJobSummary(BaseModel):
    id: int
    job_title: str


class ApplyResponse(BaseModel):
    application_id: int
    candidate_id: int
    job_posting_id: int
    job_title: str
    overall_eligible: bool
    invitation_sent: bool


class ResolveInterviewInvitationRequest(BaseModel):
    token: str = Field(min_length=1)


class ResolveInterviewInvitationResponse(BaseModel):
    application_id: int
    candidate_id: int
    job_posting_id: int
    job_title: str
    candidate_full_name: str


def _empty_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _read_cv_upload(cv: UploadFile) -> tuple[str, bytes]:
    filename = cv.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_CV_SUFFIXES:
        raise HTTPException(status_code=400, detail=_CV_UNSUPPORTED)
    data = cv.file.read()
    if not data:
        raise HTTPException(status_code=400, detail=_CV_UNREADABLE)
    if len(data) > MAX_CV_BYTES:
        raise HTTPException(status_code=400, detail=_CV_TOO_LARGE)
    return suffix, data


def _extract_uploaded_cv_text(suffix: str, data: bytes) -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(data)
        tmp.close()
        return extract_cv_text(str(tmp_path))
    except CVExtractionError:
        raise HTTPException(status_code=400, detail=_CV_UNREADABLE) from None
    finally:
        tmp_path.unlink(missing_ok=True)


def _load_job_profile(job: JobPosting) -> JobRequirementProfile:
    if not job.parsed_profile:
        raise HTTPException(status_code=400, detail=_JOB_NOT_READY)
    try:
        return JobRequirementProfile.model_validate(job.parsed_profile)
    except ValidationError:
        logger.error("Job posting %s has an invalid parsed_profile", job.id)
        raise HTTPException(status_code=400, detail=_JOB_NOT_READY) from None


def _maybe_send_invitation(
    *,
    application,
    candidate,
    job_title: str,
    db: Session,
) -> bool:
    try:
        send_interview_invitation(
            candidate_email=candidate.email,
            candidate_name=candidate.full_name,
            job_title=job_title,
            interview_token=application.interview_token,
        )
        mark_invitation_sent(db, application)
        db.commit()
        return True
    except EmailServiceError:
        logger.error(
            "Interview invitation email failed for application %s",
            application.id,
            exc_info=True,
        )
        return False


_INVALID_INVITATION = "This interview invitation is invalid."
_EXPIRED_INVITATION = "This interview invitation has expired."
_INELIGIBLE_INVITATION = "This application is not eligible for interview."
_COMPLETED_INVITATION = "This interview has already been completed."
_REJECTED_INVITATION = "This application has been rejected and cannot start a new interview."


@router.post(
    "/interview-invitations/resolve",
    response_model=ResolveInterviewInvitationResponse,
)
def resolve_interview_invitation(
    payload: ResolveInterviewInvitationRequest,
    db: Session = Depends(get_db),
) -> ResolveInterviewInvitationResponse:
    """Map an existing invitation token to its Application without returning the token."""
    token = payload.token.strip()
    application = get_application_by_interview_token(db, token)
    if application is None:
        raise HTTPException(status_code=404, detail=_INVALID_INVITATION)
    if not application.overall_eligible:
        raise HTTPException(status_code=403, detail=_INELIGIBLE_INVITATION)
    if application_is_rejected(application):
        raise HTTPException(status_code=403, detail=_REJECTED_INVITATION)
    if application.token_expires_at is None or interview_invitation_is_expired(application):
        raise HTTPException(status_code=410, detail=_EXPIRED_INVITATION)

    existing_result = (
        db.query(InterviewResult)
        .filter(InterviewResult.application_id == application.id)
        .first()
    )
    if existing_result is not None:
        raise HTTPException(status_code=409, detail=_COMPLETED_INVITATION)

    candidate = db.query(Candidate).filter(Candidate.id == application.candidate_id).first()
    job = db.query(JobPosting).filter(JobPosting.id == application.job_posting_id).first()
    if candidate is None or job is None:
        raise HTTPException(status_code=404, detail=_INVALID_INVITATION)

    return ResolveInterviewInvitationResponse(
        application_id=application.id,
        candidate_id=application.candidate_id,
        job_posting_id=application.job_posting_id,
        job_title=job.job_title,
        candidate_full_name=candidate.full_name,
    )


@router.get("/jobs", response_model=List[PublicJobSummary])
def list_open_jobs(db: Session = Depends(get_db)) -> List[PublicJobSummary]:
    rows = (
        db.query(JobPosting)
        .filter(JobPosting.parsed_profile.isnot(None))
        .order_by(JobPosting.created_at.desc())
        .all()
    )
    return [PublicJobSummary(id=job.id, job_title=job.job_title) for job in rows]


@router.post("/jobs/{job_id}/apply", response_model=ApplyResponse)
def apply_to_job(
    job_id: int,
    full_name: str = Form(...),
    email: str = Form(...),
    joining_availability: str = Form(...),
    salary_expectation: float = Form(...),
    cv: UploadFile = File(...),
    phone: Optional[str] = Form(None),
    db: Session = Depends(get_db),
) -> ApplyResponse:
    job = db.query(JobPosting).filter(JobPosting.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job posting not found")

    try:
        identity = ApplicantIdentity(
            full_name=full_name.strip(),
            email=email.strip(),
            phone=_empty_to_none(phone),
        )
        application_details = ApplicationDetails(
            joining_availability=joining_availability.strip(),
            salary_expectation=salary_expectation,
        )
    except ValidationError:
        raise HTTPException(status_code=400, detail=_CANDIDATE_INPUT_ERROR) from None

    if not application_details.joining_availability:
        raise HTTPException(status_code=400, detail=_CANDIDATE_INPUT_ERROR)
    if application_details.salary_expectation < 0:
        raise HTTPException(status_code=400, detail=_CANDIDATE_INPUT_ERROR)

    suffix, data = _read_cv_upload(cv)
    cv_text = _extract_uploaded_cv_text(suffix, data)
    job_profile = _load_job_profile(job)

    try:
        candidate_profile = parse_cv(cv_text)
        candidate = get_or_create_candidate(db, identity)
        classified_reqs = classify_requirements(job_profile)
        eligibility_result = check_eligibility(
            job_profile,
            classified_reqs,
            candidate_profile,
            application_details,
            RecruiterConstraints(),
            provider=get_default_provider(),
        )
        application = create_application(
            db,
            candidate=candidate,
            job_posting=job,
            candidate_profile=candidate_profile,
            application_details=application_details,
            constraints=RecruiterConstraints(),
            eligibility_result=eligibility_result,
        )
        if eligibility_result.overall_eligible:
            generate_interview_token(db, application)
        candidate_id = candidate.id
        application_id = application.id
        db.commit()
        db.refresh(application)
        db.refresh(candidate)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    invitation_sent = False
    if eligibility_result.overall_eligible:
        invitation_sent = _maybe_send_invitation(
            application=application,
            candidate=candidate,
            job_title=job.job_title,
            db=db,
        )

    return ApplyResponse(
        application_id=application_id,
        candidate_id=candidate_id,
        job_posting_id=job.id,
        job_title=job.job_title,
        overall_eligible=eligibility_result.overall_eligible,
        invitation_sent=invitation_sent,
    )
