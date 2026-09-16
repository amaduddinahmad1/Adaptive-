from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Tuple

from app.services.interview_intelligence.day1_interview_plan import generate_interview_plan
from app.services.interview_intelligence.day2_question_generation import generate_questions
from app.services.interview_intelligence.day3_cv_verification import verify_cv_claims
from app.services.assessment.day5_answer_evaluation import evaluate_answer
from app.services.assessment.day6_skill_gap_analysis import analyze_cv_interview_gap, build_skill_matrix
from app.services.assessment.day7_final_assessment import generate_final_assessment
from app.services.interview_intelligence.models import (
    AnswerEvaluation,
    FinalAssessmentReport,
    GapAnalysisEntry,
    InterviewPlan,
    Question,
)
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile

logger = logging.getLogger(__name__)


class AssessmentService:
    """High-level orchestration wrapper for the interview assessment workflow.

    This keeps the system focused on the assessment domain and avoids unrelated
    application concerns outside the recruitment intelligence use case.
    """

    def __init__(self) -> None:
        pass

    def generate_interview_questions(self, job: JobRequirementProfile, candidate: CandidateProfile) -> List[Question]:
        plan = generate_interview_plan(job, candidate)
        return generate_questions(job, candidate, plan)

    def verify_cv_claims(self, candidate: CandidateProfile):
        return verify_cv_claims(candidate)

    def assess_answers(self, question_set: Iterable[Question], answers: Iterable[str]) -> List[AnswerEvaluation]:
        results: List[AnswerEvaluation] = []
        for question, answer in zip(question_set, answers):
            results.append(evaluate_answer(question, answer))
        return results

    def build_report_artifacts(
        self,
        candidate: CandidateProfile,
        job: JobRequirementProfile,
        question_set: List[Question],
        answer_evaluations: List[AnswerEvaluation],
        cv_claims: list[dict] | None = None,
        unmatched_cv_claims: List[str] | None = None,
        interview_plan: Optional[InterviewPlan] = None,
    ) -> Tuple[FinalAssessmentReport, List[GapAnalysisEntry]]:
        """Build the Day 7 report and Day 6 gap analysis from supplied interview evidence."""
        plan = interview_plan or generate_interview_plan(job, candidate)
        skill_matrix = build_skill_matrix(answer_evaluations, job.required_skills)
        gap_analysis = analyze_cv_interview_gap(cv_claims or [], skill_matrix)
        report = generate_final_assessment(
            candidate_profile=candidate,
            job_requirements=job,
            interview_plan=plan,
            question_set=question_set,
            answer_evaluations=answer_evaluations,
            skill_matrix=skill_matrix,
            gap_analysis=gap_analysis,
            unmatched_cv_claims=unmatched_cv_claims,
        )
        return report, gap_analysis

    def build_report(
        self,
        candidate: CandidateProfile,
        job: JobRequirementProfile,
        question_set: List[Question],
        answer_evaluations: List[AnswerEvaluation],
        cv_claims: list[dict] | None = None,
        unmatched_cv_claims: List[str] | None = None,
        interview_plan: Optional[InterviewPlan] = None,
    ) -> FinalAssessmentReport:
        report, _gap_analysis = self.build_report_artifacts(
            candidate,
            job,
            question_set,
            answer_evaluations,
            cv_claims=cv_claims,
            unmatched_cv_claims=unmatched_cv_claims,
            interview_plan=interview_plan,
        )
        return report

