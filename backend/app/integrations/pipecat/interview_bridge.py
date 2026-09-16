"""
Bridge between the voice pipeline and Interview Intelligence.
"""
from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile
from app.services.assessment.assessment_service import AssessmentService
from app.services.assessment.day6_skill_gap_analysis import build_cv_claim_evidence
from app.services.interview_intelligence.day1_interview_plan import generate_interview_plan
from app.services.interview_intelligence.day2_question_generation import generate_questions
from app.services.interview_intelligence.day4_adaptive_interview import (
    AdaptiveInterviewController,
    decide_next_step,
)
from app.services.interview_intelligence.models import (
    AnswerEvaluation,
    CVClaim,
    FinalAssessmentReport,
    GapAnalysisEntry,
    InterviewPlan,
    Question,
    derive_experience_level,
)
from app.services.interview_intelligence.question_coverage import select_technology_areas

logger = logging.getLogger(__name__)

_BACKEND_BASE_URL = os.getenv("BACKEND_API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")


class InterviewBridge(ABC):
    @abstractmethod
    async def process_candidate_response(self, text: str, session_id: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_next_question(self, session_id: str) -> Optional[str]:
        pass

    @abstractmethod
    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        pass


class MockInterviewBridge(InterviewBridge):
    async def process_candidate_response(self, text: str, session_id: str) -> Dict[str, Any]:
        return {"status": "processed", "text": text}

    async def get_next_question(self, session_id: str) -> Optional[str]:
        return "Could you tell me about yourself?"

    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        return {"score": 0.8, "feedback": "Good response"}


@dataclass
class InterviewRuntime:
    """In-memory interview/assessment state retained for Phase 2B."""

    application_id: int
    candidate_id: int
    job_posting_id: int
    candidate: CandidateProfile
    job: JobRequirementProfile
    plan: InterviewPlan
    questions: List[Question]
    cv_claims: List[CVClaim]
    cv_follow_ups: List[Question]
    controller: AdaptiveInterviewController
    asked: List[Question] = field(default_factory=list)
    current: Optional[Question] = None
    pending_next: Optional[Question] = None
    evaluations: List[AnswerEvaluation] = field(default_factory=list)
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    last_decision: Optional[Dict[str, Any]] = None
    completed: bool = False


def _evaluation_payload(evaluation: AnswerEvaluation) -> Dict[str, Any]:
    return {
        "question_text": evaluation.question_text,
        "expected_knowledge_area": evaluation.expected_knowledge_area,
        "question_type": evaluation.question_type,
        "weighted_total": evaluation.weighted_total,
        "technical_correctness": evaluation.technical_correctness,
        "problem_solving": evaluation.problem_solving,
        "completeness": evaluation.completeness,
        "reasoning": evaluation.reasoning,
        "communication": evaluation.communication,
        "pass_fail": evaluation.pass_fail,
        "criterion_scores": evaluation.criterion_scores,
        "skills_covered": evaluation.skills_covered,
        "recommendation_note": evaluation.recommendation_note,
    }


def _cv_follow_up_questions(claims: List[CVClaim], difficulty: str) -> List[Question]:
    follow_ups: List[Question] = []
    for claim in claims:
        for text in claim.claim_questions:
            cleaned = (text or "").strip()
            if not cleaned:
                continue
            follow_ups.append(
                Question(
                    question_text=cleaned,
                    expected_knowledge_area="CV Verification",
                    question_type="Project",
                    baseline_difficulty=difficulty,  # type: ignore[arg-type]
                    skills_covered=[],
                )
            )
    return follow_ups


class InterviewIntelligenceBridge(InterviewBridge):
    """Active voice-interview path: real Question Engine, evaluation, and adaptive control."""

    def __init__(self, assessment_service: Optional[AssessmentService] = None) -> None:
        self._assessment = assessment_service or AssessmentService()
        self._runtimes: Dict[str, InterviewRuntime] = {}

    def get_runtime(self, session_id: str) -> Optional[InterviewRuntime]:
        return self._runtimes.get(session_id)

    def initialize(
        self,
        session_id: str,
        *,
        application_id: int,
        candidate_id: int,
        job_posting_id: int,
        candidate_profile: Dict[str, Any],
        job_profile_snapshot: Dict[str, Any],
    ) -> InterviewRuntime:
        """Build plan, questions, CV verification, and adaptive controller from Application data."""
        candidate = CandidateProfile.model_validate(candidate_profile)
        job = JobRequirementProfile.model_validate(job_profile_snapshot)
        plan = generate_interview_plan(job, candidate)
        questions = generate_questions(job, candidate, plan)
        if not questions:
            raise RuntimeError("Question engine produced no questions for this application")

        cv_claims = self._assessment.verify_cv_claims(candidate)
        candidate_level = derive_experience_level(candidate)
        runtime = InterviewRuntime(
            application_id=application_id,
            candidate_id=candidate_id,
            job_posting_id=job_posting_id,
            candidate=candidate,
            job=job,
            plan=plan,
            questions=questions,
            cv_claims=cv_claims,
            cv_follow_ups=_cv_follow_up_questions(cv_claims, candidate_level),
            controller=AdaptiveInterviewController(candidate_level=candidate_level),
        )
        self._runtimes[session_id] = runtime
        logger.info(
            "Initialized interview intelligence for session %s (application %s, %d questions)",
            session_id,
            application_id,
            len(questions),
        )
        return runtime

    def _require_runtime(self, session_id: str) -> InterviewRuntime:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            raise RuntimeError(
                f"Interview intelligence is not initialized for session {session_id}"
            )
        return runtime

    def _select_next_question(
        self, runtime: InterviewRuntime, decision: Any
    ) -> Optional[Question]:
        unused = [question for question in runtime.questions if question not in runtime.asked]
        if getattr(decision, "follow_up_required", "No") == "Yes" and runtime.cv_follow_ups:
            return runtime.cv_follow_ups.pop(0)

        typed = [
            question
            for question in unused
            if question.question_type == decision.next_question_type
        ]
        if decision.next_question_type == "Technology":
            coverage_areas = {
                area.casefold()
                for area in select_technology_areas(runtime.job, runtime.candidate)
            }
            covered = {
                skill.casefold()
                for question in runtime.asked
                for skill in question.skills_covered
            }
            uncovered = [
                question
                for question in typed
                if any(
                    skill.casefold() in coverage_areas and skill.casefold() not in covered
                    for skill in question.skills_covered
                )
            ]
            if uncovered:
                return uncovered[0]
        if typed:
            return typed[0]
        if unused:
            return unused[0]
        return None

    async def get_next_question(self, session_id: str) -> Optional[str]:
        runtime = self._require_runtime(session_id)
        if runtime.completed:
            return None
        if runtime.current is not None:
            return runtime.current.question_text

        if runtime.pending_next is not None:
            runtime.current = runtime.pending_next
            runtime.pending_next = None
            return runtime.current.question_text

        unused = [question for question in runtime.questions if question not in runtime.asked]
        if not unused:
            runtime.completed = True
            return None
        runtime.current = unused[0]
        return runtime.current.question_text

    async def process_candidate_response(self, text: str, session_id: str) -> Dict[str, Any]:
        runtime = self._require_runtime(session_id)
        if runtime.current is None:
            raise RuntimeError(
                f"No question is awaiting an answer for session {session_id}"
            )

        question = runtime.current
        evaluations = await asyncio.to_thread(
            self._assessment.assess_answers, [question], [text]
        )
        if not evaluations:
            raise RuntimeError("Assessment service returned no answer evaluation")
        evaluation = evaluations[0]

        decision = decide_next_step(
            current_difficulty=question.baseline_difficulty,
            previous_question_type=question.question_type,
            answer_evaluation={"weighted_total": evaluation.weighted_total},
            controller=runtime.controller,
        )

        runtime.evaluations.append(evaluation)
        runtime.asked.append(question)
        runtime.transcript.append(
            {
                "question": question.question_text,
                "question_type": question.question_type,
                "answer": text,
                "evaluation": _evaluation_payload(evaluation),
            }
        )
        runtime.last_decision = asdict(decision)
        runtime.current = None
        runtime.pending_next = self._select_next_question(runtime, decision)
        if runtime.pending_next is None:
            runtime.completed = True

        return {
            "status": "processed",
            "text": text,
            "evaluation": _evaluation_payload(evaluation),
            "decision": runtime.last_decision,
            "completed": runtime.completed,
        }

    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        result = await self.process_candidate_response(text, session_id)
        return result["evaluation"]

    def build_completion_assessment(
        self, session_id: str
    ) -> Optional[tuple[FinalAssessmentReport, List[GapAnalysisEntry]]]:
        """Build Day 6/Day 7 artifacts from retained runtime evidence.

        Returns None when there are no genuine answer evaluations. Does not
        clear InterviewRuntime.
        """
        runtime = self.get_runtime(session_id)
        if runtime is None or not runtime.evaluations:
            return None

        evidence = build_cv_claim_evidence(runtime.candidate, runtime.cv_claims)
        return self._assessment.build_report_artifacts(
            runtime.candidate,
            runtime.job,
            list(runtime.asked),
            list(runtime.evaluations),
            cv_claims=evidence.matched_claims,
            unmatched_cv_claims=evidence.unmatched_claims,
            interview_plan=runtime.plan,
        )


class HttpInterviewBridge(InterviewBridge):
    """Worker-side adapter: the LiveKit agent process talks to VoiceInterviewService over HTTP."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url = (base_url or _BACKEND_BASE_URL).rstrip("/")

    async def get_next_question(self, session_id: str) -> Optional[str]:
        url = f"{self._base_url}/voice/sessions/{session_id}/next-question"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                f"Failed to get next question for session {session_id}: HTTP {response.status_code}"
            )
        payload = response.json()
        question = payload.get("question")
        if question is None:
            return None
        return str(question)

    async def process_candidate_response(self, text: str, session_id: str) -> Dict[str, Any]:
        url = f"{self._base_url}/voice/sessions/{session_id}/response"
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json={"text": text})
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                f"Failed to process candidate response for session {session_id}: "
                f"HTTP {response.status_code}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Interview intelligence returned an invalid response payload")
        return payload

    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        result = await self.process_candidate_response(text, session_id)
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, dict):
            raise RuntimeError("Interview intelligence returned no answer evaluation")
        return evaluation
