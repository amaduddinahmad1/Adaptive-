"""
Interview voice agent using LiveKit Agents node overrides.

These STT/LLM/TTS node overrides still make synchronous/batch-style calls to our
existing Day 3 providers (WhisperLocalSTTProvider.transcribe(),
HttpInterviewBridge -> InterviewIntelligenceBridge,
TTSProviderFactory.synthesize_with_fallback()). That is intentional: it reuses the
tested batch pipeline rather than the framework's native streaming pattern, and can
be optimized to real streaming later if latency requires it.

The installed livekit-agents Agent.stt_node receives a long-lived
AsyncIterable[rtc.AudioFrame] (not a per-turn buffer). ModelSettings only carries
tool_choice — it does not signal end-of-turn. For non-streaming STT the framework's
default path (Agent.default.stt_node + stt.StreamAdapter) treats VAD END_OF_SPEECH
as the turn boundary, then calls STT.recognize() on the VAD-segmented frames. We
mirror that here before calling whisper_local.transcribe().
"""
from __future__ import annotations

import array
import asyncio
import io
import logging
import os
import time
import wave
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any

import httpx
from livekit import rtc
from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    Agent,
    ModelSettings,
    get_job_context,
    llm,
    stt,
    tts,
    utils,
    vad,
)
from livekit.agents.types import APIConnectOptions, NotGivenOr
from livekit.agents.utils.audio import AudioByteStream

from app.core.interview_latency import TurnLatency, log_interview_latency
from app.integrations.pipecat.interview_bridge import (
    HttpInterviewBridge,
    InterviewBridge,
)
from app.integrations.stt.factory import STTProviderFactory
from app.integrations.tts.base import TTSProviderError
from app.integrations.tts.factory import TTSProviderFactory
from app.schemas.stt import STTConfig
from app.schemas.tts import TTSConfig, TTSResult

logger = logging.getLogger(__name__)

_DEFAULT_LANGUAGE = "en"
_ROOM_SESSION_PREFIX = "interview-"
_GREETING = "Hello, thanks for joining. Let's get started."
_NO_SPEECH_TIMEOUT_SECONDS = 12
_MAX_CONSECUTIVE_SILENCE_PROMPTS = 2
_NO_SPEECH_PROMPT = "Are you still there? Take your time whenever you're ready to answer."
_FINAL_SILENCE_MESSAGE = (
    "It looks like we're having trouble hearing you. I'll go ahead and end this session now."
)
_EMPTY_TRANSCRIPT_PROMPT = "Sorry, I didn't catch that — could you repeat your answer?"
_INTERVIEW_COMPLETE_MESSAGE = (
    "Thank you, that concludes our questions. I'll end the interview now."
)
_END_INTENT_CLOSING_MESSAGE = (
    "Understood — thank you for your time today. I'll end the interview now."
)
_END_INTENT_PHRASES = [
    "don't want to continue",
    "do not want to continue",
    "want to stop the interview",
    "end the interview",
    "stop the interview",
    "i need to leave now",
    "i have to go now",
    "i want to end this interview",
    "i'd like to end the interview",
    "i need to end this call",
    "i'm done with this interview",
]
_BACKEND_BASE_URL = os.getenv("BACKEND_API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")


def _matches_end_intent(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _END_INTENT_PHRASES)


def should_transcribe_candidate_segment(*, agent_output_in_progress: bool) -> bool:
    """Drop candidate audio while the interviewer is speaking or thinking."""
    return not agent_output_in_progress


def committed_user_transcript(*texts: str) -> str:
    """Forward only the latest finalized transcript into /response."""
    for text in reversed(texts):
        cleaned = (text or "").strip()
        if cleaned:
            return cleaned
    return ""


class _PipelinePlaceholderSTT(stt.STT):
    """Satisfies AgentActivity.stt so the custom stt_node is wired. Unused at inference."""

    def __init__(self) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(streaming=True, interim_results=False),
        )

    @property
    def model(self) -> str:
        return "whisper_local"

    @property
    def provider(self) -> str:
        return "whisper_local"

    async def _recognize_impl(
        self,
        buffer: utils.AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[])


