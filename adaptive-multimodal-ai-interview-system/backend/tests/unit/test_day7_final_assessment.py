"""
tests/unit/test_day7_final_assessment.py

Unit tests for app.services.assessment.day7_final_assessment, specifically
_derive_eligibility()'s fix for a real bug found via a live pipeline run:
minimum_requirement used to check only whether a required skill's NAME
appeared in skill_matrix, which build_skill_matrix() guarantees regardless
of whether the skill was ever actually assessed (it creates a 0.0
placeholder entry for every required skill) -- making eligibility_result
"Pass" unconditionally for any candidate, including one who never
answered a single relevant question. Confirmed live: a near-zero-scoring
interview (application_id=4) and a genuinely competent one
(application_id=6) produced byte-identical eligibility_result and
recommendation before this fix.
"""

from app.schemas.candidate import CandidateProfile, WorkExperience
from app.schemas.job import ExperienceRequirement, ExperienceRequirementType, JobRequirementProfile
from app.services.assessment.day7_final_assessment import generate_final_assessment
from app.services.interview_intelligence.models import AnswerEvaluation, InterviewPlan, SkillMatrixEntry


def _intern_jd(required_skills=("Machine Learning", "Deep Learning")) -> JobRequirementProfile:
    return JobRequirementProfile(
        job_title="AI Engineer Intern",
        required_skills=list(required_skills),
        experience_requirements=[
            ExperienceRequirement(
                description="0-1 years",
                years=0.0,
                requirement_type=ExperienceRequirementType.GENERAL,
                target=None,
                is_mandatory=True,
            ),
        ],
    )


def _plan() -> InterviewPlan:
    return InterviewPlan(
        skill_areas=[], question_types=[], question_order=[], topic_depth={}, time_allocation={}, estimated_time=90
    )


# ---------------------------------------------------------------------------
# Test 1: An Unassessed Required Skill Does Not Satisfy minimum_requirement
# ---------------------------------------------------------------------------
def test_unassessed_required_skill_does_not_satisfy_minimum_requirement():
    """
    The vacuous-truth bug isolated directly: both required skills have
    assessment_count=0 (never actually tested) -- their names appearing in
    skill_matrix must not be enough to produce a "Pass" on their own.
    """
    skill_matrix = [
        SkillMatrixEntry(skill_name="Machine Learning", proficiency_score=0.0, assessment_count=0, confidence_level="Low"),
        SkillMatrixEntry(skill_name="Deep Learning", proficiency_score=0.0, assessment_count=0, confidence_level="Low"),
    ]

    report = generate_final_assessment(
        candidate_profile=CandidateProfile(),
        job_requirements=_intern_jd(),
        interview_plan=_plan(),
        question_set=[],
        answer_evaluations=[],
        skill_matrix=skill_matrix,
        gap_analysis=[],
    )

    assert report.eligibility_result == "Fail"
    assert report.recommendation == "Decline"


# ---------------------------------------------------------------------------
# Test 2: Genuine Near-Zero Performance Results in Fail and Decline
# ---------------------------------------------------------------------------
def test_near_zero_performance_results_in_fail_and_decline():
    """
    Real evidence exists (assessment_count=1), but every score is a
    failure -- this must also result in Fail/Decline, not the old
    always-Pass regardless of interview quality.
    """
    skill_matrix = [
        SkillMatrixEntry(skill_name="Python", proficiency_score=0.0, assessment_count=1, confidence_level="Low"),
    ]
    answer_evaluations = [
        AnswerEvaluation(
            question_text="q",
            expected_knowledge_area="Python",
            question_type="Technology",
            weighted_total=0.0,
            technical_correctness=0.0,
            problem_solving=0.0,
            completeness=0.0,
            reasoning=0.0,
            communication=0.0,
            pass_fail=False,
        ),
    ]

    report = generate_final_assessment(
        candidate_profile=CandidateProfile(),
        job_requirements=_intern_jd(),
        interview_plan=_plan(),
        question_set=[],
        answer_evaluations=answer_evaluations,
        skill_matrix=skill_matrix,
        gap_analysis=[],
    )

    assert report.eligibility_result == "Fail"
    assert report.recommendation == "Decline"


# ---------------------------------------------------------------------------
# Test 3: Genuine Passing Evidence Results in Pass
# ---------------------------------------------------------------------------
def test_genuine_passing_evidence_results_in_pass():
    """Proves the fix doesn't just flip everything to Fail -- real, assessed, passing evidence still passes."""
    skill_matrix = [
        SkillMatrixEntry(skill_name="System Design", proficiency_score=70.0, assessment_count=1, confidence_level="Moderate"),
    ]

    report = generate_final_assessment(
        candidate_profile=CandidateProfile(),
        job_requirements=_intern_jd(),
        interview_plan=_plan(),
        question_set=[],
        answer_evaluations=[],
        skill_matrix=skill_matrix,
        gap_analysis=[],
    )

    assert report.eligibility_result == "Pass"


