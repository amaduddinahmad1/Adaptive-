import logging
from typing import Iterable, List

from app.services.interview_intelligence.models import (
    AnswerEvaluation,
    FinalAssessmentReport,
    GapAnalysisEntry,
    InterviewPlan,
    Question,
    SkillMatrixEntry,
    derive_experience_level,
    derive_job_experience_level,
)
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile

logger = logging.getLogger(__name__)


def _derive_eligibility(candidate_profile: CandidateProfile, job_requirements: JobRequirementProfile, skill_matrix: Iterable[SkillMatrixEntry]) -> str:
    required_skills = set(job_requirements.required_skills)
    matrix_skills = {item.skill_name for item in skill_matrix}
    minimum_requirement = bool(required_skills.intersection(matrix_skills))
    candidate_level = derive_experience_level(candidate_profile)
    job_level = derive_job_experience_level(job_requirements)
    level_match = candidate_level in {"Mid-Level", "Senior"} or job_level in {"Intern", "Junior"}
    return "Pass" if minimum_requirement and level_match else "Fail"


def generate_final_assessment(
    candidate_profile: CandidateProfile,
    job_requirements: JobRequirementProfile,
    interview_plan: InterviewPlan,
    question_set: List[Question],
    answer_evaluations: List[AnswerEvaluation],
    skill_matrix: List[SkillMatrixEntry],
    gap_analysis: List[GapAnalysisEntry],
    unmatched_cv_claims: List[str] | None = None,
) -> FinalAssessmentReport:
    """Create the final hiring assessment report for recruiter review."""
    logger.info("Generating final assessment for candidate")

    problem_solving = round(sum(item.problem_solving for item in answer_evaluations) / max(1, len(answer_evaluations)), 2)
    communication = round(sum(item.communication for item in answer_evaluations) / max(1, len(answer_evaluations)), 2)

    strengths = []
    if skill_matrix:
        top_skills = sorted(skill_matrix, key=lambda item: item.proficiency_score, reverse=True)[:3]
        strengths = [f"{item.skill_name} proficiency {item.proficiency_score}%" for item in top_skills]

    weak_areas = []
    for item in skill_matrix:
        if item.assessment_count == 0:
            weak_areas.append(f"{item.skill_name} not yet assessed")
        elif item.proficiency_score < 60:
            weak_areas.append(f"{item.skill_name} below expected confidence")
    if not weak_areas:
        weak_areas = ["No major gaps surfaced in this sample; continue deeper validation in live panel review."]

    alignment_summary = {"Strong": 0, "Moderate": 0, "Weak": 0}
    for gap in gap_analysis:
        alignment_summary[gap.alignment] = alignment_summary.get(gap.alignment, 0) + 1

    eligibility_result = _derive_eligibility(candidate_profile, job_requirements, skill_matrix)

    if eligibility_result == "Pass" and problem_solving >= 70 and communication >= 70:
        recommendation = "Hire"
        reason = "Candidate shows adequate evidence across key skills and communication signals for the target role."
    elif eligibility_result == "Pass" and (problem_solving < 70 or communication < 70):
        recommendation = "Further Evaluation"
        reason = "Candidate meets baseline evidence but needs more evaluation for depth or communication consistency."
    else:
        recommendation = "Decline"
        reason = "Insufficient evidence against required skill areas for the targeted role."

    report = FinalAssessmentReport(
        eligibility_result=eligibility_result,
        skill_scores=skill_matrix,
        problem_solving_performance=problem_solving,
        communication_performance=communication,
        cv_interview_consistency=alignment_summary,
        strengths=strengths,
        areas_requiring_evaluation=weak_areas,
        recommendation=recommendation,
        recommendation_reason=reason,
        unmatched_cv_claims=unmatched_cv_claims or [],
        reasoning_summary=(
            f"Candidate completed {len(question_set)} questions over {interview_plan.estimated_time} minutes. "
            f"The final assessment is based on {len(answer_evaluations)} scored responses and a structured skill matrix."
        ),
    )
    logger.info("Final assessment complete: %s", report.recommendation)
    return report
