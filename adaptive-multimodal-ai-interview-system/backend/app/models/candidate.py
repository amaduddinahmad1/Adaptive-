"""
app/models/candidate.py

Applicant identity/contact info only -- deliberately separate from the
parsed CandidateProfile (skills/experience/etc.), which lives as a
per-application JSONB snapshot on Application, not here. Mirrors the
existing, deliberate design choice that CandidateProfile represents parsed
CV content, not who the person is (see app/schemas/candidate.py).
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    applications: Mapped[List["Application"]] = relationship(back_populates="candidate")
