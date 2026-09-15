import logging
from typing import Dict, List

from .models import (
    InterviewPlan,
    derive_experience_level,
    derive_job_experience_level,
)
from .question_coverage import select_technology_areas
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile

logger = logging.getLogger(__name__)

TARGET_INTERVIEW_MINUTES = 90
_QUESTION_TIME_WEIGHTS = {
    "Role-specific": 1.0,
    "Technology": 1.0,
    "Project": 1.5,
    "Architecture": 1.5,
    "Problem-solving": 1.0,
}


def _difficulty_depth(candidate_level: str) -> str:
    mapping = {
        "Intern": "Foundational",
        "Junior": "Core concepts",
        "Mid-Level": "Applied architecture and trade-offs",
        "Senior": "System-wide design and leadership",
    }
    return mapping.get(candidate_level, "Applied architecture and trade-offs")


def _allocate_question_time(question_counts: Dict[str, int]) -> Dict[str, int]:
    weighted_counts = {
        category: count * _QUESTION_TIME_WEIGHTS[category]
        for category, count in question_counts.items()
    }
    total_weight = sum(weighted_counts.values())
    allocations = {
        category: int(TARGET_INTERVIEW_MINUTES * weight / total_weight)
        for category, weight in weighted_counts.items()
    }
    remainder = TARGET_INTERVIEW_MINUTES - sum(allocations.values())
    if remainder:
        largest_category = max(weighted_counts, key=weighted_counts.get)
        allocations[largest_category] += remainder
    return allocations


def generate_interview_plan(job_requirements: JobRequirementProfile, candidate_profile: CandidateProfile) -> InterviewPlan:
    """Create a structured interview plan based on job requirements and candidate experience."""
    logger.info("Generating interview plan for role %s", job_requirements.job_title)
    candidate_level = derive_experience_level(candidate_profile)
    job_level = derive_job_experience_level(job_requirements)
    technology_areas = select_technology_areas(job_requirements, candidate_profile)
    logger.debug("Derived candidate level %s for job level %s", candidate_level, job_level)

    skill_areas = []
    job_skills = [s.strip() for s in job_requirements.required_skills if s.strip()]
    preferred = [s.strip() for s in job_requirements.preferred_skills if s.strip()]
    skill_areas.extend(job_skills)
    for skill in preferred:
        if skill not in skill_areas:
            skill_areas.append(skill)

    if candidate_profile.skills:
        candidate_skill_set = {s.lower() for s in candidate_profile.skills}
        for skill in candidate_skill_set:
            if skill not in {s.lower() for s in skill_areas}:
                skill_areas.append(skill.title())

    question_types = ["Role-specific", "Technology", "Project", "Architecture", "Problem-solving"]
    question_order = ["Role-specific", "Technology", "Project", "Architecture", "Problem-solving"]

    topic_depth = {
        skill: _difficulty_depth(candidate_level)
        for skill in skill_areas[: min(len(skill_areas), 6)]
    }

    question_counts = {
        "Role-specific": 1,
        "Technology": len(technology_areas),
        "Project": 1,
        "Architecture": 1,
        "Problem-solving": 1,
    }
    time_allocation = _allocate_question_time(question_counts)
    total_minutes = sum(time_allocation.values())

    plan = InterviewPlan(
        skill_areas=skill_areas[:10],
        question_types=question_types,
        question_order=question_order,
        topic_depth=topic_depth,
        time_allocation=time_allocation,
        estimated_time=total_minutes,
    )
    logger.info("Interview plan created with %d skill areas and %d minutes total", len(plan.skill_areas), plan.estimated_time)
    return plan
