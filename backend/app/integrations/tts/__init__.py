"""
TTS integration module.
"""
from .base import TTSProvider
from .mock_provider import MockTTSProvider
from .factory import TTSProviderFactory

__all__ = ["TTSProvider", "MockTTSProvider", "TTSProviderFactory"]
