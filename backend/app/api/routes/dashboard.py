"""
app/api/routes/dashboard.py

Read-only recruiter dashboard endpoints. All responses are dedicated
Pydantic models — ORM instances are never returned directly.
application_count is computed in SQL (subquery + func.count), not stored
and not counted in Python. has_interview_result is a left-join existence
check against interview_results, not an N+1 lookup.

Phase 4A adds recruiter-facing reads of already-persisted Application,
JobPosting, and InterviewResult rows, plus a thin job-create wrapper around
the existing parse_job_description + create_job_posting path. Interview
intelligence, eligibility, invitations, and voice behavior are unchanged.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.core.auth import require_recruiter
from app.core.ownership import job_owned_by
from app.core.interview_config import (
    DEFAULT_INTERVIEW_QUESTION_COUNT,
    MAX_INTERVIEW_QUESTION_COUNT,
    MIN_INTERVIEW_QUESTION_COUNT,
    normalize_interview_question_count,
)
from app.db.session import get_db
from app.models.application import HIRING_DECISION_PENDING, Application
from app.models.candidate import Candidate
from app.models.interview_result import InterviewResult
from app.models.job_posting import JobPosting
from app.models.user import User
from app.services.jd_intelligence.jd_parser import parse_job_description
from app.services.persistence.application_repository import (
    create_job_posting,
    set_application_hiring_decision,
)

router = APIRouter(tags=["dashboard"], dependencies=[Depends(require_recruiter)])


class ApplicationSummary(BaseModel):
    id: int
    candidate_id: int
    candidate_full_name: str
    candidate_email: str
    job_posting_id: int
    job_title: str
    overall_eligible: bool
    joining_availability: str
    salary_expectation: Decimal
    created_at: datetime
    has_interview_result: bool
    email_sent_at: Optional[datetime] = None
    token_used: bool = False
    token_expires_at: Optional[datetime] = None
    hiring_decision: str = HIRING_DECISION_PENDING


class ApplicationDetail(ApplicationSummary):
    candidate_phone: Optional[str] = None
    candidate_profile: Dict[str, Any]
    job_profile_snapshot: Dict[str, Any]
    eligibility_result: Dict[str, Any]
    recruiter_max_notice_period_days: Optional[int] = None
    recruiter_salary_min: Optional[Decimal] = None
    recruiter_salary_max: Optional[Decimal] = None
    interview_result_id: Optional[int] = None


class CandidateSummary(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str]
    created_at: datetime
    application_count: int


class CandidateDetail(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str]
    created_at: datetime
    applications: List[ApplicationSummary]


class JobPostingSummary(BaseModel):
    id: int
    job_title: str
    created_at: datetime
    application_count: int
    interview_question_count: int = DEFAULT_INTERVIEW_QUESTION_COUNT
    required_skills: List[str] = Field(default_factory=list)
    required_technologies: List[str] = Field(default_factory=list)


class JobPostingDetail(BaseModel):
    id: int
    job_title: str
    raw_jd_text: str
    parsed_profile: Optional[Dict[str, Any]] = None
    created_at: datetime
    application_count: int
    interview_question_count: int = DEFAULT_INTERVIEW_QUESTION_COUNT


class CreateJobPostingRequest(BaseModel):
    job_title: str
    jd_text: str
    interview_question_count: int = Field(
        default=DEFAULT_INTERVIEW_QUESTION_COUNT,
        ge=MIN_INTERVIEW_QUESTION_COUNT,
        le=MAX_INTERVIEW_QUESTION_COUNT,
        description="How many questions the AI should ask during the interview",
    )


class ApplicationDecisionRequest(BaseModel):
    decision: Literal["rejected"]


class InterviewResultDetail(BaseModel):
    id: int
    application_id: int
    candidate_id: int
    candidate_full_name: str
    candidate_email: str
    job_posting_id: int
    job_title: str
    recommendation: str
    interview_eligibility_result: str
    problem_solving_performance: Optional[Decimal] = None
    communication_performance: Optional[Decimal] = None
    final_report: Dict[str, Any]
    interview_plan: Optional[Dict[str, Any]] = None
    qa_transcript: Optional[Dict[str, Any]] = None
    gap_analysis: Optional[Dict[str, Any]] = None
    created_at: datetime


_ApplicationRow = Tuple[Application, str, str, str, Optional[int]]


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes"}
    return bool(value)


def _job_skill_lists(parsed_profile: Optional[dict]) -> Tuple[List[str], List[str]]:
    if not isinstance(parsed_profile, dict):
        return [], []
    return (
        _string_list(parsed_profile.get("required_skills")),
        _string_list(parsed_profile.get("required_technologies")),
    )


def _applications_query(db: Session, recruiter: User) -> Query:
    return (
        db.query(
            Application,
            Candidate.full_name,
            Candidate.email,
            JobPosting.job_title,
            InterviewResult.id,
        )
        .join(Candidate, Application.candidate_id == Candidate.id)
        .join(JobPosting, Application.job_posting_id == JobPosting.id)
        .outerjoin(InterviewResult, InterviewResult.application_id == Application.id)
        .filter(job_owned_by(recruiter))
    )


def _to_application_summary(row: _ApplicationRow) -> ApplicationSummary:
    application, candidate_full_name, candidate_email, job_title, interview_result_id = row
    return ApplicationSummary(
        id=application.id,
        candidate_id=application.candidate_id,
        candidate_full_name=candidate_full_name,
        candidate_email=candidate_email,
        job_posting_id=application.job_posting_id,
        job_title=job_title,
        overall_eligible=application.overall_eligible,
        joining_availability=application.joining_availability,
        salary_expectation=application.salary_expectation,
        created_at=application.created_at,
        has_interview_result=interview_result_id is not None,
        email_sent_at=application.email_sent_at,
        token_used=bool(application.interview_token) and _as_bool(application.token_used, False),
        token_expires_at=application.token_expires_at,
        hiring_decision=application.hiring_decision or HIRING_DECISION_PENDING,
    )


def _to_application_detail(row: _ApplicationRow, phone: Optional[str]) -> ApplicationDetail:
    application, _name, _email, _title, interview_result_id = row
    summary = _to_application_summary(row)
    return ApplicationDetail(
        **summary.model_dump(),
        candidate_phone=phone,
        candidate_profile=application.candidate_profile or {},
        job_profile_snapshot=application.job_profile_snapshot or {},
        eligibility_result=application.eligibility_result or {},
        recruiter_max_notice_period_days=application.recruiter_max_notice_period_days,
        recruiter_salary_min=application.recruiter_salary_min,
        recruiter_salary_max=application.recruiter_salary_max,
        interview_result_id=interview_result_id,
    )


def _application_count_for_job(db: Session, job_id: int) -> int:
    count = (
        db.query(func.count(Application.id))
        .filter(Application.job_posting_id == job_id)
        .scalar()
    )
    return int(count or 0)


def _job_question_count(job: JobPosting) -> int:
    return normalize_interview_question_count(
        getattr(job, "interview_question_count", None)
    )


def _to_job_detail(job: JobPosting, application_count: int) -> JobPostingDetail:
    return JobPostingDetail(
        id=job.id,
        job_title=job.job_title,
        raw_jd_text=job.raw_jd_text,
        parsed_profile=job.parsed_profile,
        created_at=job.created_at,
        application_count=application_count,
        interview_question_count=_job_question_count(job),
    )


@router.get("/candidates", response_model=List[CandidateSummary])
def list_candidates(
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> List[CandidateSummary]:
    application_counts = (
        db.query(
            Application.candidate_id.label("candidate_id"),
            func.count(Application.id).label("application_count"),
        )
        .join(JobPosting, Application.job_posting_id == JobPosting.id)
        .filter(job_owned_by(recruiter))
        .group_by(Application.candidate_id)
        .subquery()
    )
    rows = (
        db.query(Candidate, application_counts.c.application_count)
        .join(application_counts, Candidate.id == application_counts.c.candidate_id)
        .order_by(Candidate.created_at.desc())
        .all()
    )
    return [
        CandidateSummary(
            id=candidate.id,
            full_name=candidate.full_name,
            email=candidate.email,
            phone=candidate.phone,
            created_at=candidate.created_at,
            application_count=int(count),
        )
        for candidate, count in rows
    ]


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def get_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> CandidateDetail:
    owned_application = (
        db.query(Application.id)
        .join(JobPosting, Application.job_posting_id == JobPosting.id)
        .filter(
            Application.candidate_id == candidate_id,
            job_owned_by(recruiter),
        )
        .first()
    )
    if owned_application is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    application_rows = (
        _applications_query(db, recruiter)
        .filter(Application.candidate_id == candidate_id)
        .order_by(Application.created_at.desc())
        .all()
    )
    return CandidateDetail(
        id=candidate.id,
        full_name=candidate.full_name,
        email=candidate.email,
        phone=candidate.phone,
        created_at=candidate.created_at,
        applications=[_to_application_summary(row) for row in application_rows],
    )


@router.get("/jobs", response_model=List[JobPostingSummary])
def list_jobs(
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> List[JobPostingSummary]:
    application_counts = (
        db.query(
            Application.job_posting_id.label("job_posting_id"),
            func.count(Application.id).label("application_count"),
        )
        .group_by(Application.job_posting_id)
        .subquery()
    )
    rows = (
        db.query(JobPosting, func.coalesce(application_counts.c.application_count, 0))
        .outerjoin(application_counts, JobPosting.id == application_counts.c.job_posting_id)
        .filter(job_owned_by(recruiter))
        .order_by(JobPosting.created_at.desc())
        .all()
    )
    summaries: List[JobPostingSummary] = []
    for job, count in rows:
        skills, technologies = _job_skill_lists(job.parsed_profile)
        summaries.append(
            JobPostingSummary(
                id=job.id,
                job_title=job.job_title,
                created_at=job.created_at,
                application_count=int(count),
                interview_question_count=_job_question_count(job),
                required_skills=skills,
                required_technologies=technologies,
            )
        )
    return summaries


@router.post("/jobs", response_model=JobPostingDetail)
def create_job(
    request: CreateJobPostingRequest,
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> JobPostingDetail:
    """Persist a job posting using the existing JD parser + repository insert."""
    jd_text = (request.jd_text or "").strip()
    if not jd_text:
        raise HTTPException(status_code=400, detail="jd_text is required")
    job_title = (request.job_title or "").strip()
    try:
        parsed_profile = parse_job_description(jd_text)
        title = job_title or parsed_profile.job_title
        job_posting = create_job_posting(
            db,
            job_title=title,
            raw_jd_text=jd_text,
            parsed_profile=parsed_profile,
            interview_question_count=request.interview_question_count,
            created_by_user_id=recruiter.id,
        )
        db.commit()
        db.refresh(job_posting)
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise
    return _to_job_detail(job_posting, 0)


@router.get("/jobs/{job_id}", response_model=JobPostingDetail)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> JobPostingDetail:
    job = (
        db.query(JobPosting)
        .filter(JobPosting.id == job_id, job_owned_by(recruiter))
        .first()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job posting not found")
    return _to_job_detail(job, _application_count_for_job(db, job.id))


@router.get("/applications", response_model=List[ApplicationSummary])
def list_applications(
    eligible_only: bool = False,
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> List[ApplicationSummary]:
    query = _applications_query(db, recruiter).order_by(Application.created_at.desc())
    if eligible_only:
        query = query.filter(Application.overall_eligible.is_(True))
    return [_to_application_summary(row) for row in query.all()]


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> ApplicationDetail:
    row = (
        _applications_query(db, recruiter)
        .filter(Application.id == application_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    application = row[0]
    candidate = db.query(Candidate).filter(Candidate.id == application.candidate_id).first()
    phone = candidate.phone if candidate is not None else None
    return _to_application_detail(row, phone)


@router.post(
    "/applications/{application_id}/decision",
    response_model=ApplicationDetail,
)
def set_application_decision(
    application_id: int,
    request: ApplicationDecisionRequest,
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> ApplicationDetail:
    """Persist a recruiter hiring decision. Does not delete candidate or interview data."""
    row = (
        _applications_query(db, recruiter)
        .filter(Application.id == application_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    application = row[0]
    try:
        set_application_hiring_decision(db, application, request.decision)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(application)
    candidate = db.query(Candidate).filter(Candidate.id == application.candidate_id).first()
    phone = candidate.phone if candidate is not None else None
    refreshed = (
        _applications_query(db, recruiter)
        .filter(Application.id == application_id)
        .first()
    )
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return _to_application_detail(refreshed, phone)


@router.get(
    "/applications/{application_id}/interview-result",
    response_model=InterviewResultDetail,
)
def get_application_interview_result(
    application_id: int,
    db: Session = Depends(get_db),
    recruiter: User = Depends(require_recruiter),
) -> InterviewResultDetail:
    row = (
        db.query(
            InterviewResult,
            Application,
            Candidate.full_name,
            Candidate.email,
            JobPosting.job_title,
        )
        .join(Application, InterviewResult.application_id == Application.id)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .join(JobPosting, Application.job_posting_id == JobPosting.id)
        .filter(Application.id == application_id, job_owned_by(recruiter))
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Interview result not found for this application",
        )
    result, application, candidate_full_name, candidate_email, job_title = row
    return InterviewResultDetail(
        id=result.id,
        application_id=application.id,
        candidate_id=application.candidate_id,
        candidate_full_name=candidate_full_name,
        candidate_email=candidate_email,
        job_posting_id=application.job_posting_id,
        job_title=job_title,
        recommendation=result.recommendation,
        interview_eligibility_result=result.interview_eligibility_result,
        problem_solving_performance=result.problem_solving_performance,
        communication_performance=result.communication_performance,
        final_report=result.final_report or {},
        interview_plan=result.interview_plan,
        qa_transcript=result.qa_transcript,
        gap_analysis=result.gap_analysis,
        created_at=result.created_at,
    )
