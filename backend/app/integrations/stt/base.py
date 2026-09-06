"""
Abstract base class for STT Providers.
"""
from abc import ABC, abstractmethod
from typing import AsyncIterator
from app.schemas.stt import STTConfig, STTResult

class STTProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio_data: bytes, config: STTConfig) -> STTResult:
        """Transcribe a complete audio buffer."""
        pass
        
    @abstractmethod
    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes], config: STTConfig) -> AsyncIterator[STTResult]:
        """Transcribe an audio stream."""
        pass
        
    @abstractmethod
    def get_supported_languages(self) -> list[str]:
        """Get list of supported language codes."""
        pass
        
    @abstractmethod
    def get_provider_name(self) -> str:
        """Get the provider's identifier."""
        pass
