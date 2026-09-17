"""Regression tests for real-time interview turn-taking."""
from __future__ import annotations

import asyncio
import inspect
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from livekit.agents import ModelSettings, llm

from app.agents.interview_agent import (
    InterviewAgent,
    _end_interview_via_backend,
    committed_user_transcript,
    should_transcribe_candidate_segment,
)
from app.agents.worker import INTERVIEW_TURN_HANDLING, entrypoint, prewarm_interview_process
from app.integrations.pipecat.interview_bridge import (
    HttpInterviewBridge,
    InterviewIntelligenceBridge,
    MockInterviewBridge,
    classify_candidate_turn,
    match_meta_utterance,
)
from app.models.application import Application
from app.services.assessment.assessment_service import AssessmentService
from tests.conftest import make_mock_voice_service
from tests.test_interview_intelligence_voice import (
    _expected_questions,
    _fake_evaluation,
    _patch_assess_answers,
)


def _user_chat(*messages: str) -> llm.ChatContext:
    chat_ctx = llm.ChatContext.empty()
    for message in messages:
        chat_ctx.add_message(role="user", content=message)
    return chat_ctx


async def _started_session(application: Application):
    service = make_mock_voice_service()
    session = await service.create_session(application)
    await service.start_interview(session.session_id, application=application)
    return service, session


