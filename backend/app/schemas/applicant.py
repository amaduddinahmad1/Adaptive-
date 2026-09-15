"""
app/schemas/applicant.py

Candidate identity/contact info, supplied directly by the applicant at
application time -- not parsed from CV text (unreliable, and the wrong
source: contact info should come from the applicant, not from whatever
their PDF happens to say). Mirrors ApplicationDetails' existing pattern of
structured, non-LLM-parsed, candidate-supplied input.
"""
from typing import Optional

from pydantic import BaseModel, EmailStr


class ApplicantIdentity(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
