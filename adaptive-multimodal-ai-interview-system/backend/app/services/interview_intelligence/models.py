from __future__ import annotations

from datetime import date

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

from app.schemas.candidate import CandidateProfile
from app.services.eligibility.date_utils import calculate_total_general_experience
from app.schemas.job import JobRequirementProfile

DifficultyLevel = Literal["Intern", "Junior", "Mid-Level", "Senior"]
QuestionType = Literal["Role-specific", "Technology", "Project", "Architecture", "Problem-solving"]
Recommendation = Literal["Hire", "Further Evaluation", "Decline"]
ExperienceLevel = Literal["Intern", "Junior", "Mid-Level", "Senior"]
ANSWER_PASS_THRESHOLD = 65.0


def _experience_level_from_years(total_years: float) -> ExperienceLevel:
    if total_years < 1.0:
        return "Intern"
    if total_years < 3.0:
        return "Junior"
    if total_years < 6.0:
        return "Mid-Level"
    return "Senior"


def derive_experience_level(candidate: CandidateProfile) -> ExperienceLevel:
    """Derive a four-level experience tier from the real backend candidate schema.

    Use the shared general-experience calculator as the primary source; only fall
    back to technology-specific years when work history produces zero usable years.
    This avoids double-counting overlapping data.
    """
    work_total = calculate_total_general_experience(candidate.work_experience, today=date.today())
    if work_total > 0:
        return _experience_level_from_years(work_total)

    tech_total = sum(
        float(item.years) for item in candidate.technology_specific_experience if item.years is not None
    )
    if tech_total > 0:
        return _experience_level_from_years(tech_total)

    return "Intern"


def derive_job_experience_level(job: JobRequirementProfile) -> ExperienceLevel:
    """Derive a four-level experience tier from the JD's general requirements."""
    general_years = [
        float(req.years)
        for req in job.experience_requirements
        if req.requirement_type.value == "general" and req.is_mandatory and req.years > 0
    ]
    if not general_years:
        return "Intern"
    return _experience_level_from_years(max(general_years))


def iter_claim_sources(candidate: CandidateProfile) -> List[str]:
    """Return claim-like source texts from the real structured profile.

    This intentionally does not reference a nonexistent cv_claims field.
    """
    sources: List[str] = []
    seen = set()

    def add_value(value: Optional[str]) -> None:
        if value is None:
            return
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            sources.append(cleaned)

    for item in candidate.work_experience:
        add_value(item.description)

    for item in candidate.projects:
        add_value(item.description)

    for item in candidate.achievements:
        add_value(item)

    return sources


@dataclass
class InterviewPlan:
    skill_areas: List[str]
    question_types: List[str]
    question_order: List[str]
    topic_depth: Dict[str, str]
    time_allocation: Dict[str, int]
    estimated_time: int


@dataclass
class Question:
    question_text: str
    expected_knowledge_area: str
    question_type: QuestionType
    baseline_difficulty: DifficultyLevel
    skills_covered: List[str] = field(default_factory=list)
    follow_up_prompt: Optional[str] = None


@dataclass
class CVClaim:
    claim_text: str
    claim_questions: List[str]
    verification_focus: str = "experience authenticity"


@dataclass
class CVClaimEvidence:
    matched_claims: List[Dict[str, str]]
    unmatched_claims: List[str]


@dataclass
class AnswerEvaluation:
    question_text: str
    expected_knowledge_area: str
    question_type: QuestionType
    weighted_total: float
    technical_correctness: float
    problem_solving: float
    completeness: float
    reasoning: float
    communication: float
    pass_fail: bool
    criterion_scores: Dict[str, float] = field(default_factory=dict)
    skills_covered: List[str] = field(default_factory=list)
    recommendation_note: str = ""


@dataclass
class SkillMatrixEntry:
    skill_name: str
    proficiency_score: float
    assessment_count: int
    confidence_level: str
    evidence_summary: str = ""


@dataclass
class GapAnalysisEntry:
    skill: str
    cv_claim: str
    interview_evidence: str
    alignment: str


@dataclass
class DecisionOutcome:
    next_difficulty: str
    next_question_type: str
    follow_up_required: str
    reason: str


@dataclass
class FinalAssessmentReport:
    eligibility_result: str
    skill_scores: List[SkillMatrixEntry]
    problem_solving_performance: float
    communication_performance: float
    cv_interview_consistency: Dict[str, int]
    strengths: List[str]
    areas_requiring_evaluation: List[str]
    recommendation: Recommendation
    recommendation_reason: str
    unmatched_cv_claims: List[str] = field(default_factory=list)
    reasoning_summary: str = ""
