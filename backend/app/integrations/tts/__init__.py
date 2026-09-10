"""
TTS integration module.
"""
from .base import TTSProvider, TTSProviderError
from .mock_provider import MockTTSProvider
from .factory import TTSProviderFactory
from .providers.elevenlabs_tts import ElevenLabsTTSProvider
from .providers.local_tts import LocalTTSProvider

__all__ = [
    "TTSProvider",
    "TTSProviderError",
    "MockTTSProvider",
    "TTSProviderFactory",
    "ElevenLabsTTSProvider",
    "LocalTTSProvider",
]
