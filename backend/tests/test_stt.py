"""
Tests for STT abstractions.
"""
from types import SimpleNamespace

import pytest
from app.integrations.stt.factory import STTProviderFactory
from app.integrations.stt.providers.whisper_local import (
    WHISPER_TRANSCRIBE_OPTIONS,
    WhisperLocalSTTProvider,
)
from app.schemas.stt import STTConfig

@pytest.mark.asyncio
async def test_mock_stt_provider():
    provider = STTProviderFactory.get_provider("mock")
    assert "en" in provider.get_supported_languages()
    assert provider.get_provider_name() == "mock"
    
    config = STTConfig(provider="mock", language="en")
    result = await provider.transcribe(b"audio", config)
    
    assert result.text == "This is a mock transcription."
    assert result.confidence == 0.99
    
def test_stt_factory_unknown_provider():
    with pytest.raises(ValueError):
        STTProviderFactory.get_provider("unknown")


def test_whisper_load_uses_cpu_int8_and_configured_threads(monkeypatch):
    captured = {}

    class FakeWhisperModel:
        def __init__(self, size, **kwargs):
            captured["size"] = size
            captured.update(kwargs)

    import faster_whisper

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisperModel)
    monkeypatch.setenv("WHISPER_CPU_THREADS", "4")
    provider = WhisperLocalSTTProvider()
    provider._cpu_threads = 4
    provider._load_model()
    assert captured["size"] == provider._model_size
    assert captured["device"] == "cpu"
    assert captured["compute_type"] == "int8"
    assert captured["cpu_threads"] == 4
    assert captured["num_workers"] == 1


def test_whisper_decoding_uses_single_temperature_without_retries():
    captured = {}

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            captured.update(kwargs)
            return iter([]), SimpleNamespace(language="en")

    provider = WhisperLocalSTTProvider()
    provider._model = FakeModel()
    provider._transcribe_bytes(
        b"\x00\x00" * 320,
        "en",
        STTConfig(
            provider="whisper_local",
            language="en",
            sample_rate=16000,
            encoding="LINEAR16",
        ),
    )

    assert captured["temperature"] == 0.0
    assert not isinstance(captured["temperature"], (list, tuple))
    assert captured["vad_filter"] is False
    assert captured["beam_size"] == 1
    assert captured["best_of"] == 1
    assert captured["condition_on_previous_text"] is False
    assert captured["without_timestamps"] is True
    assert captured["word_timestamps"] is False
    assert captured["multilingual"] is False
    assert captured["log_progress"] is False
    assert captured["max_new_tokens"] == 224
    assert captured["task"] == "transcribe"
    assert WHISPER_TRANSCRIBE_OPTIONS["temperature"] == 0.0
    assert WHISPER_TRANSCRIBE_OPTIONS["vad_filter"] is False
    info = provider.model_runtime_info()
    assert info["device"] == "cpu"
    assert info["compute_type"] == "int8"
    assert info["model_size"]


def test_whisper_model_is_not_reinitialized_per_answer():
    loads = {"count": 0}

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            return iter([]), SimpleNamespace(language="en")

    provider = WhisperLocalSTTProvider()

    def _load():
        loads["count"] += 1
        return FakeModel()

    provider._load_model = _load
    config = STTConfig(
        provider="whisper_local",
        language="en",
        sample_rate=16000,
        encoding="LINEAR16",
    )
    provider._transcribe_bytes(b"\x00\x00" * 320, "en", config)
    provider._transcribe_bytes(b"\x00\x00" * 640, "en", config)
    assert loads["count"] == 1
    assert provider._model is not None


@pytest.mark.asyncio
async def test_whisper_transcribe_runs_off_the_event_loop():
    import inspect
    import time
    import asyncio

    source = inspect.getsource(WhisperLocalSTTProvider.transcribe)
    assert "asyncio.to_thread" in source

    provider = WhisperLocalSTTProvider()

    def _blocking(_audio, _language, _config):
        time.sleep(0.35)
        return "I used FastAPI with PostgreSQL in production.", {"language": "en", "segments": []}

    provider._transcribe_bytes = _blocking
    ticks = []

    async def heartbeat():
        deadline = time.perf_counter() + 0.45
        while time.perf_counter() < deadline:
            await asyncio.sleep(0.03)
            ticks.append(time.perf_counter())

    heart = asyncio.create_task(heartbeat())
    result = await provider.transcribe(
        b"\x00\x00" * 320,
        STTConfig(
            provider="whisper_local",
            language="en",
            sample_rate=16000,
            encoding="LINEAR16",
        ),
    )
    await heart
    assert result.text == "I used FastAPI with PostgreSQL in production."
    assert ticks, "heartbeat should run while Whisper is off the event loop"
    gaps = [later - earlier for earlier, later in zip(ticks, ticks[1:])]
    assert gaps
    assert max(gaps) < 0.25
