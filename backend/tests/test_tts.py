"""
Tests for TTS abstractions.
"""
import pytest
from app.integrations.tts.factory import TTSProviderFactory
from app.schemas.tts import TTSConfig

@pytest.mark.asyncio
async def test_mock_tts_provider():
    provider = TTSProviderFactory.get_provider("mock")
    assert "en" in provider.get_supported_languages()
    assert provider.get_provider_name() == "mock"
    assert "mock-voice-1" in provider.get_supported_voices("en")
    
    config = TTSConfig(provider="mock", language="en")
    result = await provider.synthesize("hello world", config)
    
    assert result.audio_data == b"RIFFmockaudiobytes"
    assert result.language == "en"

def test_tts_factory_unknown_provider():
    with pytest.raises(ValueError):
        TTSProviderFactory.get_provider("unknown")


@pytest.mark.asyncio
async def test_uncached_tts_provider_init_does_not_block_event_loop():
    import time
    import asyncio

    from app.schemas.tts import TTSResult

    class SlowInitProvider:
        def __init__(self):
            time.sleep(0.35)

        async def synthesize(self, text, config):
            return TTSResult(
                audio_data=b"pcm",
                audio_format="LINEAR16",
                language="en",
                processing_time_ms=1.0,
                provider="slow_init",
                sample_rate=16000,
            )

        def get_supported_languages(self):
            return ["en"]

        def get_supported_voices(self, language):
            return ["slow"]

        def get_provider_name(self):
            return "slow_init"

    TTSProviderFactory.register_provider("slow_init", SlowInitProvider)
    TTSProviderFactory._instances.pop("slow_init", None)
    ticks = []

    async def heartbeat():
        deadline = time.perf_counter() + 0.45
        while time.perf_counter() < deadline:
            await asyncio.sleep(0.03)
            ticks.append(time.perf_counter())

    heart = asyncio.create_task(heartbeat())
    try:
        await TTSProviderFactory._aget_provider("slow_init")
        await heart
    finally:
        TTSProviderFactory._instances.pop("slow_init", None)
        TTSProviderFactory._providers.pop("slow_init", None)

    assert ticks, "heartbeat should run while provider construction is off-loop"
    gaps = [later - earlier for earlier, later in zip(ticks, ticks[1:])]
    assert gaps
    assert max(gaps) < 0.25


def test_warmup_blocking_providers_does_not_raise_without_keys(monkeypatch):
    from app.integrations.tts.factory import warmup_blocking_providers

    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    TTSProviderFactory._instances.pop("elevenlabs", None)
    warmup_blocking_providers()


def test_tts_factory_reuses_cached_provider():
    first = TTSProviderFactory.get_provider("mock")
    second = TTSProviderFactory.get_provider("mock")
    assert first is second


def test_elevenlabs_convert_enables_streaming_latency_optimization():
    from types import SimpleNamespace

    from app.integrations.tts.providers.elevenlabs_tts import (
        ElevenLabsTTSProvider,
        _OPTIMIZE_STREAMING_LATENCY,
    )

    calls = []

    class FakeSpeech:
        def convert(self, **kwargs):
            calls.append(kwargs)
            return [b"\x00\x00"]

    provider = ElevenLabsTTSProvider.__new__(ElevenLabsTTSProvider)
    provider._voice_id = "voice"
    provider._client = SimpleNamespace(text_to_speech=FakeSpeech())
    audio = provider._convert("What did you build with FastAPI?", "voice", "pcm_16000")
    assert audio == b"\x00\x00"
    assert calls[0]["optimize_streaming_latency"] == 3
    assert _OPTIMIZE_STREAMING_LATENCY == 3
    assert calls[0]["model_id"]


@pytest.mark.asyncio
async def test_elevenlabs_pcm_stream_yields_chunks_before_completion():
    from types import SimpleNamespace

    from app.integrations.tts.providers.elevenlabs_tts import ElevenLabsTTSProvider
    from app.schemas.tts import TTSConfig

    class FakeSpeech:
        def convert(self, **kwargs):
            yield b"\x01\x00"
            yield b"\x02\x00"

    provider = ElevenLabsTTSProvider.__new__(ElevenLabsTTSProvider)
    provider._voice_id = "voice"
    provider._api_key = "test"
    provider._client = SimpleNamespace(text_to_speech=FakeSpeech())
    chunks = [
        chunk
        async for chunk in provider.synthesize_pcm_stream(
            "Next question.",
            TTSConfig(provider="elevenlabs", language="en", output_format="LINEAR16"),
        )
    ]
    assert chunks == [b"\x01\x00", b"\x02\x00"]

