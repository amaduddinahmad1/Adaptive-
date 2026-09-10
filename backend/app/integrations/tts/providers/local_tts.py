"""
Local MMS-TTS fallback (CPU-only) using facebook/mms-tts-eng.

Expects English text, same convention as the other TTS adapters.
This is a lower-quality fallback, not the primary provider.
"""
from __future__ import annotations

import asyncio
import io
import time
import wave
from typing import Any

from app.integrations.tts.base import TTSProvider, TTSProviderError
from app.schemas.tts import TTSConfig, TTSResult

_MODEL_ID = "facebook/mms-tts-eng"
_DEFAULT_PCM_RATE = 16000
_VOICE_ID = "mms-tts-eng"


class LocalTTSProvider(TTSProvider):
    def __init__(self) -> None:
        self._tokenizer, self._model = self._load_model()
        self._sample_rate = int(
            getattr(self._model.config, "sampling_rate", _DEFAULT_PCM_RATE)
            or _DEFAULT_PCM_RATE
        )

    def _load_model(self) -> tuple[Any, Any]:
        try:
            import torch
            from transformers import AutoTokenizer, VitsModel
        except ImportError as exc:
            raise TTSProviderError(
                "Failed to load local TTS: transformers and torch must be installed. "
                "Install backend requirements (pip install -r requirements.txt) before "
                "using the local_fallback TTS provider."
            ) from exc

        try:
            tokenizer = AutoTokenizer.from_pretrained(_MODEL_ID)
            model = VitsModel.from_pretrained(_MODEL_ID)
            model.to("cpu")
            model.eval()
        except Exception as exc:
            raise TTSProviderError(
                f"Failed to load MMS-TTS model '{_MODEL_ID}' on CPU. "
                "Weights may not be downloaded yet, or this machine may not have "
                f"enough memory. Original error: {exc}"
            ) from exc

        # Keep a reference so inference always uses the CPU torch module we imported.
        self._torch = torch
        return tokenizer, model

    async def synthesize(self, text: str, config: TTSConfig) -> TTSResult:
        start = time.perf_counter()
        sample_rate, wrap_wav = _map_output_format(config.output_format, self._sample_rate)

        try:
            pcm_data = await asyncio.to_thread(self._synthesize_pcm, text)
        except TTSProviderError:
            raise
        except Exception as exc:
            raise TTSProviderError(f"Local MMS-TTS synthesis failed: {exc}") from exc

        audio_data = _pcm_to_wav(pcm_data, sample_rate) if wrap_wav else pcm_data
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
                "voice_id": _VOICE_ID,
                "device": "cpu",
            },
        )

    def _synthesize_pcm(self, text: str) -> bytes:
        stripped = (text or "").strip()
        if not stripped:
            return b""

        torch = self._torch
        inputs = self._tokenizer(stripped, return_tensors="pt")
        inputs = {key: value.to("cpu") for key, value in inputs.items()}

        with torch.no_grad():
            waveform = self._model(**inputs).waveform

        audio = waveform.squeeze().detach().cpu().float()
        if audio.ndim > 1:
            audio = audio.mean(dim=0)
        audio = audio.clamp(-1.0, 1.0)
        return (audio * 32767.0).to(torch.int16).numpy().tobytes()

    def get_supported_languages(self) -> list[str]:
        return ["en"]

    def get_supported_voices(self, language: str) -> list[str]:
        return [_VOICE_ID]

    def get_provider_name(self) -> str:
        return "local_fallback"


def _map_output_format(output_format: str, model_rate: int) -> tuple[int, bool]:
    """Return (sample_rate, wrap_pcm_as_wav). Local MMS-TTS only emits PCM."""
    fmt = (output_format or "wav").strip().lower()
    if fmt in {"wav", "wave"}:
        return model_rate, True
    if fmt in {"linear16", "pcm"} or fmt.startswith("pcm_"):
        return model_rate, False
    return model_rate, True


def _pcm_to_wav(pcm_data: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    return buffer.getvalue()
