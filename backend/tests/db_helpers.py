"""
SQLite test database helpers for Application-backed voice tests.

There is no existing backend DB test harness, so these helpers provide a
create_all() SQLite stand-in. JSONB is compiled as JSON for SQLite only.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.job_posting import JobPosting
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile
import app.models  # noqa: F401  — populate Base.metadata


SAMPLE_CANDIDATE_PROFILE = CandidateProfile(
    skills=["Python", "FastAPI", "PostgreSQL"],
    technologies=["Python", "FastAPI", "PostgreSQL"],
    projects=[
        {
            "name": "Interview Platform",
            "description": "Built FastAPI services backed by PostgreSQL.",
            "technologies": ["FastAPI", "PostgreSQL"],
        }
    ],
    work_experience=[
        {
            "position": "Backend Engineer",
            "company": "Acme",
            "start_date": "2022-01",
            "end_date": "present",
            "description": "Designed FastAPI endpoints and PostgreSQL schemas for production APIs.",
        }
    ],
    education=["BS Computer Science"],
    certifications=[],
    achievements=["Reduced API latency by 40%"],
    technology_specific_experience=[
        {"technology": "FastAPI", "years": 2.0},
        {"technology": "PostgreSQL", "years": 2.0},
    ],
).model_dump(mode="json")

SAMPLE_JOB_PROFILE = JobRequirementProfile(
    job_title="Backend Engineer",
    required_skills=["Python", "FastAPI", "PostgreSQL"],
    preferred_skills=["Docker"],
    required_technologies=["Python", "FastAPI", "PostgreSQL"],
    preferred_technologies=["Docker"],
).model_dump(mode="json")


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


def create_test_engine() -> Engine:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return engine


def create_test_session(engine: Engine) -> Session:
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def seed_application(
    db: Session,
    *,
    overall_eligible: bool = True,
    email: str | None = None,
) -> Application:
    """Insert a real Candidate, JobPosting, and Application; IDs come from the DB."""
    candidate = Candidate(
        full_name="Test Candidate",
        email=email or f"candidate-{uuid4().hex}@example.com",
    )
    job_posting = JobPosting(
        job_title="Backend Engineer",
        raw_jd_text="Build and maintain backend services with Python, FastAPI, and PostgreSQL.",
        parsed_profile=SAMPLE_JOB_PROFILE,
    )
    db.add_all([candidate, job_posting])
    db.flush()

    application = Application(
        candidate_id=candidate.id,
        job_posting_id=job_posting.id,
        candidate_profile=SAMPLE_CANDIDATE_PROFILE,
        job_profile_snapshot=SAMPLE_JOB_PROFILE,
        joining_availability="immediate",
        salary_expectation=Decimal("120000"),
        eligibility_result={"overall_eligible": overall_eligible},
        overall_eligible=overall_eligible,
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return application
