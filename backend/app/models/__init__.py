"""
app/models/__init__.py

Imports every model so Base.metadata is fully populated as soon as
app.models is imported -- required for Alembic autogenerate (env.py imports
this module) and for any create_all()-based test setup.
"""
from app.models.candidate import Candidate
from app.models.job_posting import JobPosting
from app.models.application import Application
from app.models.interview_result import InterviewResult
from app.models.user import User
from app.models.password_reset_token import PasswordResetToken

__all__ = [
    "Candidate",
    "JobPosting",
    "Application",
    "InterviewResult",
    "User",
    "PasswordResetToken",
]
