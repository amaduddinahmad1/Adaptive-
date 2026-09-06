"""
Tests for STT abstractions.
"""
import pytest
from app.integrations.stt.factory import STTProviderFactory
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
