"""
Bridge between the voice pipeline and Interview Intelligence.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from app.core.interview_latency import log_interview_latency
from app.core.interview_config import normalize_interview_question_count

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
_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_UTTERANCE_PUNCT_RE = re.compile(r"[^\w\s']+", re.UNICODE)
_META_UTTERANCE_REPLIES: Dict[str, str] = {
    "did you hear me": "Yes, I can hear you. Please continue with your answer.",
    "did you hear me please": "Yes, I can hear you. Please continue with your answer.",
    "can you hear me": "Yes, I can hear you. Please go ahead.",
    "can you hear me please": "Yes, I can hear you. Please go ahead.",
    "hello can you hear me": "Yes, I can hear you. Please go ahead.",
    "hello can you hear me please": "Yes, I can hear you. Please go ahead.",
    "hi can you hear me": "Yes, I can hear you. Please go ahead.",
    "hi can you hear me please": "Yes, I can hear you. Please go ahead.",
    "are you there": "Yes, I'm here. Please continue with your answer.",
    "are you there please": "Yes, I'm here. Please continue with your answer.",
    "hello are you there": "Yes, I'm here. Please continue with your answer.",
    "can we move to the next question": (
        "We're still on the current question. Please continue with your answer."
    ),
    "can we move to the next question please": (
        "We're still on the current question. Please continue with your answer."
    ),
}


def normalize_utterance(text: str) -> str:
    collapsed = _UTTERANCE_PUNCT_RE.sub(" ", (text or "").lower())
    return re.sub(r"\s+", " ", collapsed).strip()


def match_meta_utterance(text: str) -> Optional[str]:
    """Return a spoken repair reply for a narrow set of meta utterances, else None."""
    normalized = normalize_utterance(text)
    if not normalized:
        return None
    return _META_UTTERANCE_REPLIES.get(normalized)


def classify_candidate_turn(
    *,
    intended_question: Optional[str],
    current_question: Optional[str],
) -> str:
    """Classify a transcript against the question it was captured for.

    ``evaluate`` — still the unanswered current question.
    ``stale`` — that question has already advanced.
    ``no_pending_question`` — interview has no current question to score.
    """
    if current_question is None:
        return "stale" if intended_question else "no_pending_question"
    if intended_question is None or intended_question == current_question:
        return "evaluate"
    return "stale"


def derive_question_turn_budget(
    questions: List[Question],
    configured_count: Optional[int] = None,
) -> int:
    """Interview-turn budget is the recruiter-configured question count.

    Each evaluated interviewer question (planned, CV verification, or adaptive
    follow-up) consumes one turn. Follow-ups do not extend the interview past
    this count. If no positive configured count is available, fall back to the
    generated question list length so existing jobs keep working.
    """
    if configured_count is not None:
        try:
            count = int(configured_count)
        except (TypeError, ValueError):
            count = 0
        if count > 0:
            return normalize_interview_question_count(count)
    return max(len(questions), 1)


class InterviewBridge(ABC):
    @abstractmethod
    async def process_candidate_response(
        self,
        text: str,
        session_id: str,
        question_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_next_question(self, session_id: str) -> Optional[str]:
        pass

    @abstractmethod
    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        pass

    async def claim_opening(self, session_id: str, owner_id: str = "unknown") -> Dict[str, Any]:
        question = await self.get_next_question(session_id)
        return {
            "action": "greet" if question else "completed",
            "question": question,
            "completed": question is None,
            "allow_opening_speech": bool(question),
        }

    async def aclose(self) -> None:
        return None


class MockInterviewBridge(InterviewBridge):
    async def process_candidate_response(
        self,
        text: str,
        session_id: str,
        question_text: Optional[str] = None,
    ) -> Dict[str, Any]:
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
    terminated: bool = False
    question_turn_budget: int = 0
    completed_turns: int = 0
    follow_up_turns: int = 0
    opening_delivered: bool = False
    agent_owner_id: Optional[str] = None

    @property
    def remaining_turns(self) -> int:
        inflight = 1 if self.current is not None else 0
        return max(self.question_turn_budget - self.completed_turns - inflight, 0)


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
        self._session_locks: Dict[str, asyncio.Lock] = {}

    def get_runtime(self, session_id: str) -> Optional[InterviewRuntime]:
        return self._runtimes.get(session_id)

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    def release_session_lock(self, session_id: str) -> None:
        self._session_locks.pop(session_id, None)

    def _current_question_text(self, session_id: str) -> Optional[str]:
        runtime = self._runtimes.get(session_id)
        if runtime is None or runtime.current is None:
            return None
        return runtime.current.question_text

    def _ignored_response(
        self, session_id: str, text: str, reason: str
    ) -> Dict[str, Any]:
        runtime = self._runtimes.get(session_id)
        return {
            "status": "ignored",
            "reason": reason,
            "text": text,
            "completed": bool(runtime.completed) if runtime is not None else False,
            "next_question": self._current_question_text(session_id),
        }

    def initialize(
        self,
        session_id: str,
        *,
        application_id: int,
        candidate_id: int,
        job_posting_id: int,
        candidate_profile: Dict[str, Any],
        job_profile_snapshot: Dict[str, Any],
        interview_question_count: Optional[int] = None,
    ) -> InterviewRuntime:
        """Build plan, questions, CV verification, and adaptive controller from Application data."""
        existing = self._runtimes.get(session_id)
        if existing is not None:
            if existing.terminated:
                raise RuntimeError(
                    f"Interview session {session_id} has already ended and cannot be restarted"
                )
            logger.info(
                "Reusing existing interview intelligence for session %s "
                "(budget=%s completed_turns=%s completed=%s)",
                session_id,
                existing.question_turn_budget,
                existing.completed_turns,
                existing.completed,
            )
            return existing

        candidate = CandidateProfile.model_validate(candidate_profile)
        job = JobRequirementProfile.model_validate(job_profile_snapshot)
        plan = generate_interview_plan(job, candidate)
        questions = generate_questions(
            job,
            candidate,
            plan,
            target_count=normalize_interview_question_count(interview_question_count)
            if interview_question_count is not None
            else None,
        )
        if not questions:
            raise RuntimeError("Question engine produced no questions for this application")

        cv_claims = self._assessment.verify_cv_claims(candidate)
        candidate_level = derive_experience_level(candidate)
        budget = derive_question_turn_budget(
            questions, configured_count=interview_question_count
        )
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
            question_turn_budget=budget,
        )
        self._runtimes[session_id] = runtime
        logger.info(
            "Initialized interview intelligence for session %s "
            "(application %s, budget=%d planned questions=%d)",
            session_id,
            application_id,
            budget,
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

    def _budget_exhausted(self, runtime: InterviewRuntime) -> bool:
        return runtime.completed_turns >= runtime.question_turn_budget

    def _select_next_question(
        self, runtime: InterviewRuntime, decision: Any
    ) -> Optional[Question]:
        if self._budget_exhausted(runtime):
            return None
        unused = [question for question in runtime.questions if question not in runtime.asked]
        if getattr(decision, "follow_up_required", "No") == "Yes" and runtime.cv_follow_ups:
            runtime.follow_up_turns += 1
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

    async def _get_next_question_locked(self, session_id: str) -> Optional[str]:
        runtime = self._require_runtime(session_id)
        if runtime.completed or runtime.terminated:
            return None
        if runtime.current is not None:
            return runtime.current.question_text

        if self._budget_exhausted(runtime):
            runtime.pending_next = None
            runtime.completed = True
            return None

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

    async def get_next_question(self, session_id: str) -> Optional[str]:
        async with self._session_lock(session_id):
            return await self._get_next_question_locked(session_id)

    async def claim_opening(self, session_id: str, owner_id: str = "unknown") -> Dict[str, Any]:
        async with self._session_lock(session_id):
            runtime = self._require_runtime(session_id)
            if runtime.terminated or runtime.completed:
                return {
                    "action": "completed",
                    "question": None,
                    "completed": True,
                    "allow_opening_speech": False,
                    "question_turn_budget": runtime.question_turn_budget,
                    "completed_turns": runtime.completed_turns,
                }
            if runtime.opening_delivered:
                current_text = (
                    runtime.current.question_text if runtime.current is not None else None
                )
                return {
                    "action": "stand_down",
                    "question": current_text,
                    "completed": False,
                    "allow_opening_speech": False,
                    "question_turn_budget": runtime.question_turn_budget,
                    "completed_turns": runtime.completed_turns,
                }
            runtime.agent_owner_id = owner_id
            runtime.opening_delivered = True
            question = await self._get_next_question_locked(session_id)
            return {
                "action": "greet",
                "question": question,
                "completed": runtime.completed,
                "allow_opening_speech": bool(question),
                "question_turn_budget": runtime.question_turn_budget,
                "completed_turns": runtime.completed_turns,
            }

    async def _process_candidate_response_locked(
        self,
        text: str,
        session_id: str,
        intended_question: Optional[str] = None,
    ) -> Dict[str, Any]:
        runtime = self._require_runtime(session_id)
        meta_reply = match_meta_utterance(text)
        if meta_reply:
            return {
                "status": "acknowledged",
                "meta": True,
                "text": text,
                "spoken_reply": meta_reply,
                "completed": runtime.completed,
                "next_question": (
                    runtime.current.question_text if runtime.current is not None else None
                ),
            }

        if runtime.terminated:
            return self._ignored_response(session_id, text, "terminated")
        if runtime.completed or runtime.current is None:
            return self._ignored_response(
                session_id,
                text,
                "completed" if runtime.completed else "no_pending_question",
            )

        current_text = runtime.current.question_text
        turn_class = classify_candidate_turn(
            intended_question=intended_question,
            current_question=current_text,
        )
        if turn_class != "evaluate":
            log_interview_latency(
                session_id,
                "stale_transcript",
                reason=turn_class,
            )
            return self._ignored_response(session_id, text, "stale_transcript")

        question = runtime.current
        response_started = time.perf_counter()
        log_interview_latency(session_id, "evaluation_start")
        evaluations = await asyncio.to_thread(
            self._assessment.assess_answers, [question], [text]
        )
        if not evaluations:
            raise RuntimeError("Assessment service returned no answer evaluation")
        evaluation = evaluations[0]
        log_interview_latency(
            session_id,
            "evaluation_done",
            (time.perf_counter() - response_started) * 1000.0,
        )

        log_interview_latency(session_id, "adaptive_start")
        decision_started = time.perf_counter()
        decision = decide_next_step(
            current_difficulty=question.baseline_difficulty,
            previous_question_type=question.question_type,
            answer_evaluation={"weighted_total": evaluation.weighted_total},
            controller=runtime.controller,
        )
        log_interview_latency(
            session_id,
            "adaptive_done",
            duration_ms=f"{(time.perf_counter() - decision_started) * 1000.0:.0f}",
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
        runtime.completed_turns += 1
        runtime.pending_next = self._select_next_question(runtime, decision)
        if runtime.pending_next is None:
            runtime.completed = True

        next_question = await self._get_next_question_locked(session_id)
        log_interview_latency(
            session_id,
            "next_question_selected",
            (time.perf_counter() - response_started) * 1000.0,
            has_question=bool(next_question),
            completed=runtime.completed,
        )
        return {
            "status": "processed",
            "text": text,
            "evaluation": _evaluation_payload(evaluation),
            "decision": runtime.last_decision,
            "completed": runtime.completed,
            "next_question": next_question,
            "question_turn_budget": runtime.question_turn_budget,
            "completed_turns": runtime.completed_turns,
            "remaining_turns": runtime.remaining_turns,
        }

    async def process_candidate_response(
        self,
        text: str,
        session_id: str,
        question_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        runtime = self._runtimes.get(session_id)
        intended_question = question_text
        if intended_question is None and runtime is not None and runtime.current is not None:
            intended_question = runtime.current.question_text
        lock = self._session_lock(session_id)
        queued = lock.locked()
        if queued:
            log_interview_latency(
                session_id,
                "transcript_queued",
                has_intended=bool(intended_question),
            )
        async with lock:
            result = await self._process_candidate_response_locked(
                text, session_id, intended_question=intended_question
            )
            if queued and result.get("status") == "processed":
                log_interview_latency(session_id, "queued_transcript_processed")
            return result

    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        result = await self.process_candidate_response(text, session_id)
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, dict):
            raise RuntimeError("Interview intelligence returned no answer evaluation")
        return evaluation

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

    def mark_terminated(self, session_id: str) -> None:
        runtime = self._runtimes.get(session_id)
        if runtime is None:
            return
        runtime.terminated = True


class HttpInterviewBridge(InterviewBridge):
    """Worker-side adapter: the LiveKit agent process talks to VoiceInterviewService over HTTP.

    The AsyncClient is created on the job's running event loop and is never shared
    with another loop or another InterviewAgent instance.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base_url = (base_url or _BACKEND_BASE_URL).rstrip("/")
        self._session_locks: Dict[str, asyncio.Lock] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
        self._http_loop: Optional[asyncio.AbstractEventLoop] = None

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    def release_session_lock(self, session_id: str) -> None:
        self._session_locks.pop(session_id, None)

    def peek_http_client(self) -> Optional[httpx.AsyncClient]:
        client = self._http_client
        if client is None or client.is_closed:
            return None
        return client

    def _detach_foreign_loop_client(self, loop: asyncio.AbstractEventLoop) -> None:
        """Drop a client bound to another loop without awaiting it on this loop."""
        if self._http_loop is None or self._http_loop is loop:
            return
        logger.warning(
            "HttpInterviewBridge refusing to reuse AsyncClient across event loops"
        )
        self._http_client = None
        self._http_loop = None
        self._session_locks = {}

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Create or reuse an AsyncClient for *this* running event loop only."""
        loop = asyncio.get_running_loop()
        self._detach_foreign_loop_client(loop)
        client = self._http_client
        if client is not None and not client.is_closed and self._http_loop is loop:
            return client
        client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
        self._http_client = client
        self._http_loop = loop
        log_interview_latency("-", "http_client_created")
        return client

    async def aclose(self) -> None:
        client = self._http_client
        loop = self._http_loop
        self._http_client = None
        self._http_loop = None
        self._session_locks = {}
        if client is None or client.is_closed:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is not None and running is not None and loop is not running:
            return
        await client.aclose()

    async def get_next_question(self, session_id: str) -> Optional[str]:
        url = f"{self._base_url}/voice/sessions/{session_id}/next-question"
        client = await self._ensure_client()
        response = await client.get(url, timeout=30.0)
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                f"Failed to get next question for session {session_id}: HTTP {response.status_code}"
            )
        payload = response.json()
        question = payload.get("question")
        if question is None:
            return None
        return str(question)

    async def claim_opening(self, session_id: str, owner_id: str = "unknown") -> Dict[str, Any]:
        url = f"{self._base_url}/voice/sessions/{session_id}/next-question"
        client = await self._ensure_client()
        response = await client.get(
            url,
            params={"claim_opening": "true", "owner_id": owner_id},
            timeout=30.0,
        )
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                f"Failed to claim opening for session {session_id}: HTTP {response.status_code}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Interview intelligence returned an invalid opening payload")
        question = payload.get("question")
        allow = bool(payload.get("allow_opening_speech"))
        completed = bool(payload.get("completed"))
        action = payload.get("action") or (
            "greet" if allow else ("completed" if completed else "stand_down")
        )
        return {
            "action": str(action),
            "question": None if question is None else str(question),
            "completed": completed,
            "allow_opening_speech": allow,
            "question_turn_budget": payload.get("question_turn_budget"),
            "completed_turns": payload.get("completed_turns"),
        }

    async def end_session(self, session_id: str) -> None:
        url = f"{self._base_url}/voice/sessions/{session_id}/end"
        client = await self._ensure_client()
        response = await client.post(url, timeout=10.0)
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                f"Failed to end interview session {session_id}: HTTP {response.status_code}"
            )

    async def process_candidate_response(
        self,
        text: str,
        session_id: str,
        question_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        lock = self._session_lock(session_id)
        queued = lock.locked()
        if queued:
            log_interview_latency(
                session_id,
                "transcript_queued",
                has_intended=bool(question_text),
            )
        async with lock:
            log_interview_latency(session_id, "response_start")
            started = time.perf_counter()
            url = f"{self._base_url}/voice/sessions/{session_id}/response"
            client = await self._ensure_client()
            payload_in: Dict[str, Any] = {"text": text}
            if question_text:
                payload_in["question_text"] = question_text
            response = await client.post(url, json=payload_in, timeout=120.0)
            if not (200 <= response.status_code < 300):
                raise RuntimeError(
                    f"Failed to process candidate response for session {session_id}: "
                    f"HTTP {response.status_code}"
                )
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Interview intelligence returned an invalid response payload")
            log_interview_latency(
                session_id,
                "response_done",
                (time.perf_counter() - started) * 1000.0,
                status=payload.get("status"),
                response_total_ms=f"{(time.perf_counter() - started) * 1000.0:.0f}",
            )
            if queued and payload.get("status") == "processed":
                log_interview_latency(session_id, "queued_transcript_processed")
            return payload

    async def evaluate_answer(self, text: str, question_id: str, session_id: str) -> Dict[str, Any]:
        result = await self.process_candidate_response(text, session_id)
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, dict):
            raise RuntimeError("Interview intelligence returned no answer evaluation")
        return evaluation
