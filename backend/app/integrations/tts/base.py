"""
Abstract base class for TTS Providers.
"""
from abc import ABC, abstractmethod
from app.schemas.tts import TTSConfig, TTSResult


class TTSProviderError(Exception):
    """Catchable failure from a TTS provider (auth, quota, rate limit, network, etc.)."""


class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, config: TTSConfig) -> TTSResult:
        """Synthesize text into audio."""
        pass
        
    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        """Get list of supported language codes."""
        pass
        
    @abstractmethod
    def get_supported_voices(self, language: str) -> list[str]:
        """Get list of supported voices for a language."""
        pass
        
    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the provider's identifier."""
        pass
