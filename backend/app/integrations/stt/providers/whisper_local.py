"""
Local faster-whisper STT provider (CPU-only, int8).

Defaults to English (`language="en"`); pass STTConfig.language to override.
Model size defaults to "small" via WHISPER_MODEL_SIZE for laptop CPU use.

This environment does not have a working CUDA runtime, so the live worker
stays on CPU. Decoding is tuned for already-VAD-segmented interview turns:
one greedy pass, no temperature fallback retries, no inner VAD filter, and
a token cap so hallucination loops cannot inflate turn latency.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
import threading
import time
import wave
from typing import Any, AsyncIterator, Optional

from app.integrations.stt.base import STTProvider
from app.schemas.stt import STTConfig, STTResult

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_SIZE = "small"
_DEFAULT_LANGUAGE = "en"
_DEFAULT_DEVICE = "cpu"
_DEFAULT_COMPUTE_TYPE = "int8"
_CONTAINER_MAGIC = (b"RIFF", b"OggS", b"fLaC", b"ID3", b"\xff\xfb", b"\x1a\x45\xdf\xa3")

# faster-whisper defaults temperature to [0.0, 0.2, ..., 1.0] and retries on
# compression-ratio / log-prob thresholds. That extra decoding is the main
# source of multi-second STT delay on clear interview answers.
WHISPER_TRANSCRIBE_OPTIONS: dict[str, Any] = {
    "task": "transcribe",
    "beam_size": 1,
    "best_of": 1,
    "temperature": 0.0,
    "vad_filter": False,
    "condition_on_previous_text": False,
    "without_timestamps": True,
    "word_timestamps": False,
    "multilingual": False,
    "log_progress": False,
    "max_new_tokens": 224,
}


def _resolve_language(config: STTConfig) -> str:
    return (config.language or "").strip() or _DEFAULT_LANGUAGE


def resolve_whisper_cpu_threads() -> int:
    """Use WHISPER_CPU_THREADS when set, otherwise all detected CPU threads."""
    raw = (os.getenv("WHISPER_CPU_THREADS") or "").strip()
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return max(1, os.cpu_count() or 4)


class WhisperModelLoadError(RuntimeError):
    """Raised when the local Whisper model cannot be loaded."""


class WhisperLocalSTTProvider(STTProvider):
    def __init__(self) -> None:
        self._model_size = (
            os.getenv("WHISPER_MODEL_SIZE", _DEFAULT_MODEL_SIZE).strip() or _DEFAULT_MODEL_SIZE
        )
        self._device = _DEFAULT_DEVICE
        self._compute_type = _DEFAULT_COMPUTE_TYPE
        self._cpu_threads = resolve_whisper_cpu_threads()
        self._model: Optional[Any] = None
        self._infer_lock = threading.Lock()

    def model_runtime_info(self) -> dict[str, Any]:
        return {
            "model_size": self._model_size,
            "device": self._device,
            "compute_type": self._compute_type,
            "cpu_threads": self._cpu_threads,
            "model_loaded": self._model is not None,
        }

    def _ensure_model(self) -> Any:
        if self._model is None:
            with self._infer_lock:
                if self._model is None:
                    self._model = self._load_model()
        return self._model

    def _load_model(self) -> Any:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise WhisperModelLoadError(
                "Failed to load Whisper: the faster-whisper package is not installed. "
                "Install backend requirements (pip install -r requirements.txt) before "
                "using the whisper_local STT provider."
            ) from exc

        try:
            model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
                cpu_threads=self._cpu_threads,
                num_workers=1,
            )
        except Exception as exc:
            raise WhisperModelLoadError(
                f"Failed to load Whisper model '{self._model_size}' on CPU. "
                "Weights may not be downloaded yet, the size name may be invalid, "
                "or this machine may not have enough memory. "
                f"Original error: {exc}"
            ) from exc
        logger.info(
            "Loaded Whisper model=%s device=%s compute_type=%s cpu_threads=%s",
            self._model_size,
            self._device,
            self._compute_type,
            self._cpu_threads,
        )
        return model

    async def transcribe(self, audio_data: bytes, config: STTConfig) -> STTResult:
        start = time.perf_counter()
        language = _resolve_language(config)
        text, metadata = await asyncio.to_thread(
            self._transcribe_bytes, audio_data, language, config
        )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return STTResult(
            text=text,
            language=language,
            confidence=_confidence_from_metadata(metadata),
            processing_time_ms=elapsed_ms,
            provider=self.get_provider_name(),
            raw_metadata=metadata,
        )

    def _transcribe_bytes(
        self, audio_data: bytes, language: str, config: STTConfig
    ) -> tuple[str, Optional[dict[str, Any]]]:
        if not audio_data:
            return "", None

        audio_input, temp_path = self._prepare_audio(audio_data, config)
        model = self._ensure_model()
        try:
            with self._infer_lock:
                segments_iter, info = model.transcribe(
                    audio_input,
                    language=language,
                    **WHISPER_TRANSCRIBE_OPTIONS,
                )
                segments = list(segments_iter)
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

        text = " ".join(part for part in (seg.text.strip() for seg in segments) if part)
        metadata = {
            "language": info.language,
            "segments": segments,
            "model_size": self._model_size,
            "device": self._device,
            "compute_type": self._compute_type,
            "cpu_threads": self._cpu_threads,
        }
        return text, metadata

    def _prepare_audio(self, audio_data: bytes, config: STTConfig) -> tuple[Any, Optional[str]]:
        """Return (whisper input, optional temp path to delete)."""
        if audio_data.startswith(_CONTAINER_MAGIC):
            path = self._write_temp_audio(audio_data)
            return path, path

        encoding = (config.encoding or "LINEAR16").upper()
        if encoding == "LINEAR16":
            try:
                import numpy as np

                return _pcm16_to_float32(audio_data, config.sample_rate, np), None
            except ImportError:
                wav_bytes = _pcm16_to_wav(audio_data, config.sample_rate)
                path = self._write_temp_audio(wav_bytes)
                return path, path

        path = self._write_temp_audio(audio_data)
        return path, path

    @staticmethod
    def _write_temp_audio(audio_data: bytes) -> str:
        suffix = ".wav" if audio_data[:4] == b"RIFF" else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_data)
            return tmp.name

    async def transcribe_stream(
        self, audio_stream: AsyncIterator[bytes], config: STTConfig
    ) -> AsyncIterator[STTResult]:
        chunks: list[bytes] = []
        async for chunk in audio_stream:
            if chunk:
                chunks.append(chunk)
        yield await self.transcribe(b"".join(chunks), config)

    def get_supported_languages(self) -> list[str]:
        return [_DEFAULT_LANGUAGE]

    def get_provider_name(self) -> str:
        return "whisper_local"


def _pcm16_to_float32(pcm_data: bytes, sample_rate: int, np: Any) -> Any:
    """Convert mono 16-bit PCM to Whisper's 16 kHz float32 waveform."""
    audio = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
    if sample_rate and sample_rate != 16000 and audio.size > 1:
        duration = audio.size / float(sample_rate)
        target_len = max(1, int(round(duration * 16000)))
        x_old = np.linspace(0.0, 1.0, num=audio.size, endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=target_len, endpoint=False)
        audio = np.interp(x_new, x_old, audio).astype(np.float32)
    return audio


def _pcm16_to_wav(pcm_data: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return buffer.getvalue()


def _confidence_from_metadata(metadata: Optional[dict[str, Any]]) -> float:
    if not metadata:
        return 0.0
    segments = metadata.get("segments") or []
    if not segments:
        return 0.0
    scores = [
        max(0.0, min(1.0, 1.0 - float(getattr(seg, "no_speech_prob", 0.0))))
        for seg in segments
    ]
    return sum(scores) / len(scores)
