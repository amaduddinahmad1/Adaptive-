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
