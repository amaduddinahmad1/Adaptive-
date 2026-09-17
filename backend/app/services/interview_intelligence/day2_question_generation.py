import logging
from typing import List, Optional

from .models import InterviewPlan, Question, derive_experience_level
from .question_coverage import select_technology_areas
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile

logger = logging.getLogger(__name__)


def _difficulty_for_level(level: str) -> str:
    return level


def _project_area(candidate_profile: CandidateProfile, primary_areas: List[str]) -> str:
    if not candidate_profile.projects:
        return primary_areas[1] if len(primary_areas) > 1 else primary_areas[0]
    return candidate_profile.projects[0].name


def _build_question_text(category: str, area: str, candidate_name: str) -> str:
    templates = {
        "Role-specific": f"Describe how you would contribute to {area} responsibilities in a backend engineering role.",
        "Technology": f"How would you use {area} in a production system to balance correctness, performance, and maintainability?",
        "Project": f"Walk through a project where you used {area} and explain the architecture, trade-offs, and outcomes.",
        "Architecture": f"Design a scalable system around {area} for a growing product with reliability and latency requirements.",
        "Problem-solving": f"Given a live traffic spike, how would you diagnose and fix a failure in a {area}-based service?",
    }
    return templates.get(category, f"Explain your approach to {area} in a real production environment.")


def generate_questions(
    job_requirements: JobRequirementProfile,
    candidate_profile: CandidateProfile,
    interview_plan: InterviewPlan,
    target_count: Optional[int] = None,
) -> List[Question]:
    """Generate a set of interview questions from the plan and profile."""
    candidate_level = derive_experience_level(candidate_profile)
    logger.info("Generating questions for candidate")
    questions: List[Question] = []
    primary_areas = interview_plan.skill_areas or job_requirements.required_skills
    technology_areas = select_technology_areas(job_requirements, candidate_profile)
    question_topics = [
        ("Role-specific", "API Design"),
        *[("Technology", area) for area in technology_areas],
        ("Project", _project_area(candidate_profile, primary_areas)),
        ("Architecture", "System Design"),
        (
            "Problem-solving",
            primary_areas[2] if len(primary_areas) > 2 else "Performance Engineering",
        ),
    ]

    for category, knowledge_area in question_topics:
        question = Question(
            question_text=_build_question_text(category, knowledge_area, "candidate"),
            expected_knowledge_area=knowledge_area,
            question_type=category,
            baseline_difficulty=_difficulty_for_level(candidate_level),
            skills_covered=[knowledge_area],
        )
        questions.append(question)

    if target_count and target_count > len(questions):
        questions = _extend_questions_to_count(
            questions,
            job_requirements,
            candidate_profile,
            interview_plan,
            target_count,
            candidate_level,
        )

    logger.info("Generated %d questions", len(questions))
    return questions


def _extend_questions_to_count(
    questions: List[Question],
    job_requirements: JobRequirementProfile,
    candidate_profile: CandidateProfile,
    interview_plan: InterviewPlan,
    target_count: int,
    candidate_level: str,
) -> List[Question]:
    """Add more real templated questions when the recruiter budget exceeds the base set.

    Does not invent scores or placeholder prompts. Extra questions reuse the
    existing category templates against known skill/technology areas.
    """
    areas = list(interview_plan.skill_areas or job_requirements.required_skills or [])
    if not areas:
        areas = ["Backend Engineering"]
    technology_areas = select_technology_areas(job_requirements, candidate_profile) or areas
    rotation = [
        ("Role-specific", areas[0]),
        *[("Technology", area) for area in technology_areas],
        ("Project", _project_area(candidate_profile, areas)),
        ("Architecture", "System Design"),
        (
            "Problem-solving",
            areas[2] if len(areas) > 2 else "Performance Engineering",
        ),
    ]
    existing_texts = {question.question_text for question in questions}
    suffixes = (
        "What specific trade-offs did you consider?",
        "How would you measure success in production?",
        "What would you change if you had to do it again?",
    )
    extra: List[Question] = []
    index = 0
    suffix_index = 0
    guard = 0
    while len(questions) + len(extra) < target_count and guard < 80:
        category, knowledge_area = rotation[index % len(rotation)]
        index += 1
        guard += 1
        text = _build_question_text(category, knowledge_area, "candidate")
        if text in existing_texts:
            text = f"{text} {suffixes[suffix_index % len(suffixes)]}"
            suffix_index += 1
        if text in existing_texts:
            continue
        extra.append(
            Question(
                question_text=text,
                expected_knowledge_area=knowledge_area,
                question_type=category,
                baseline_difficulty=_difficulty_for_level(candidate_level),
                skills_covered=[knowledge_area],
            )
        )
        existing_texts.add(text)
    return questions + extra