@pytest.mark.asyncio
async def test_concurrent_responses_do_not_corrupt_runtime_state(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    first_question = await service.get_next_question(session.session_id)
    started = threading.Event()
    release = threading.Event()

    def _slow_assess(*args, **kwargs):
        question_set = args[1] if len(args) >= 3 else args[0]
        questions = list(question_set)
        started.set()
        assert release.wait(timeout=2)
        return [_fake_evaluation(questions[0], weighted_total=72.0)]

    with patch.object(AssessmentService, "assess_answers", side_effect=_slow_assess) as assess_spy:
        first = asyncio.create_task(
            service.process_candidate_response(
                session.session_id, "I used FastAPI with PostgreSQL in production."
            )
        )
        await asyncio.to_thread(started.wait, 2)
        second = asyncio.create_task(
            service.process_candidate_response(
                session.session_id, "This overlapping turn must not steal the same question."
            )
        )
        await asyncio.sleep(0.05)
        release.set()
        results = await asyncio.gather(first, second)

    statuses = {result["status"] for result in results}
    assert "processed" in statuses
    assert "ignored" in statuses
    ignored = next(result for result in results if result["status"] == "ignored")
    assert ignored["reason"] == "stale_transcript"
    assess_spy.assert_called_once()

    runtime = service.bridge.get_runtime(session.session_id)
    assert len(runtime.evaluations) == 1
    assert len(runtime.asked) == 1
    assert runtime.evaluations[0].question_text == first_question
    assert runtime.asked[0].question_text == first_question
    assert runtime.current is None or runtime.current.question_text != first_question


@pytest.mark.asyncio
async def test_did_you_hear_me_is_not_evaluated_or_consumed(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    first_question = await service.get_next_question(session.session_id)

    with _patch_assess_answers() as assess_spy:
        result = await service.process_candidate_response(
            session.session_id, "Did you hear me?"
        )

    assess_spy.assert_not_called()
    assert result["status"] == "acknowledged"
    assert result["meta"] is True
    assert "continue with your answer" in result["spoken_reply"].lower()
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime.evaluations == []
    assert runtime.asked == []
    assert runtime.current is not None
    assert runtime.current.question_text == first_question
    assert result["next_question"] == first_question
    assert runtime.completed is False


@pytest.mark.asyncio
async def test_can_you_hear_me_gets_conversational_acknowledgement(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    with _patch_assess_answers() as assess_spy:
        result = await service.process_candidate_response(
            session.session_id, "Can you hear me?"
        )

    assess_spy.assert_not_called()
    assert result["spoken_reply"] == "Yes, I can hear you. Please go ahead."
    assert match_meta_utterance("Hello, can you hear me?")
    assert match_meta_utterance("I used FastAPI with PostgreSQL in production.") is None


@pytest.mark.asyncio
async def test_normal_answer_still_invokes_interview_intelligence_once(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    first_question = await service.get_next_question(session.session_id)

    with _patch_assess_answers() as assess_spy:
        result = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )

    assess_spy.assert_called_once()
    assert result["status"] == "processed"
    assert result["evaluation"]["question_text"] == first_question
    assert result["evaluation"]["weighted_total"] == 72.0
    assert result["next_question"]
    assert result["next_question"] != first_question


@pytest.mark.asyncio
async def test_interview_does_not_complete_after_three_turns_when_questions_remain(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    expected = _expected_questions(eligible_application)
    assert len(expected) > 3

    with _patch_assess_answers():
        for index in range(3):
            result = await service.process_candidate_response(
                session.session_id,
                f"I used FastAPI with PostgreSQL in production for turn {index}.",
            )
            assert result["status"] == "processed"

    runtime = service.bridge.get_runtime(session.session_id)
    unused = [question for question in runtime.questions if question not in runtime.asked]
    assert len(runtime.evaluations) == 3
    assert unused
    assert runtime.completed is False
    assert result["completed"] is False
    assert result["next_question"]


@pytest.mark.asyncio
async def test_interview_completes_only_when_selector_returns_no_next_question(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    with _patch_assess_answers(), patch.object(
        InterviewIntelligenceBridge,
        "_select_next_question",
        return_value=None,
    ):
        result = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )

    runtime = service.bridge.get_runtime(session.session_id)
    assert result["completed"] is True
    assert result["next_question"] is None
    assert runtime.completed is True
    assert await service.get_next_question(session.session_id) is None


@pytest.mark.asyncio
async def test_next_question_is_obtained_automatically_after_valid_answer(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    first_question = await service.get_next_question(session.session_id)
    with _patch_assess_answers():
        result = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )

    assert result["next_question"]
    assert result["next_question"] != first_question
    assert await service.get_next_question(session.session_id) == result["next_question"]


def test_late_whisper_transcript_not_premature_partial():
    final = committed_user_transcript(
        "Did you hear me?",
        "I used FastAPI with PostgreSQL in production.",
    )
    assert final == "I used FastAPI with PostgreSQL in production."


@pytest.mark.asyncio
async def test_llm_node_forwards_only_the_latest_final_user_transcript():
    bridge = AsyncMock()
    bridge.process_candidate_response.return_value = {
        "status": "processed",
        "next_question": "What did you build next?",
    }
    agent = InterviewAgent(bridge=bridge)
    chat_ctx = _user_chat(
        "Did you hear me?",
        "I used FastAPI with PostgreSQL in production.",
    )

    with patch("app.agents.interview_agent._interview_session_id", return_value="sess-1"):
        spoken = await agent.llm_node(chat_ctx, [], ModelSettings())

    assert spoken == "What did you build next?"
    bridge.process_candidate_response.assert_awaited_once_with(
        "I used FastAPI with PostgreSQL in production.",
        "sess-1",
        question_text=None,
    )


@pytest.mark.asyncio
async def test_llm_node_sends_current_spoken_question_with_transcript():
    bridge = AsyncMock()
    bridge.process_candidate_response.return_value = {
        "status": "processed",
        "next_question": "What did you build next?",
    }
    agent = InterviewAgent(bridge=bridge)
    agent._current_spoken_question = "What did you build with FastAPI?"

    with patch("app.agents.interview_agent._interview_session_id", return_value="sess-1"):
        spoken = await agent.llm_node(
            _user_chat("I used FastAPI with PostgreSQL in production."),
            [],
            ModelSettings(),
        )

    assert spoken == "What did you build next?"
    bridge.process_candidate_response.assert_awaited_once_with(
        "I used FastAPI with PostgreSQL in production.",
        "sess-1",
        question_text="What did you build with FastAPI?",
    )
    assert agent._current_spoken_question == "What did you build next?"


@pytest.mark.asyncio
async def test_llm_node_acknowledges_meta_utterance_without_next_question_fetch():
    bridge = AsyncMock()
    bridge.process_candidate_response.return_value = {
        "status": "acknowledged",
        "spoken_reply": "Yes, I can hear you. Please continue with your answer.",
        "next_question": "Original question?",
    }
    agent = InterviewAgent(bridge=bridge)

    with patch("app.agents.interview_agent._interview_session_id", return_value="sess-1"):
        spoken = await agent.llm_node(_user_chat("Did you hear me?"), [], ModelSettings())

    assert spoken == "Yes, I can hear you. Please continue with your answer."
    bridge.get_next_question.assert_not_awaited()


@pytest.mark.asyncio
async def test_two_candidate_turns_can_occur_sequentially_without_microphone_toggle():
    bridge = AsyncMock()
    bridge.process_candidate_response.side_effect = [
        {"status": "processed", "next_question": "Question two?"},
        {"status": "processed", "next_question": "Question three?"},
    ]
    agent = InterviewAgent(bridge=bridge)

    with patch("app.agents.interview_agent._interview_session_id", return_value="sess-1"):
        first = await agent.llm_node(_user_chat("First real answer about FastAPI."), [], ModelSettings())
        second = await agent.llm_node(
            _user_chat("Second real answer about PostgreSQL."), [], ModelSettings()
        )

    assert first == "Question two?"
    assert second == "Question three?"
    assert bridge.process_candidate_response.await_count == 2
    source = inspect.getsource(InterviewAgent.llm_node)
    assert "microphone" not in source.lower()
    assert "toggle" not in source.lower()


def test_tts_handoff_uses_uninterruptible_vad_turn_handling():
    assert INTERVIEW_TURN_HANDLING["turn_detection"] == "vad"
    assert INTERVIEW_TURN_HANDLING["interruption"]["enabled"] is False
    assert INTERVIEW_TURN_HANDLING["interruption"]["mode"] == "vad"
    assert INTERVIEW_TURN_HANDLING["interruption"]["discard_audio_if_uninterruptible"] is True
    assert INTERVIEW_TURN_HANDLING["preemptive_generation"]["enabled"] is False
    assert INTERVIEW_TURN_HANDLING["endpointing"]["min_delay"] == 0.0

    from livekit.agents import AgentSession

    parameters = inspect.signature(AgentSession.__init__).parameters
    assert "turn_handling" in parameters
    assert "vad" in parameters


def test_candidate_speech_during_question_tts_is_not_transcribed():
    assert should_transcribe_candidate_segment(agent_output_in_progress=True) is False
    assert should_transcribe_candidate_segment(agent_output_in_progress=False) is True


@pytest.mark.asyncio
async def test_tts_completion_returns_to_listening_then_can_end_session():
    agent = InterviewAgent(bridge=AsyncMock())
    agent._finish_after_reply = True
    with patch(
        "app.agents.interview_agent._end_interview_via_backend",
        new_callable=AsyncMock,
    ) as end_spy:
        agent._on_agent_state_changed(
            SimpleNamespace(old_state="thinking", new_state="speaking")
        )
        assert agent._finish_after_reply is True
        end_spy.assert_not_called()
        agent._on_agent_state_changed(
            SimpleNamespace(old_state="speaking", new_state="listening")
        )
        await asyncio.sleep(0)

    assert agent._finish_after_reply is False
    end_spy.assert_awaited()


def test_voice_agent_default_bridge_is_still_http_not_mock():
    with patch("app.agents.interview_agent.Agent.__init__", return_value=None), patch(
        "app.agents.interview_agent.STTProviderFactory.get_provider", return_value=MagicMock()
    ):
        agent = InterviewAgent()

    assert isinstance(agent._bridge, HttpInterviewBridge)
    assert not isinstance(agent._bridge, MockInterviewBridge)
    assert not isinstance(make_mock_voice_service().bridge, MockInterviewBridge)


class _AwaitableSpeechHandle:
    def __init__(self):
        self.awaited = False

    def __await__(self):
        async def _inner():
            self.awaited = True
            return self

        return _inner().__await__()


@pytest.mark.asyncio
async def test_on_enter_awaits_initial_question_tts_before_returning():
    bridge = AsyncMock()
    bridge.claim_opening.return_value = {
        "action": "greet",
        "question": "What did you build with FastAPI?",
        "allow_opening_speech": True,
        "completed": False,
    }
    agent = InterviewAgent(bridge=bridge)
    handle = _AwaitableSpeechHandle()
    session = MagicMock()
    session.say.return_value = handle
    session.on = MagicMock()
    agent._activity = SimpleNamespace(session=session)

    with patch("app.agents.interview_agent._interview_session_id", return_value="sess-1"):
        await agent.on_enter()

    bridge.claim_opening.assert_awaited_once()
    session.say.assert_called_once()
    spoken = session.say.call_args.args[0]
    assert "Hello, thanks for joining" in spoken
    assert "What did you build with FastAPI?" in spoken
    assert session.say.call_args.kwargs["allow_interruptions"] is False
    assert handle.awaited is True


@pytest.mark.asyncio
async def test_greeting_tts_completion_does_not_end_interview():
    agent = InterviewAgent(bridge=AsyncMock())
    agent._finish_after_reply = False
    with patch(
        "app.agents.interview_agent._end_interview_via_backend",
        new_callable=AsyncMock,
    ) as end_spy:
        agent._on_agent_state_changed(
            SimpleNamespace(old_state="speaking", new_state="listening")
        )
        await asyncio.sleep(0)

    end_spy.assert_not_called()
    source = inspect.getsource(InterviewAgent.on_enter)
    assert "await self._speak_uninterruptible" in source


@pytest.mark.asyncio
async def test_http_bridge_reuses_async_client(monkeypatch):
    created = []

    class _GetResponse:
        status_code = 200

        def json(self):
            return {"question": "What did you build with FastAPI?"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            created.append(self)
            self.is_closed = False

        async def get(self, url, **kwargs):
            return _GetResponse()

        async def post(self, url, **kwargs):
            class _PostResponse:
                status_code = 200

                def json(self):
                    return {
                        "status": "processed",
                        "next_question": "What did you build next?",
                    }

            return _PostResponse()

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr(
        "app.integrations.pipecat.interview_bridge.httpx.AsyncClient",
        FakeClient,
    )
    bridge = HttpInterviewBridge(base_url="http://example.test/api/v1")
    try:
        assert await bridge.get_next_question("sess-1") == "What did you build with FastAPI?"
        first = await bridge.process_candidate_response(
            "I used FastAPI with PostgreSQL in production.", "sess-1"
        )
        second = await bridge.process_candidate_response(
            "I also designed the schema and indexes.", "sess-1"
        )
        third = await bridge.process_candidate_response(
            "Then I shipped the assessment report pipeline.", "sess-1"
        )
        assert first["next_question"] == "What did you build next?"
        assert second["status"] == "processed"
        assert third["status"] == "processed"
        assert len(created) == 1
        assert bridge.peek_http_client() is created[0]
    finally:
        await bridge.aclose()
        assert created[0].is_closed is True


@pytest.mark.asyncio
async def test_http_bridge_client_is_bound_to_the_running_event_loop(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            created.append((self, asyncio.get_running_loop()))
            self.is_closed = False

        async def get(self, url, **kwargs):
            class _GetResponse:
                status_code = 200

                def json(self):
                    return {"question": "Q1"}

            return _GetResponse()

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr(
        "app.integrations.pipecat.interview_bridge.httpx.AsyncClient",
        FakeClient,
    )
    bridge = HttpInterviewBridge(base_url="http://example.test/api/v1")
    loop = asyncio.get_running_loop()
    await bridge.get_next_question("sess-loop")
    assert len(created) == 1
    assert created[0][1] is loop
    await bridge.aclose()


@pytest.mark.asyncio
async def test_http_bridge_cannot_reuse_async_client_across_event_loops(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            created.append(self)
            self.is_closed = False
            self.loop = asyncio.get_running_loop()

        async def get(self, url, **kwargs):
            class _GetResponse:
                status_code = 200

                def json(self):
                    return {"question": "Q1"}

            return _GetResponse()

        async def aclose(self):
            self.is_closed = True

    monkeypatch.setattr(
        "app.integrations.pipecat.interview_bridge.httpx.AsyncClient",
        FakeClient,
    )
    bridge = HttpInterviewBridge(base_url="http://example.test/api/v1")
    await bridge.get_next_question("sess-a")
    first_client = bridge.peek_http_client()
    first_loop = asyncio.get_running_loop()

    def _use_on_new_loop():
        async def _inner():
            await bridge.get_next_question("sess-a")
            return bridge.peek_http_client(), asyncio.get_running_loop()

        return asyncio.run(_inner())

    second_client, second_loop = await asyncio.to_thread(_use_on_new_loop)
    assert first_client is not None
    assert second_client is not None
    assert first_client is not second_client
    assert first_loop is not second_loop
    assert len(created) == 2


def test_http_response_methods_do_not_construct_async_client():
    response_src = inspect.getsource(HttpInterviewBridge.process_candidate_response)
    question_src = inspect.getsource(HttpInterviewBridge.get_next_question)
    assert "AsyncClient(" not in response_src
    assert "AsyncClient(" not in question_src


def test_worker_prewarms_vad_before_livekit_connect():
    setup = inspect.getsource(prewarm_interview_process)
    assert "VAD.load" in setup
    assert "warmup_blocking_providers" in setup
    assert "warmup_whisper_model" in setup
    assert "warmup_shared_http_client" not in setup
    assert "AsyncClient" not in setup
    entry = inspect.getsource(entrypoint)
    assert entry.index('userdata.get("vad")') < entry.index("ctx.connect()")


def test_tts_starts_after_next_question_selection():
    llm_src = inspect.getsource(InterviewAgent.llm_node)
    spoken_src = inspect.getsource(InterviewAgent._spoken_text_from_result)
    tts_src = inspect.getsource(InterviewAgent.tts_node)
    assert "process_candidate_response" in llm_src
    assert "next_question" in spoken_src
    assert "synthesize" not in llm_src
    assert "tts_start" in tts_src
    assert "tts_first_audio" in tts_src
    assert "synthesize_pcm_stream" in tts_src or "synthesize_with_fallback" in tts_src


def test_classify_candidate_turn_detects_stale_and_current_questions():
    assert classify_candidate_turn(
        intended_question="Q1", current_question="Q1"
    ) == "evaluate"
    assert classify_candidate_turn(
        intended_question="Q1", current_question="Q2"
    ) == "stale"
    assert classify_candidate_turn(
        intended_question=None, current_question="Q1"
    ) == "evaluate"
    assert classify_candidate_turn(
        intended_question="Q1", current_question=None
    ) == "stale"
    assert classify_candidate_turn(
        intended_question=None, current_question=None
    ) == "no_pending_question"


@pytest.mark.asyncio
async def test_late_final_transcript_does_not_evaluate_the_next_question(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    first_question = await service.get_next_question(session.session_id)
    with _patch_assess_answers() as assess_spy:
        first = await service.process_candidate_response(
            session.session_id,
            "I used FastAPI with PostgreSQL in production.",
            question_text=first_question,
        )
        late = await service.process_candidate_response(
            session.session_id,
            "Trailing leftover audio from the previous answer.",
            question_text=first_question,
        )

    assert first["status"] == "processed"
    assert late["status"] == "ignored"
    assert late["reason"] == "stale_transcript"
    assess_spy.assert_called_once()
    runtime = service.bridge.get_runtime(session.session_id)
    assert len(runtime.evaluations) == 1
    assert runtime.asked[0].question_text == first_question
    assert runtime.current is None or runtime.current.question_text == first["next_question"]


@pytest.mark.asyncio
async def test_two_final_transcripts_cannot_evaluate_the_same_question_twice(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    first_question = await service.get_next_question(session.session_id)
    with _patch_assess_answers() as assess_spy:
        results = await asyncio.gather(
            service.process_candidate_response(
                session.session_id,
                "I used FastAPI with PostgreSQL in production.",
                question_text=first_question,
            ),
            service.process_candidate_response(
                session.session_id,
                "Duplicate final transcript for the same question.",
                question_text=first_question,
            ),
        )

    processed = [item for item in results if item["status"] == "processed"]
    ignored = [item for item in results if item["status"] == "ignored"]
    assert len(processed) == 1
    assert len(ignored) == 1
    assert ignored[0]["reason"] == "stale_transcript"
    assess_spy.assert_called_once()
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime.completed_turns == 1
    assert len(runtime.evaluations) == 1


@pytest.mark.asyncio
async def test_queued_real_answer_behind_meta_is_processed(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    first_question = await service.get_next_question(session.session_id)
    started = asyncio.Event()
    release = asyncio.Event()
    original = service.bridge._process_candidate_response_locked

    async def _delay_meta(text, session_id, intended_question=None):
        if match_meta_utterance(text):
            started.set()
            await release.wait()
        return await original(text, session_id, intended_question=intended_question)

    with patch.object(
        service.bridge,
        "_process_candidate_response_locked",
        side_effect=_delay_meta,
    ), _patch_assess_answers() as assess_spy:
        meta = asyncio.create_task(
            service.process_candidate_response(session.session_id, "Did you hear me?")
        )
        await started.wait()
        real = asyncio.create_task(
            service.process_candidate_response(
                session.session_id,
                "I used FastAPI with PostgreSQL in production.",
            )
        )
        await asyncio.sleep(0.05)
        release.set()
        meta_result, real_result = await asyncio.gather(meta, real)

    assert meta_result["status"] == "acknowledged"
    assert real_result["status"] == "processed"
    assess_spy.assert_called_once()
    runtime = service.bridge.get_runtime(session.session_id)
    assert len(runtime.evaluations) == 1
    assert runtime.asked[0].question_text == first_question


@pytest.mark.asyncio
async def test_stale_transcript_cannot_advance_the_interview_twice(
    eligible_application: Application,
):
    service, session = await _started_session(eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    budget = runtime.question_turn_budget
    first_question = await service.get_next_question(session.session_id)
    with _patch_assess_answers() as assess_spy:
        await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
        late = await service.process_candidate_response(
            session.session_id,
            "Same turn leftover must not consume another budget slot.",
            question_text=first_question,
        )
    assert late["reason"] == "stale_transcript"
    assert runtime.completed_turns == 1
    assert runtime.question_turn_budget == budget
    assert len(runtime.asked) == 1
    assess_spy.assert_called_once()


@pytest.mark.asyncio
async def test_response_timing_stages_are_measurable(
    eligible_application: Application, caplog
):
    service, session = await _started_session(eligible_application)
    with _patch_assess_answers(), caplog.at_level("INFO"):
        await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    stages = {
        "evaluation_start",
        "evaluation_done",
        "adaptive_start",
        "adaptive_done",
        "next_question_selected",
    }
    logged = caplog.text
    for stage in stages:
        assert f"stage={stage}" in logged


@pytest.mark.asyncio
async def test_deferred_transcript_during_tts_is_processed_when_still_current():
    bridge = AsyncMock()
    bridge.process_candidate_response.return_value = {
        "status": "processed",
        "next_question": "What did you build next?",
    }
    bridge.get_next_question.return_value = "What did you build next?"
    agent = InterviewAgent(bridge=bridge)
    agent._current_spoken_question = "What did you build with FastAPI?"
    agent._deferred_transcript = (
        "I used FastAPI with PostgreSQL in production.",
        "What did you build with FastAPI?",
    )
    handle = _AwaitableSpeechHandle()
    session = MagicMock()
    session.say.return_value = handle
    agent._activity = SimpleNamespace(session=session)

    with patch("app.agents.interview_agent._interview_session_id", return_value="sess-1"):
        await agent._flush_deferred_transcript()

    bridge.process_candidate_response.assert_awaited_once()
    assert session.say.called
    assert handle.awaited is True
    assert agent._current_spoken_question == "What did you build next?"


@pytest.mark.asyncio
async def test_stale_deferred_transcript_during_tts_is_not_evaluated():
    bridge = AsyncMock()
    agent = InterviewAgent(bridge=bridge)
    agent._current_spoken_question = "Question two?"
    agent._deferred_transcript = ("Leftover from question one.", "Question one?")
    with patch("app.agents.interview_agent._interview_session_id", return_value="sess-1"):
        await agent._flush_deferred_transcript()
    bridge.process_candidate_response.assert_not_awaited()


def test_get_default_provider_reuses_cached_instance():
    from app.integrations.llm.factory import (
        get_default_provider,
        reset_default_provider_cache_for_tests,
    )

    reset_default_provider_cache_for_tests()
    try:
        first = get_default_provider()
        second = get_default_provider()
        assert first is second
    finally:
        reset_default_provider_cache_for_tests()
