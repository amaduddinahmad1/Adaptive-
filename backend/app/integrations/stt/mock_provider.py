"""
Mock STT Provider for testing and local development.
"""
import asyncio
from typing import AsyncIterator
from app.integrations.stt.base import STTProvider
from app.schemas.stt import STTConfig, STTResult

class MockSTTProvider(STTProvider):
    async def transcribe(self, audio_data: bytes, config: STTConfig) -> STTResult:
        # Simulate processing delay based on size
        await asyncio.sleep(0.1)
        return STTResult(
            text="This is a mock transcription.",
            language=config.language,
            confidence=0.99,
            processing_time_ms=100.0,
            provider=self.get_provider_name()
        )
        
    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes], config: STTConfig) -> AsyncIterator[STTResult]:
        async for chunk in audio_stream:
            await asyncio.sleep(0.05)
            yield STTResult(
                text="mock text",
                language=config.language,
                confidence=0.99,
                processing_time_ms=50.0,
                provider=self.get_provider_name()
            )
            
    def get_supported_languages(self) -> list[str]:
        return ["en", "ur", "ru"]
        
    def get_provider_name(self) -> str:
        return "mock"
