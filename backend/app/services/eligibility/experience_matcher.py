"""
app/services/eligibility/experience_matcher.py

Matches a JobRequirementProfile's experience_requirements against a
CandidateProfile, keeping general (overall tenure) and specific
(technology-bound) requirements strictly independent: a candidate's total
overall experience must never satisfy a technology-specific requirement,
and vice versa.
"""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.candidate import CandidateProfile
from app.schemas.job import ExperienceRequirement, ExperienceRequirementType, JobRequirementProfile
from app.services.eligibility.date_utils import calculate_total_general_experience


class ExperienceMatchResult(BaseModel):
    """Outcome of matching a single ExperienceRequirement against a candidate."""
    description: str
    required_years: float
    candidate_years: float
    met: bool
    requirement_type: ExperienceRequirementType
    target: Optional[str]


def _lookup_technology_years(candidate: CandidateProfile, target: Optional[str]) -> float:
    """
    Case/whitespace-insensitive lookup of a technology's years in the
    candidate's technology_experience_map.

    This only normalizes casing and incidental whitespace (e.g. "python" vs
    "Python ") because JD parsing and CV parsing are two independent LLM
    extractions with no shared vocabulary enforcement between them. It does
    NOT resolve near-miss vocabulary mismatches (e.g. "Node.js" vs "NodeJS"
    vs "Node") — that would need a semantic/fuzzy matching approach (the
    sentence-transformers skill-matching idea from the original tech stack
    discussion). Known future improvement, not implemented today.
    """
    if target is None:
        return 0.0

    normalized_target = target.strip().lower()
    normalized_map = {
        technology.strip().lower(): years
        for technology, years in candidate.technology_experience_map.items()
    }
    return normalized_map.get(normalized_target, 0.0)


def match_experience(
    requirement: ExperienceRequirement,
    candidate: CandidateProfile,
    *,
    today: Optional[date] = None,
) -> ExperienceMatchResult:
    """
    Matches a single experience requirement against a candidate.

    SPECIFIC requirements are checked only against
    candidate.technology_experience_map (never against overall tenure).
    GENERAL requirements are checked only against total general experience
    computed from candidate.work_experience (never against a single
    technology's years). This separation is the entire point of this
    function: a candidate's overall experience must never satisfy a
    technology-specific requirement, and a technology's years must never
    satisfy a general requirement.
    """
    if requirement.requirement_type == ExperienceRequirementType.SPECIFIC:
        candidate_years = _lookup_technology_years(candidate, requirement.target)
    else:
        candidate_years = calculate_total_general_experience(candidate.work_experience, today=today)

    return ExperienceMatchResult(
        description=requirement.description,
        required_years=requirement.years,
        candidate_years=candidate_years,
        met=candidate_years >= requirement.years,
        requirement_type=requirement.requirement_type,
        target=requirement.target,
    )


def match_all_experience_requirements(
    job_profile: JobRequirementProfile,
    candidate: CandidateProfile,
    *,
    today: Optional[date] = None,
) -> List[ExperienceMatchResult]:
    """
    Matches every experience requirement in a JobRequirementProfile against a
    candidate, independently. No requirement's outcome affects another's —
    e.g. a JD requiring 3yr overall + 2yr Python + 1yr FastAPI produces three
    independently-evaluated results.
    """
    return [
        match_experience(requirement, candidate, today=today)
        for requirement in job_profile.experience_requirements
    ]
