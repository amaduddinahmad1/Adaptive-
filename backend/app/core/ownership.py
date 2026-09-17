"""SQL-level recruiter ownership filters.

Recruiter data is scoped through job_postings.created_by_user_id. Applications,
candidates, interview results, and recruiter-visible sessions inherit ownership
from the related job. Unowned (NULL) legacy jobs are not visible to any
recruiter API.
"""
from __future__ import annotations

from typing import Iterable, Set

from sqlalchemy.orm import Query, Session

from app.models.application import Application
from app.models.job_posting import JobPosting
from app.models.user import User


def job_owned_by(recruiter: User):
    return JobPosting.created_by_user_id == recruiter.id


def owned_jobs_query(db: Session, recruiter: User) -> Query:
    return db.query(JobPosting).filter(job_owned_by(recruiter))


def owned_application_ids(
    db: Session,
    recruiter: User,
    application_ids: Iterable[int] | None = None,
) -> Set[int]:
    query = (
        db.query(Application.id)
        .join(JobPosting, Application.job_posting_id == JobPosting.id)
        .filter(job_owned_by(recruiter))
    )
    if application_ids is not None:
        ids = list(application_ids)
        if not ids:
            return set()
        query = query.filter(Application.id.in_(ids))
    return {row[0] for row in query.all()}


def recruiter_owns_application(
    db: Session,
    recruiter: User,
    application_id: int,
) -> bool:
    return application_id in owned_application_ids(db, recruiter, [application_id])