# ---------------------------------------------------------------------------
# Test 4: Entry-Level Leniency Still Works (Fix 2 confirmation -- no regression)
# ---------------------------------------------------------------------------
def test_intern_candidate_still_matches_intern_level_job():
    """An Intern-level candidate applying to an Intern-level JD must still pass the level check."""
    candidate = CandidateProfile(
        work_experience=[WorkExperience(position="Intern", start_date="2026-06", end_date="present")]
    )
    skill_matrix = [
        SkillMatrixEntry(skill_name="Python", proficiency_score=80.0, assessment_count=1, confidence_level="High"),
    ]

    report = generate_final_assessment(
        candidate_profile=candidate,
        job_requirements=_intern_jd(),
        interview_plan=_plan(),
        question_set=[],
        answer_evaluations=[],
        skill_matrix=skill_matrix,
        gap_analysis=[],
    )

    assert report.eligibility_result == "Pass"


# ---------------------------------------------------------------------------
# Test 5: Regression -- application_id=4 vs application_id=6 Now Diverge
# ---------------------------------------------------------------------------
def test_regression_application_4_vs_6_now_diverge():
    """
    Built directly from the real DB data for application_id=4 (random
    keyboard-mashing answers) and application_id=6 (genuine, thoughtful
    answers). Before this fix, both produced eligibility_result="Pass" and
    recommendation="Further Evaluation" -- byte-identical despite a ~44x
    difference in problem_solving_performance (1 vs 44) and a ~42x
    difference in communication_performance (1 vs 42). This test proves
    they now correctly diverge.
    """
    jd = _intern_jd()

    app4_skills = [
        SkillMatrixEntry(skill_name="API Design", proficiency_score=0.0, assessment_count=1, confidence_level="Low"),
        SkillMatrixEntry(skill_name="Credit Scoring Model", proficiency_score=0.0, assessment_count=1, confidence_level="Low"),
        SkillMatrixEntry(skill_name="Deep Learning", proficiency_score=0.0, assessment_count=0, confidence_level="Low"),
        SkillMatrixEntry(skill_name="Machine Learning", proficiency_score=0.0, assessment_count=0, confidence_level="Low"),
        SkillMatrixEntry(
            skill_name="Prior personal or academic project involving AI/ML",
            proficiency_score=5.0,
            assessment_count=1,
            confidence_level="Low",
        ),
        SkillMatrixEntry(skill_name="Python", proficiency_score=0.0, assessment_count=1, confidence_level="Low"),
        SkillMatrixEntry(skill_name="System Design", proficiency_score=0.0, assessment_count=1, confidence_level="Low"),
    ]
    app4_evaluations = [
        AnswerEvaluation(
            question_text="q",
            expected_knowledge_area="x",
            question_type="Technology",
            weighted_total=1.0,
            technical_correctness=0.0,
            problem_solving=1.0,
            completeness=0.0,
            reasoning=0.0,
            communication=1.0,
            pass_fail=False,
        ),
    ]

    app6_skills = [
        SkillMatrixEntry(skill_name="API Design", proficiency_score=59.0, assessment_count=1, confidence_level="Moderate"),
        SkillMatrixEntry(skill_name="Credit Scoring Model", proficiency_score=14.5, assessment_count=1, confidence_level="Low"),
        SkillMatrixEntry(skill_name="Deep Learning", proficiency_score=0.0, assessment_count=0, confidence_level="Low"),
        SkillMatrixEntry(skill_name="Machine Learning", proficiency_score=0.0, assessment_count=0, confidence_level="Low"),
        SkillMatrixEntry(
            skill_name="Prior personal or academic project involving AI/ML",
            proficiency_score=68.75,
            assessment_count=1,
            confidence_level="Moderate",
        ),
        SkillMatrixEntry(skill_name="Python", proficiency_score=47.0, assessment_count=1, confidence_level="Low"),
        SkillMatrixEntry(skill_name="System Design", proficiency_score=43.5, assessment_count=1, confidence_level="Low"),
    ]
    app6_evaluations = [
        AnswerEvaluation(
            question_text="q",
            expected_knowledge_area="x",
            question_type="Technology",
            weighted_total=44.0,
            technical_correctness=44.0,
            problem_solving=44.0,
            completeness=44.0,
            reasoning=44.0,
            communication=42.0,
            pass_fail=False,
        ),
    ]

    report_4 = generate_final_assessment(
        candidate_profile=CandidateProfile(),
        job_requirements=jd,
        interview_plan=_plan(),
        question_set=[None] * 5,
        answer_evaluations=app4_evaluations,
        skill_matrix=app4_skills,
        gap_analysis=[],
    )
    report_6 = generate_final_assessment(
        candidate_profile=CandidateProfile(),
        job_requirements=jd,
        interview_plan=_plan(),
        question_set=[None] * 5,
        answer_evaluations=app6_evaluations,
        skill_matrix=app6_skills,
        gap_analysis=[],
    )

    # Before the fix: both were eligibility_result="Pass", recommendation="Further Evaluation" -- identical.
    assert report_4.eligibility_result == "Fail"
    assert report_4.recommendation == "Decline"
    assert report_6.eligibility_result == "Pass"
    assert report_6.recommendation == "Further Evaluation"
    assert report_4.recommendation != report_6.recommendation
