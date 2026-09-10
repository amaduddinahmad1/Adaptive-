"""
STT integration module.
"""
from .base import STTProvider
from .mock_provider import MockSTTProvider
from .factory import STTProviderFactory
from .providers.whisper_local import WhisperLocalSTTProvider, WhisperModelLoadError

__all__ = [
    "STTProvider",
    "MockSTTProvider",
    "STTProviderFactory",
    "WhisperLocalSTTProvider",
    "WhisperModelLoadError",
]
