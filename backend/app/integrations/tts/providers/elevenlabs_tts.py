"""
ElevenLabs TTS provider using eleven_multilingual_v2 (Urdu-script input).

Requires ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID. Transliteration of
Roman Urdu is expected to happen upstream; this adapter sends the given
text to ElevenLabs unchanged.
"""
from __future__ import annotations

import asyncio
import io
import os
import time
import wave
from typing import Any, Optional

from app.integrations.tts.base import TTSProvider, TTSProviderError
from app.schemas.tts import TTSConfig, TTSResult

_MODEL_ID = "eleven_multilingual_v2"
_DEFAULT_PCM_RATE = 16000


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self) -> None:
        api_key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
        voice_id = (os.getenv("ELEVENLABS_VOICE_ID") or "").strip()
        if not api_key:
            raise TTSProviderError(
                "ELEVENLABS_API_KEY is not set. Set it in the environment before using "
                "the elevenlabs TTS provider."
            )
        if not voice_id:
            raise TTSProviderError(
                "ELEVENLABS_VOICE_ID is not set. Set it to a voice ID from the "
                "ElevenLabs voice library before using the elevenlabs TTS provider."
            )
        self._api_key = api_key
        self._voice_id = voice_id
        self._client = self._create_client()

    def _create_client(self) -> Any:
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError as exc:
            raise TTSProviderError(
                "Failed to load ElevenLabs: the elevenlabs package is not installed. "
                "Install backend requirements (pip install -r requirements.txt) before "
                "using the elevenlabs TTS provider."
            ) from exc

        try:
            return ElevenLabs(api_key=self._api_key)
        except Exception as exc:
            raise TTSProviderError(
                f"Failed to initialize the ElevenLabs client: {exc}"
            ) from exc

    async def synthesize(self, text: str, config: TTSConfig) -> TTSResult:
        start = time.perf_counter()
        voice_id = (config.voice_id or "").strip() or self._voice_id
        eleven_format, sample_rate, wrap_wav = _map_output_format(config.output_format)

        try:
            audio_data = await asyncio.to_thread(
                self._convert, text, voice_id, eleven_format
            )
        except TTSProviderError:
            raise
        except Exception as exc:
            raise TTSProviderError(_format_api_failure(exc)) from exc

        if wrap_wav:
            audio_data = _pcm_to_wav(audio_data, sample_rate)

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return TTSResult(
            audio_data=audio_data,
            audio_format=config.output_format,
            language=config.language,
            processing_time_ms=elapsed_ms,
            provider=self.get_provider_name(),
            sample_rate=sample_rate,
            raw_metadata={
                "model_id": _MODEL_ID,
                "voice_id": voice_id,
                "elevenlabs_output_format": eleven_format,
            },
        )

    def _convert(self, text: str, voice_id: str, output_format: str) -> bytes:
        try:
            audio = self._client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=_MODEL_ID,
                output_format=output_format,
            )
            return _collect_audio_bytes(audio)
        except TTSProviderError:
            raise
        except Exception as exc:
            raise TTSProviderError(_format_api_failure(exc)) from exc

    def get_supported_languages(self) -> list[str]:
        return ["en"]

    def get_supported_voices(self, language: str) -> list[str]:
        return [self._voice_id]

    def get_provider_name(self) -> str:
        return "elevenlabs"


def _map_output_format(output_format: str) -> tuple[str, int, bool]:
    """Return (elevenlabs_format, sample_rate, wrap_pcm_as_wav)."""
    fmt = (output_format or "wav").strip().lower()
    if fmt in {"wav", "wave", "linear16", "pcm"}:
        return f"pcm_{_DEFAULT_PCM_RATE}", _DEFAULT_PCM_RATE, fmt in {"wav", "wave"}
    if fmt == "mp3":
        return "mp3_44100_128", 44100, False
    if fmt.startswith("pcm_"):
        rate = _parse_trailing_rate(fmt, _DEFAULT_PCM_RATE)
        return fmt, rate, False
    if fmt.startswith("mp3_"):
        return fmt, _parse_mp3_rate(fmt), False
    return f"pcm_{_DEFAULT_PCM_RATE}", _DEFAULT_PCM_RATE, True


def _parse_trailing_rate(fmt: str, default: int) -> int:
    try:
        return int(fmt.rsplit("_", 1)[-1])
    except ValueError:
        return default


def _parse_mp3_rate(fmt: str) -> int:
    parts = fmt.split("_")
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return 44100


def _collect_audio_bytes(audio: Any) -> bytes:
    if audio is None:
        return b""
    if isinstance(audio, (bytes, bytearray, memoryview)):
        return bytes(audio)
    chunks: list[bytes] = []
    for chunk in audio:
        if isinstance(chunk, (bytes, bytearray, memoryview)):
            chunks.append(bytes(chunk))
    return b"".join(chunks)


def _pcm_to_wav(pcm_data: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return buffer.getvalue()


def _format_api_failure(exc: Exception) -> str:
    status = _extract_status_code(exc)
    detail = str(exc).strip() or exc.__class__.__name__
    if status is not None:
        return (
            f"ElevenLabs TTS request failed (HTTP {status}): {detail}"
        )
    return f"ElevenLabs TTS request failed: {detail}"


def _extract_status_code(exc: Exception) -> Optional[int]:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None
