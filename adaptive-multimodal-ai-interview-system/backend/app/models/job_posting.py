"""
app/models/job_posting.py

Stores the raw JD text plus a cached parsed JobRequirementProfile
(parsed_profile). Parsing is a real Gemini call, so every candidate applying
to the same posting reuses one parse instead of re-parsing identical JD text
per application -- avoiding both the extra API cost and inconsistent LLM
output across candidates being evaluated against "the same" job.
Application.job_profile_snapshot still keeps its own copy at evaluation
time, for audit immutability if this posting is ever edited later.
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_title: Mapped[str] = mapped_column(String, nullable=False)
    raw_jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_profile: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    applications: Mapped[List["Application"]] = relationship(back_populates="job_posting")
