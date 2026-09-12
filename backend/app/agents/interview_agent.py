"""
Interview voice agent using LiveKit Agents node overrides.

These STT/LLM/TTS node overrides still make synchronous/batch-style calls to our
existing Day 3 providers (WhisperLocalSTTProvider.transcribe(), MockInterviewBridge,
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
import time
import wave
from collections.abc import AsyncGenerator, AsyncIterable
from typing import Any

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

from app.integrations.pipecat.interview_bridge import MockInterviewBridge
from app.integrations.stt.providers.whisper_local import WhisperLocalSTTProvider
from app.integrations.tts.factory import TTSProviderFactory
from app.schemas.stt import STTConfig
from app.schemas.tts import TTSConfig, TTSResult

logger = logging.getLogger(__name__)

_DEFAULT_LANGUAGE = "en"
_ROOM_SESSION_PREFIX = "interview-"


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
        return "mock_interview_bridge"

    @property
    def provider(self) -> str:
        return "mock_interview_bridge"

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
    def __init__(self) -> None:
        super().__init__(
            instructions="You are conducting a structured voice interview.",
            stt=_PipelinePlaceholderSTT(),
            llm=_PipelinePlaceholderLLM(),
            tts=_PipelinePlaceholderTTS(),
        )
        self._whisper = WhisperLocalSTTProvider()
        self._bridge = MockInterviewBridge()

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

        forward_task = asyncio.create_task(_forward_input())
        try:
            async for event in vad_stream:
                if event.type == vad.VADEventType.START_OF_SPEECH:
                    yield stt.SpeechEvent(type=stt.SpeechEventType.START_OF_SPEECH)
                elif event.type == vad.VADEventType.END_OF_SPEECH:
                    speech_end_time = (
                        time.time() - event.silence_duration - event.inference_duration
                    )
                    yield stt.SpeechEvent(
                        type=stt.SpeechEventType.END_OF_SPEECH,
                        speech_end_time=speech_end_time,
                    )
                    transcript_event = await self._transcribe_vad_frames(event.frames)
                    if transcript_event is not None:
                        yield transcript_event
        finally:
            await utils.aio.cancel_and_wait(forward_task)
            await vad_stream.aclose()

    async def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: ModelSettings,
    ) -> str:
        transcript = _latest_user_transcript(chat_ctx)
        session_id = _interview_session_id()
        await self._bridge.process_candidate_response(transcript, session_id)
        reply = await self._bridge.get_next_question(session_id)
        if reply is None:
            return ""
        return reply.strip()

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

        result = await TTSProviderFactory.synthesize_with_fallback(
            spoken,
            TTSConfig(
                provider="elevenlabs",
                language=_DEFAULT_LANGUAGE,
                output_format="LINEAR16",
            ),
        )
        for frame in _audio_frames_from_tts_result(result):
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


def _interview_session_id() -> str:
    ctx = get_job_context(required=False)
    if ctx is None:
        return "local"
    name = (ctx.room.name or "").strip() or "local"
    if name.startswith(_ROOM_SESSION_PREFIX):
        return name[len(_ROOM_SESSION_PREFIX) :]
    return name


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