class _PipelinePlaceholderLLMStream(llm.LLMStream):
    async def _run(self) -> None:
        return


class _PipelinePlaceholderLLM(llm.LLM):
    """Satisfies AgentActivity.llm so generate_reply invokes llm_node. Unused at inference."""

    @property
    def model(self) -> str:
        return "interview_intelligence"

    @property
    def provider(self) -> str:
        return "interview_intelligence"

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[llm.ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> llm.LLMStream:
        return _PipelinePlaceholderLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )


class _PipelinePlaceholderTTS(tts.TTS):
    """Satisfies AgentActivity.tts so say()/audio output can reach tts_node. Unused at inference."""

    def __init__(self) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=16000,
            num_channels=1,
        )

    @property
    def model(self) -> str:
        return "tts_factory_fallback"

    @property
    def provider(self) -> str:
        return "tts_factory_fallback"

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        raise NotImplementedError("InterviewAgent.tts_node handles synthesis")


class InterviewAgent(Agent):
    def __init__(self, bridge: InterviewBridge | None = None) -> None:
        super().__init__(
            instructions="You are conducting a structured voice interview.",
            stt=_PipelinePlaceholderSTT(),
            llm=_PipelinePlaceholderLLM(),
            tts=_PipelinePlaceholderTTS(),
            turn_handling={
                "turn_detection": "vad",
                "interruption": {
                    "enabled": False,
                    "mode": "vad",
                    "discard_audio_if_uninterruptible": True,
                },
                "preemptive_generation": {"enabled": False},
            },
        )
        self._whisper = STTProviderFactory.get_provider()
        self._bridge = bridge or HttpInterviewBridge()
        self._greeting_sent = False
        self._finish_after_reply = False
        self._state_listener_registered = False
        self._turn_latency: TurnLatency | None = None
        self._stt_in_progress = False
        self._response_in_flight = False
        self._current_spoken_question: str | None = None
        self._deferred_transcript: tuple[str, str | None] | None = None
        self._overlap_frames: list[rtc.AudioFrame] = []

    async def aclose(self) -> None:
        closer = getattr(self._bridge, "aclose", None)
        if callable(closer):
            await closer()

    async def _end_this_interview(self) -> None:
        http_client = None
        peek = getattr(self._bridge, "peek_http_client", None)
        if callable(peek):
            http_client = peek()
        await _end_interview_via_backend(
            _interview_session_id(),
            http_client=http_client,
        )

    async def on_enter(self) -> None:
        """Speak a greeting and the first question when the agent joins the room.

        livekit-agents 1.8.1 calls this once from AgentActivity.start (not on
        resume). Built-in workflows use session.generate_reply() so the LLM can
        produce that first utterance. We already have the first-question text
        from Interview Intelligence, so we use the canned-text equivalent noted on
        Agent.on_user_turn_exceeded: session.say(). That still synthesizes through
        tts_node (AgentActivity.say -> _tts_task -> perform_tts_inference).

        session.say() returns a SpeechHandle; awaiting it waits for playout so
        the greeting is not abandoned when on_enter returns.
        """
        if self._greeting_sent:
            return
        self._greeting_sent = True
        if not self._state_listener_registered:
            self.session.on("agent_state_changed", self._on_agent_state_changed)
            self._state_listener_registered = True

        session_id = _interview_session_id()
        logger.info("Retrieving initial question for session %s", session_id)
        entry = await self._resolve_opening(session_id)
        if not entry.get("allow_opening_speech"):
            logger.info(
                "Standing down interview agent session=%s action=%s completed=%s",
                session_id,
                entry.get("action"),
                entry.get("completed"),
            )
            return
        question = (entry.get("question") or "").strip()
        if not question:
            logger.info("No opening question for session %s; not speaking greeting", session_id)
            return
        spoken = f"{_GREETING} {question}"
        self._current_spoken_question = question
        logger.info(
            "Initial question retrieved session=%s has_question=%s budget=%s",
            session_id,
            True,
            entry.get("question_turn_budget"),
        )
        await self._speak_uninterruptible(spoken)
        logger.info("Question speech completed")

    async def _resolve_opening(self, session_id: str) -> dict[str, Any]:
        owner_id = _interview_job_id()
        claim_opening = getattr(self._bridge, "claim_opening", None)
        if callable(claim_opening):
            try:
                entry = await claim_opening(session_id, owner_id)
            except TypeError:
                entry = await claim_opening(session_id)
            if isinstance(entry, dict):
                return entry
        question = (await self._bridge.get_next_question(session_id) or "").strip()
        return {
            "action": "greet" if question else "completed",
            "question": question or None,
            "completed": not bool(question),
            "allow_opening_speech": bool(question),
        }

    def _on_agent_state_changed(self, ev: Any) -> None:
        new_state = getattr(ev, "new_state", None)
        old_state = getattr(ev, "old_state", None)
        if new_state == "listening":
            logger.info("Listening state entered")
            self._response_in_flight = False
            if old_state == "speaking" and self._turn_latency is not None:
                self._turn_latency.mark("question_playout_done")
                self._turn_latency.total()
                self._turn_latency = None
            if not self._finish_after_reply:
                asyncio.create_task(self._flush_deferred_transcript())
        elif new_state == "speaking":
            logger.info("Speaking state entered")
        if not self._finish_after_reply:
            return
        if old_state != "speaking":
            return
        if new_state != "listening":
            return
        self._finish_after_reply = False
        asyncio.create_task(self._end_this_interview())

    async def _speak_uninterruptible(self, text: str) -> Any:
        logger.info("TTS started chars=%s", len(text or ""))
        if self._turn_latency is not None:
            self._turn_latency.mark("tts_start", chars=len(text or ""))
        handle = self.session.say(text, allow_interruptions=False)
        await handle
        return handle

    def _agent_output_in_progress(self) -> bool:
        """True while the greeting or a turn reply is still being produced."""
        if self.session.agent_state in ("speaking", "thinking", "initializing"):
            return True
        speech = self.session.current_speech
        return speech is not None and not speech.done()

    def _turn_busy(self) -> bool:
        return (
            self._stt_in_progress
            or self._response_in_flight
            or self._agent_output_in_progress()
        )

    async def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncGenerator[stt.SpeechEvent, None]:
        activity = self._get_activity_or_raise()
        activity_vad = activity.vad
        if activity_vad is None:
            logger.warning(
                "No VAD on the agent session; transcribing only when the audio "
                "channel closes (session end), not per turn"
            )
            async for event in self._transcribe_after_stream_end(audio):
                yield event
            return

        vad_stream = activity_vad.stream()

        async def _forward_input() -> None:
            try:
                async for frame in audio:
                    vad_stream.push_frame(frame)
            finally:
                vad_stream.end_input()

        # Never wrap anext(vad_stream) in wait_for: cancelling that coroutine
        # corrupts VADStream's internal task. Read in a background task and
        # apply the silence timeout only to queue.get().
        _VAD_STREAM_ENDED = object()
        event_queue: asyncio.Queue[vad.VADEvent | object] = asyncio.Queue()

        async def _read_vad_events() -> None:
            try:
                while True:
                    event = await anext(vad_stream)
                    # Silero emits INFERENCE_DONE on every window, including silence.
                    # Waiting on those would never hit the no-speech timeout.
                    if event.type != vad.VADEventType.INFERENCE_DONE:
                        await event_queue.put(event)
            except StopAsyncIteration:
                pass
            finally:
                event_queue.put_nowait(_VAD_STREAM_ENDED)

        forward_task = asyncio.create_task(_forward_input())
        reader_task = asyncio.create_task(_read_vad_events())
        consecutive_silence_prompts = 0
        in_speech = False
        try:
            while True:
                try:
                    if in_speech:
                        event = await event_queue.get()
                    else:
                        event = await asyncio.wait_for(
                            event_queue.get(),
                            timeout=_NO_SPEECH_TIMEOUT_SECONDS,
                        )
                except TimeoutError:
                    if self._agent_output_in_progress():
                        continue
                    if consecutive_silence_prompts < _MAX_CONSECUTIVE_SILENCE_PROMPTS:
                        try:
                            self.session.say(_NO_SPEECH_PROMPT, allow_interruptions=False)
                        except Exception:
                            logger.warning(
                                "Failed to speak no-speech prompt",
                                exc_info=True,
                            )
                        consecutive_silence_prompts += 1
                        continue
                    logger.warning(
                        "Candidate may have disconnected or have a mic issue "
                        "after %s consecutive silence timeouts; ending session",
                        consecutive_silence_prompts + 1,
                    )
                    try:
                        await self.session.say(
                            _FINAL_SILENCE_MESSAGE, allow_interruptions=False
                        )
                    except Exception:
                        logger.warning(
                            "Failed to speak final silence message before ending session",
                            exc_info=True,
                        )
                    await self._end_this_interview()
                    break

                if event is _VAD_STREAM_ENDED:
                    break

                if event.type == vad.VADEventType.START_OF_SPEECH:
                    if not should_transcribe_candidate_segment(
                        agent_output_in_progress=self._turn_busy()
                    ):
                        continue
                    in_speech = True
                    yield stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
                elif event.type == vad.VADEventType.END_OF_SPEECH:
                    in_speech = False
                    if self._stt_in_progress:
                        self._overlap_frames.extend(event.frames or [])
                        continue
                    if not should_transcribe_candidate_segment(
                        agent_output_in_progress=self._turn_busy()
                    ):
                        continue
                    speech_end_time = (
                        time.time() - event.silence_duration - event.inference_duration
                    )
                    self._turn_latency = TurnLatency(_interview_session_id())
                    self._turn_latency.mark("turn_committed_at")
                    self._turn_latency.mark("candidate_turn_committed")
                    intended_at_commit = self._current_spoken_question
                    yield stt.SpeechEvent(
                        type=stt.SpeechEventType.END_OF_SPEECH,
                        speech_end_time=speech_end_time,
                    )
                    transcript_event = await self._transcribe_vad_frames(event.frames)
                    if transcript_event is not None:
                        if _matches_end_intent(transcript_event.alternatives[0].text):
                            try:
                                await self.session.say(
                                    _END_INTENT_CLOSING_MESSAGE, allow_interruptions=False
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to speak end-intent closing message before ending session",
                                    exc_info=True,
                                )
                            await self._end_this_interview()
                            break
                        consecutive_silence_prompts = 0
                        final_text = transcript_event.alternatives[0].text
                        if self._response_in_flight or self._agent_output_in_progress():
                            self._deferred_transcript = (final_text, intended_at_commit)
                            log_interview_latency(
                                _interview_session_id(),
                                "transcript_deferred",
                                during_tts=self._agent_output_in_progress(),
                            )
                            continue
                        self._response_in_flight = True
                        yield transcript_event
        finally:
            await utils.aio.cancel_and_wait(forward_task, reader_task)
            await vad_stream.aclose()

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: ModelSettings,
    ) -> str:
        transcript = committed_user_transcript(_latest_user_transcript(chat_ctx))
        session_id = _interview_session_id()
        if not transcript:
            return _EMPTY_TRANSCRIPT_PROMPT

        intended_question = self._current_spoken_question
        turn = self._turn_latency
        if turn is not None:
            turn.mark("response_start")
        else:
            log_interview_latency(session_id, "response_start")
        self._response_in_flight = True
        result = await self._bridge.process_candidate_response(
            transcript,
            session_id,
            question_text=intended_question,
        )
        if turn is not None:
            turn.mark("response_done")
        spoken = await self._spoken_text_from_result(result, session_id)
        if result.get("status") == "processed":
            next_question = (result.get("next_question") or "").strip()
            self._current_spoken_question = next_question or None
        return spoken

    async def _spoken_text_from_result(self, result: Any, session_id: str) -> str:
        if not isinstance(result, dict):
            return ""
        spoken_reply = (result.get("spoken_reply") or "").strip()
        if spoken_reply:
            return spoken_reply
        if result.get("status") == "ignored":
            return ""
        if result.get("completed") and not result.get("next_question"):
            self._finish_after_reply = True
            return _INTERVIEW_COMPLETE_MESSAGE

        reply = result.get("next_question")
        if not reply:
            reply = await self._bridge.get_next_question(session_id)
        if reply:
            if self._turn_latency is not None:
                self._turn_latency.mark("next_question_selected")
            return str(reply).strip()

        self._finish_after_reply = True
        return _INTERVIEW_COMPLETE_MESSAGE

    async def _flush_deferred_transcript(self) -> None:
        deferred = self._deferred_transcript
        self._deferred_transcript = None
        if not deferred or self._response_in_flight or self._finish_after_reply:
            return
        text, intended_question = deferred
        if not (text or "").strip():
            return
        if intended_question and intended_question != self._current_spoken_question:
            log_interview_latency(
                _interview_session_id(),
                "stale_transcript",
                reason="question_advanced",
            )
            return
        session_id = _interview_session_id()
        self._response_in_flight = True
        try:
            result = await self._bridge.process_candidate_response(
                text,
                session_id,
                question_text=intended_question or self._current_spoken_question,
            )
            spoken = await self._spoken_text_from_result(result, session_id)
            if result.get("status") == "processed":
                next_question = (result.get("next_question") or "").strip()
                self._current_spoken_question = next_question or None
                log_interview_latency(session_id, "queued_transcript_processed")
            if spoken:
                await self._speak_uninterruptible(spoken)
        except Exception:
            logger.warning("Failed to process deferred candidate transcript", exc_info=True)
            self._response_in_flight = False

    async def tts_node(
        self, text: AsyncIterable[str], model_settings: ModelSettings
    ) -> AsyncGenerator[rtc.AudioFrame, None]:
        chunks: list[str] = []
        async for chunk in text:
            if chunk:
                chunks.append(chunk)
        spoken = "".join(chunks).strip()
        if not spoken:
            return

        logger.info("TTS audio generation started chars=%s", len(spoken))
        turn = self._turn_latency
        if turn is not None:
            turn.mark("tts_start", chars=len(spoken))
        else:
            log_interview_latency(_interview_session_id(), "tts_start", chars=len(spoken))

        config = TTSConfig(
            provider="elevenlabs",
            language=_DEFAULT_LANGUAGE,
            output_format="LINEAR16",
        )
        first_audio_logged = False

        def _mark_first_audio() -> None:
            nonlocal first_audio_logged
            if first_audio_logged:
                return
            first_audio_logged = True
            if turn is not None:
                turn.mark("tts_first_audio")
            else:
                log_interview_latency(_interview_session_id(), "tts_first_audio")

        streamed_any = False
        try:
            primary = await TTSProviderFactory._aget_provider("elevenlabs")
            stream_fn = getattr(primary, "synthesize_pcm_stream", None)
            if callable(stream_fn):
                stream = AudioByteStream(
                    sample_rate=16000, num_channels=1, progressive=True
                )
                frame_count = 0
                async for chunk in stream_fn(spoken, config):
                    if not chunk:
                        continue
                    _mark_first_audio()
                    frames = stream.push(chunk)
                    frame_count += len(frames)
                    for frame in frames:
                        streamed_any = True
                        yield frame
                flushed = stream.flush()
                frame_count += len(flushed)
                for frame in flushed:
                    streamed_any = True
                    yield frame
                if turn is not None:
                    turn.mark("tts_generation_done", frames=frame_count)
                else:
                    log_interview_latency(
                        _interview_session_id(), "tts_generation_done", frames=frame_count
                    )
                return
        except TTSProviderError:
            if streamed_any:
                logger.warning(
                    "ElevenLabs streaming TTS failed after audio started",
                    exc_info=True,
                )
                return
            logger.warning(
                "ElevenLabs streaming TTS failed; using synthesize_with_fallback",
                exc_info=True,
            )

        result = await TTSProviderFactory.synthesize_with_fallback(spoken, config)
        frames = _audio_frames_from_tts_result(result)
        logger.info(
            "TTS audio generation completed provider=%s frames=%s sample_rate=%s",
            result.provider,
            len(frames),
            result.sample_rate,
        )
        if not frames:
            logger.warning("TTS produced no audio frames for playback")
        if frames:
            _mark_first_audio()
        if turn is not None:
            turn.mark("tts_generation_done", provider=result.provider, frames=len(frames))
        for frame in frames:
            yield frame

    async def _transcribe_after_stream_end(
        self, audio: AsyncIterable[rtc.AudioFrame]
    ) -> AsyncGenerator[stt.SpeechEvent, None]:
        frames: list[rtc.AudioFrame] = []
        async for frame in audio:
            frames.append(frame)
        transcript_event = await self._transcribe_vad_frames(frames)
        if transcript_event is not None:
            yield stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
            yield transcript_event

    async def _transcribe_vad_frames(
        self, frames: list[rtc.AudioFrame]
    ) -> stt.SpeechEvent | None:
        if not frames:
            return None
        self._stt_in_progress = True
        try:
            merged = rtc.combine_audio_frames(frames)
            pcm = _pcm16_mono_bytes(merged)
            if not pcm:
                return None
            audio_s = len(pcm) / 2 / float(merged.sample_rate or 16000)
            runtime = {}
            info_fn = getattr(self._whisper, "model_runtime_info", None)
            if callable(info_fn):
                runtime = info_fn() or {}
            if self._turn_latency is not None:
                self._turn_latency.mark(
                    "stt_start",
                    audio_s=f"{audio_s:.2f}",
                    model=runtime.get("model_size"),
                    device=runtime.get("device"),
                    cpu_threads=runtime.get("cpu_threads"),
                )
            result = await self._whisper.transcribe(
                pcm,
                STTConfig(
                    provider=self._whisper.get_provider_name(),
                    language=_DEFAULT_LANGUAGE,
                    sample_rate=merged.sample_rate,
                    encoding="LINEAR16",
                ),
            )
            text = (result.text or "").strip()
            while self._overlap_frames:
                overlap = self._overlap_frames
                self._overlap_frames = []
                extra_event = await self._transcribe_vad_frames_once(overlap)
                extra_text = ""
                if extra_event is not None:
                    extra_text = (extra_event.alternatives[0].text or "").strip()
                if extra_text:
                    text = f"{text} {extra_text}".strip() if text else extra_text
            if self._turn_latency is not None:
                self._turn_latency.mark(
                    "stt_final",
                    stt_ms=f"{result.processing_time_ms:.0f}",
                    empty=not bool(text),
                )
            if not text:
                try:
                    self.session.say(_EMPTY_TRANSCRIPT_PROMPT, allow_interruptions=False)
                except Exception:
                    logger.warning(
                        "Failed to speak empty-transcript prompt",
                        exc_info=True,
                    )
                return None
            return stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[
                    stt.SpeechData(
                        language=result.language or _DEFAULT_LANGUAGE,
                        text=text,
                        confidence=result.confidence,
                    )
                ],
            )
        finally:
            self._stt_in_progress = False

    async def _transcribe_vad_frames_once(
        self, frames: list[rtc.AudioFrame]
    ) -> stt.SpeechEvent | None:
        if not frames:
            return None
        merged = rtc.combine_audio_frames(frames)
        pcm = _pcm16_mono_bytes(merged)
        if not pcm:
            return None
        result = await self._whisper.transcribe(
            pcm,
            STTConfig(
                provider=self._whisper.get_provider_name(),
                language=_DEFAULT_LANGUAGE,
                sample_rate=merged.sample_rate,
                encoding="LINEAR16",
            ),
        )
        text = (result.text or "").strip()
        if not text:
            return None
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                stt.SpeechData(
                    language=result.language or _DEFAULT_LANGUAGE,
                    text=text,
                    confidence=result.confidence,
                )
            ],
        )


