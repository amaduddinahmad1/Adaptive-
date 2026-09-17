"""Regression tests for single-agent ownership, loop-safe HTTP, and question budget."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit.agents import ModelSettings

from app.agents.interview_agent import InterviewAgent, _INTERVIEW_COMPLETE_MESSAGE
from app.agents.room_ownership import (
    owner_job_id,
    release_room,
    reset_room_ownership_for_tests,
    room_already_has_interview_agent,
    try_claim_room,
)
from app.agents.worker import handle_interview_job_request
from app.integrations.pipecat.interview_bridge import (
    InterviewIntelligenceBridge,
    derive_question_turn_budget,
)
from app.models.application import Application
from app.schemas.voice_session import InterviewStatus
from app.services.interview_intelligence.models import Question
from tests.db_helpers import seed_application
from tests.test_interview_intelligence_voice import (
    _expected_questions,
    _patch_assess_answers,
)
from tests.test_interview_turn_taking import _started_session, _user_chat


class _FakeJobRequest:
    def __init__(self, room_name: str, job_id: str) -> None:
        self.id = job_id
        self.room = SimpleNamespace(name=room_name)
        self.accepted = False
        self.rejected = False

    async def accept(self, **_kwargs):
        self.accepted = True

    async def reject(self, **_kwargs):
        self.rejected = True


class _AwaitableSpeechHandle:
    def __await__(self):
        async def _inner():
            return self

        return _inner().__await__()


@pytest.fixture(autouse=True)
def _reset_room_owners():
    reset_room_ownership_for_tests()
    yield
    reset_room_ownership_for_tests()


def test_same_room_cannot_have_two_active_owners():
    assert try_claim_room("interview-sess-1", "job-a") is True
    assert try_claim_room("interview-sess-1", "job-b") is False
    assert owner_job_id("interview-sess-1") == "job-a"
    release_room("interview-sess-1", "job-b")
    assert owner_job_id("interview-sess-1") == "job-a"
    release_room("interview-sess-1", "job-a")
    assert owner_job_id("interview-sess-1") is None
    assert try_claim_room("interview-sess-1", "job-b") is True


def test_room_detects_existing_agent_participant():
    room = SimpleNamespace(
        remote_participants={
            "p1": SimpleNamespace(identity="candidate-12"),
            "p2": SimpleNamespace(identity="agent-job-1"),
        }
    )
    assert room_already_has_interview_agent(room, "agent-job-2") is True
    assert room_already_has_interview_agent(room, "agent-job-1") is False


@pytest.mark.asyncio
async def test_duplicate_job_request_is_rejected_for_owned_room():
    first = _FakeJobRequest("interview-abc", "job-1")
    second = _FakeJobRequest("interview-abc", "job-2")
    await handle_interview_job_request(first)
    await handle_interview_job_request(second)
    assert first.accepted is True
    assert first.rejected is False
    assert second.accepted is False
    assert second.rejected is True
    assert owner_job_id("interview-abc") == "job-1"


@pytest.mark.asyncio
async def test_interview_starts_with_job_configured_question_budget(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    configured = eligible_application.job_posting.interview_question_count
    assert configured == 7
    assert runtime.question_turn_budget == configured
    assert runtime.question_turn_budget == derive_question_turn_budget(
        runtime.questions,
        configured_count=configured,
    )
    assert runtime.question_turn_budget > 0
    assert runtime.completed_turns == 0
    assert session.question_turn_budget == runtime.question_turn_budget
    assert session.completed_turns == 0


@pytest.mark.asyncio
async def test_completed_turn_increments_budget_counter(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    with _patch_assess_answers():
        result = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    assert runtime.completed_turns == 1
    assert result["completed_turns"] == 1
    assert result["question_turn_budget"] == runtime.question_turn_budget
    inflight = 1 if runtime.current is not None else 0
    assert runtime.remaining_turns == runtime.question_turn_budget - 1 - inflight


@pytest.mark.asyncio
async def test_adaptive_follow_up_stays_within_budget(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    runtime.cv_follow_ups = [
        Question(
            question_text="Can you verify that FastAPI claim from your CV?",
            expected_knowledge_area="CV Verification",
            question_type="Project",
            baseline_difficulty="Junior",
            skills_covered=[],
        )
    ]
    original_budget = runtime.question_turn_budget
    with _patch_assess_answers(weighted_total=40.0):
        result = await service.process_candidate_response(
            session.session_id, "I am not sure about that implementation detail."
        )
    assert runtime.follow_up_turns == 1
    assert runtime.completed_turns == 1
    assert runtime.question_turn_budget == original_budget
    assert result["next_question"] == "Can you verify that FastAPI claim from your CV?"
    assert runtime.completed is False


@pytest.mark.asyncio
async def test_budget_exhaustion_prevents_another_question(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    runtime.question_turn_budget = 1
    session.question_turn_budget = 1
    unused_before = [question for question in runtime.questions if question not in runtime.asked]
    assert len(unused_before) > 1
    with _patch_assess_answers():
        result = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    assert result["status"] == "processed"
    assert result["evaluation"]["weighted_total"] == 72.0
    assert runtime.completed_turns == 1
    assert result["next_question"] is None
    assert result["completed"] is True
    assert runtime.completed is True
    assert await service.get_next_question(session.session_id) is None


@pytest.mark.asyncio
async def test_selector_none_still_completes_before_budget_exhausted(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime.question_turn_budget > 1
    with _patch_assess_answers(), patch.object(
        InterviewIntelligenceBridge,
        "_select_next_question",
        return_value=None,
    ):
        result = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    assert result["completed"] is True
    assert result["next_question"] is None
    assert runtime.completed is True
    assert runtime.completed_turns == 1
    assert runtime.completed_turns < runtime.question_turn_budget


@pytest.mark.asyncio
async def test_duplicate_initialize_does_not_reset_budget_or_runtime(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    first_question = runtime.current.question_text
    with _patch_assess_answers():
        await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    asked = list(runtime.asked)
    budget = runtime.question_turn_budget
    turns = runtime.completed_turns
    current = runtime.current
    reused = service.bridge.initialize(
        session.session_id,
        application_id=eligible_application.id,
        candidate_id=eligible_application.candidate_id,
        job_posting_id=eligible_application.job_posting_id,
        candidate_profile=eligible_application.candidate_profile,
        job_profile_snapshot=eligible_application.job_profile_snapshot,
    )
    assert reused is runtime
    assert runtime.question_turn_budget == budget
    assert runtime.completed_turns == turns
    assert runtime.asked == asked
    assert runtime.current is current
    assert runtime.current is None or runtime.current.question_text != first_question


@pytest.mark.asyncio
async def test_duplicate_opening_claim_does_not_restart_greeting_or_question(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    first = await service.claim_agent_opening(session.session_id, "job-1")
    current = runtime.current.question_text
    second = await service.claim_agent_opening(session.session_id, "job-2")
    assert first["allow_opening_speech"] is True
    assert first["action"] == "greet"
    assert first["question"] == current
    assert second["allow_opening_speech"] is False
    assert second["action"] == "stand_down"
    assert second["question"] == current
    assert runtime.opening_delivered is True
    assert runtime.agent_owner_id == "job-1"
    assert runtime.completed_turns == 0


@pytest.mark.asyncio
async def test_duplicate_agent_on_enter_does_not_start_tts(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    await service.claim_agent_opening(session.session_id, "job-1")
    current = service.bridge.get_runtime(session.session_id).current.question_text

    class _Bridge:
        async def claim_opening(self, session_id: str, owner_id: str = "unknown"):
            return await service.bridge.claim_opening(session_id, owner_id)

        async def get_next_question(self, session_id: str):
            return await service.bridge.get_next_question(session_id)

    agent = InterviewAgent(bridge=_Bridge())
    live_session = MagicMock()
    live_session.say.return_value = _AwaitableSpeechHandle()
    live_session.on = MagicMock()
    agent._activity = SimpleNamespace(session=live_session)
    with patch(
        "app.agents.interview_agent._interview_session_id",
        return_value=session.session_id,
    ), patch(
        "app.agents.interview_agent._interview_job_id",
        return_value="job-2",
    ):
        await agent.on_enter()
    live_session.say.assert_not_called()
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime.current.question_text == current
    assert runtime.agent_owner_id == "job-1"


@pytest.mark.asyncio
async def test_new_interview_still_speaks_greeting_and_first_question(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    expected = _expected_questions(eligible_application)[0].question_text

    class _Bridge:
        async def claim_opening(self, session_id: str, owner_id: str = "unknown"):
            return await service.bridge.claim_opening(session_id, owner_id)

    agent = InterviewAgent(bridge=_Bridge())
    live_session = MagicMock()
    live_session.say.return_value = _AwaitableSpeechHandle()
    live_session.on = MagicMock()
    agent._activity = SimpleNamespace(session=live_session)
    with patch(
        "app.agents.interview_agent._interview_session_id",
        return_value=session.session_id,
    ), patch(
        "app.agents.interview_agent._interview_job_id",
        return_value="job-new",
    ):
        await agent.on_enter()
    live_session.say.assert_called_once()
    spoken = live_session.say.call_args.args[0]
    assert "Hello, thanks for joining" in spoken
    assert expected in spoken


@pytest.mark.asyncio
async def test_completed_session_cannot_be_restarted_by_duplicate_job(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    with _patch_assess_answers():
        await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    runtime = service.bridge.get_runtime(session.session_id)
    turns = runtime.completed_turns
    budget = runtime.question_turn_budget
    await service.end_interview(session.session_id)
    assert runtime.terminated is True
    assert session.interview_status == InterviewStatus.COMPLETED
    opening = await service.claim_agent_opening(session.session_id, "job-retry")
    assert opening["allow_opening_speech"] is False
    assert opening["action"] == "completed"
    assert opening["question"] is None
    assert await service.get_next_question(session.session_id) is None
    assert runtime.completed_turns == turns
    assert runtime.question_turn_budget == budget
    with pytest.raises(ValueError, match="already ended"):
        await service.start_interview(session.session_id, application=eligible_application)
    with pytest.raises(RuntimeError, match="already ended"):
        service.bridge.initialize(
            session.session_id,
            application_id=eligible_application.id,
            candidate_id=eligible_application.candidate_id,
            job_posting_id=eligible_application.job_posting_id,
            candidate_profile=eligible_application.candidate_profile,
            job_profile_snapshot=eligible_application.job_profile_snapshot,
        )


@pytest.mark.asyncio
async def test_end_marks_runtime_terminated_before_room_delete(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    order = []
    original_delete = service.livekit.delete_room

    async def _delete(room_name: str):
        runtime = service.bridge.get_runtime(session.session_id)
        order.append(("delete", bool(runtime.terminated), session.interview_status))
        return await original_delete(room_name)

    with patch.object(service.livekit, "delete_room", side_effect=_delete):
        await service.end_interview(session.session_id)
    assert order == [("delete", True, InterviewStatus.COMPLETED)]
    assert service.bridge.get_runtime(session.session_id).terminated is True


@pytest.mark.asyncio
async def test_llm_node_does_not_select_duplicate_question_from_second_runner(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    first_question = await service.get_next_question(session.session_id)
    await service.claim_agent_opening(session.session_id, "job-1")
    with _patch_assess_answers():
        first = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    duplicate = await service.claim_agent_opening(session.session_id, "job-2")
    runtime = service.bridge.get_runtime(session.session_id)
    assert first["next_question"] != first_question
    assert duplicate["allow_opening_speech"] is False
    assert duplicate["question"] == runtime.current.question_text
    assert duplicate["question"] == first["next_question"]
    assert runtime.asked[0].question_text == first_question


@pytest.mark.asyncio
async def test_final_answer_is_evaluated_then_closing_speech_is_used(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    runtime.question_turn_budget = 1
    with _patch_assess_answers():
        payload = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    assert payload["status"] == "processed"
    assert payload["evaluation"]["weighted_total"] == 72.0
    assert payload["completed"] is True
    assert payload["next_question"] is None
    assert runtime.evaluations

    bridge = AsyncMock()
    bridge.process_candidate_response.return_value = payload
    bridge.get_next_question.return_value = None
    agent = InterviewAgent(bridge=bridge)
    with patch("app.agents.interview_agent._interview_session_id", return_value=session.session_id):
        spoken = await agent.llm_node(
            _user_chat("I used FastAPI with PostgreSQL in production."),
            [],
            ModelSettings(),
        )
    assert spoken == _INTERVIEW_COMPLETE_MESSAGE
    assert agent._finish_after_reply is True


async def _answer_until(service, session_id: str, turns: int, weighted_total: float = 72.0):
    last = None
    with _patch_assess_answers(weighted_total=weighted_total):
        for _ in range(turns):
            last = await service.process_candidate_response(
                session_id, "I used FastAPI with PostgreSQL in production."
            )
    return last


@pytest.mark.asyncio
async def test_five_question_job_cannot_exceed_five_evaluated_turns(db_session):
    application = seed_application(db_session, interview_question_count=5)
    service, session = await _started_session(application)
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime.question_turn_budget == 5
    last = await _answer_until(service, session.session_id, 5)
    assert last["completed"] is True
    assert last["next_question"] is None
    assert runtime.completed_turns == 5
    with _patch_assess_answers():
        extra = await service.process_candidate_response(
            session.session_id, "This late answer must not consume another turn."
        )
    assert extra["status"] == "ignored"
    assert runtime.completed_turns == 5
    assert runtime.completed is True


@pytest.mark.asyncio
async def test_seven_question_job_can_use_seven_turns(db_session):
    application = seed_application(db_session, interview_question_count=7)
    service, session = await _started_session(application)
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime.question_turn_budget == 7
    sixth = await _answer_until(service, session.session_id, 6)
    assert sixth["completed"] is False
    assert sixth["next_question"]
    assert runtime.completed_turns == 6
    last = await _answer_until(service, session.session_id, 1)
    assert last["completed"] is True
    assert last["next_question"] is None
    assert runtime.completed_turns == 7


@pytest.mark.asyncio
async def test_configured_follow_up_consumes_the_same_question_budget(db_session):
    application = seed_application(db_session, interview_question_count=5)
    service, session = await _started_session(application)
    runtime = service.bridge.get_runtime(session.session_id)
    runtime.cv_follow_ups = [
        Question(
            question_text="Can you verify that FastAPI claim from your CV?",
            expected_knowledge_area="CV Verification",
            question_type="Project",
            baseline_difficulty="Junior",
            skills_covered=[],
        )
    ]
    with _patch_assess_answers(weighted_total=40.0):
        first = await service.process_candidate_response(
            session.session_id, "I am not sure about that implementation detail."
        )
    assert runtime.follow_up_turns == 1
    assert first["next_question"] == "Can you verify that FastAPI claim from your CV?"
    assert runtime.question_turn_budget == 5
    last = await _answer_until(service, session.session_id, 4)
    assert last["completed"] is True
    assert runtime.completed_turns == 5
    assert runtime.question_turn_budget == 5
    with _patch_assess_answers():
        extra = await service.process_candidate_response(
            session.session_id, "Another answer after the budget must be ignored."
        )
    assert extra["status"] == "ignored"
    assert runtime.completed_turns == 5


@pytest.mark.asyncio
async def test_duplicate_transcript_does_not_consume_configured_budget_twice(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    current = runtime.current.question_text
    with _patch_assess_answers():
        first = await service.process_candidate_response(
            session.session_id,
            "I used FastAPI with PostgreSQL in production.",
            question_text=current,
        )
        duplicate = await service.process_candidate_response(
            session.session_id,
            "I used FastAPI with PostgreSQL in production.",
            question_text=current,
        )
    assert first["status"] == "processed"
    assert duplicate["status"] == "ignored"
    assert duplicate["reason"] == "stale_transcript"
    assert runtime.completed_turns == 1

