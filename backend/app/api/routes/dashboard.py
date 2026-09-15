"""
app/api/routes/dashboard.py

Read-only recruiter dashboard endpoints. All responses are dedicated
Pydantic models — ORM instances are never returned directly.
application_count is computed in SQL (subquery + func.count), not stored
and not counted in Python. has_interview_result is a left-join existence
check against interview_results, not an N+1 lookup.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.db.session import get_db
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.interview_result import InterviewResult
from app.models.job_posting import JobPosting

router = APIRouter(tags=["dashboard"])


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


_ApplicationRow = Tuple[Application, str, str, str, Optional[int]]


def _applications_query(db: Session) -> Query:
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
    )


@router.get("/candidates", response_model=List[CandidateSummary])
def list_candidates(db: Session = Depends(get_db)) -> List[CandidateSummary]:
    application_counts = (
        db.query(
            Application.candidate_id.label("candidate_id"),
            func.count(Application.id).label("application_count"),
        )
        .group_by(Application.candidate_id)
        .subquery()
    )
    rows = (
        db.query(Candidate, func.coalesce(application_counts.c.application_count, 0))
        .outerjoin(application_counts, Candidate.id == application_counts.c.candidate_id)
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
def get_candidate(candidate_id: int, db: Session = Depends(get_db)) -> CandidateDetail:
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    application_rows = (
        _applications_query(db)
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
def list_jobs(db: Session = Depends(get_db)) -> List[JobPostingSummary]:
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
        .order_by(JobPosting.created_at.desc())
        .all()
    )
    return [
        JobPostingSummary(
            id=job.id,
            job_title=job.job_title,
            created_at=job.created_at,
            application_count=int(count),
        )
        for job, count in rows
    ]


@router.get("/applications", response_model=List[ApplicationSummary])
def list_applications(
    eligible_only: bool = False,
    db: Session = Depends(get_db),
) -> List[ApplicationSummary]:
    query = _applications_query(db).order_by(Application.created_at.desc())
    if eligible_only:
        query = query.filter(Application.overall_eligible.is_(True))
    return [_to_application_summary(row) for row in query.all()]