def _latest_user_transcript(chat_ctx: llm.ChatContext) -> str:
    for message in reversed(chat_ctx.messages()):
        if message.role == "user":
            return (message.raw_text_content or "").strip()
    return ""


async def _end_interview_via_backend(session_id: str, http_client: Any | None = None) -> None:
    """Best-effort POST to the same /voice/sessions/{id}/end route the frontend uses."""
    url = f"{_BACKEND_BASE_URL}/voice/sessions/{session_id}/end"
    owned_client = False
    client = http_client
    if client is None or getattr(client, "is_closed", False):
        client = httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        owned_client = True
    try:
        response = await client.post(url, timeout=10.0)
        if 200 <= response.status_code < 300:
            logger.info(
                "Ended interview session %s via backend API (%s)",
                session_id,
                response.status_code,
            )
        else:
            logger.warning(
                "Failed to end interview session %s via backend API: HTTP %s",
                session_id,
                response.status_code,
            )
    except Exception:
        logger.warning(
            "Failed to end interview session %s via backend API at %s",
            session_id,
            url,
            exc_info=True,
        )
    finally:
        if owned_client:
            await client.aclose()


def _interview_session_id() -> str:
    ctx = get_job_context(required=False)
    if ctx is None:
        return "local"
    name = (ctx.room.name or "").strip() or "local"
    if name.startswith(_ROOM_SESSION_PREFIX):
        return name[len(_ROOM_SESSION_PREFIX) :]
    return name


