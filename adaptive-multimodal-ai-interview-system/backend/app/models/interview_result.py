"""
app/models/interview_result.py

One row per application that proceeded to interview (interviews only run
for eligible candidates -- see Application.overall_eligible). final_report
is the FinalAssessmentReport dataclass, converted with dataclasses.asdict()
before writing. interview_plan/qa_transcript/gap_analysis capture the raw
interview data FinalAssessmentReport summarizes but doesn't retain -- the
same data run_real_interview.py currently dumps to a standalone .txt file
for lack of anywhere else to put it; this table is meant to replace that.

interview_eligibility_result is deliberately not named overall_eligible or
a bare eligibility_result: FinalAssessmentReport.eligibility_result is a
skill-matrix-based recheck computed during the interview stage -- a
different computation from Application.overall_eligible (the pre-interview
gate) -- even though both are "Pass/Fail"-shaped. Distinct names prevent
two same-looking columns across tables from meaning different things.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InterviewResult(Base):
    __tablename__ = "interview_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    final_report: Mapped[dict] = mapped_column(JSONB, nullable=False)
    recommendation: Mapped[str] = mapped_column(String, nullable=False, index=True)
    interview_eligibility_result: Mapped[str] = mapped_column(String, nullable=False)

    problem_solving_performance: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    communication_performance: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)

    interview_plan: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    qa_transcript: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    gap_analysis: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    application: Mapped["Application"] = relationship(back_populates="interview_result")
