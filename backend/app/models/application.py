"""
app/models/application.py

Links a candidate to a job posting and records the eligibility decision for
that specific pairing. candidate_profile and job_profile_snapshot are JSONB
snapshots of the exact CandidateProfile/JobRequirementProfile used for this
eligibility check -- independent of job_postings.parsed_profile and of
whatever the candidate's CV parses to on a future application, so a
historical decision stays reconstructable even if either source is later
re-parsed differently.

overall_eligible is promoted out of eligibility_result (JSONB) into its own
indexed column so it can be filtered/sorted on directly. It belongs here,
not on InterviewResult, because EligibilityResult -- including
overall_eligible -- is produced by check_eligibility() at the application
stage, before any interview happens.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    job_posting_id: Mapped[int] = mapped_column(ForeignKey("job_postings.id"), nullable=False, index=True)

    candidate_profile: Mapped[dict] = mapped_column(JSONB, nullable=False)
    job_profile_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

    joining_availability: Mapped[str] = mapped_column(String, nullable=False)
    salary_expectation: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    recruiter_max_notice_period_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recruiter_salary_min: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    recruiter_salary_max: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    eligibility_result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    overall_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Interview invitation link (Phase 1 of email notification feature).
    # interview_token/token_expires_at are populated together, later, by the
    # invite-generation step -- not at Application creation time -- so both
    # stay nullable with no DB-level default. token_used has a single
    # always-correct value from row creation onward, so it gets a real
    # NOT NULL + server default instead.
    interview_token: Mapped[Optional[str]] = mapped_column(String, nullable=True, unique=True, index=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    token_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="applications")
    job_posting: Mapped["JobPosting"] = relationship(back_populates="applications")
    interview_result: Mapped[Optional["InterviewResult"]] = relationship(
        back_populates="application", uselist=False, cascade="all, delete-orphan"
    )