def _interview_job_id() -> str:
    ctx = get_job_context(required=False)
    if ctx is None:
        return "local"
    job = getattr(ctx, "job", None)
    job_id = getattr(job, "id", None)
    if job_id:
        return str(job_id)
    return "local"


def _pcm16_mono_bytes(frame: rtc.AudioFrame) -> bytes:
    raw = bytes(memoryview(frame.data).cast("B"))
    if frame.num_channels <= 1:
        return raw
    return _downmix_interleaved_int16(raw, frame.num_channels)


def _downmix_interleaved_int16(pcm: bytes, num_channels: int) -> bytes:
    samples = array.array("h")
    samples.frombytes(pcm)
    if num_channels <= 1 or not samples:
        return samples.tobytes()
    mono = array.array("h")
    for i in range(0, len(samples) - num_channels + 1, num_channels):
        acc = 0
        for channel in range(num_channels):
            acc += samples[i + channel]
        mono.append(int(acc / num_channels))
    return mono.tobytes()


def _audio_frames_from_tts_result(result: TTSResult) -> list[rtc.AudioFrame]:
    pcm, sample_rate = _pcm16_from_tts_result(result)
    if not pcm or sample_rate <= 0:
        return []
    stream = AudioByteStream(sample_rate=sample_rate, num_channels=1, progressive=True)
    frames = stream.push(pcm)
    frames.extend(stream.flush())
    return frames


def _pcm16_from_tts_result(result: TTSResult) -> tuple[bytes, int]:
    data = result.audio_data or b""
    if data.startswith(b"RIFF"):
        with wave.open(io.BytesIO(data), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            width = wav_file.getsampwidth()
            frames = wav_file.readframes(wav_file.getnframes())
        if width != 2:
            logger.warning("TTS WAV sample width is %s bytes; expected 16-bit PCM", width)
            return b"", result.sample_rate
        if channels > 1:
            frames = _downmix_interleaved_int16(frames, channels)
        return frames, sample_rate
    return data, result.sample_rate
