"""
Mock TTS Provider for testing and local development.
"""
import asyncio
from app.integrations.tts.base import TTSProvider
from app.schemas.tts import TTSConfig, TTSResult

class MockTTSProvider(TTSProvider):
    async def synthesize(self, text: str, config: TTSConfig) -> TTSResult:
        # Simulate generation delay based on text length
        await asyncio.sleep(0.1)
        mock_audio = b"RIFFmockaudiobytes"
        return TTSResult(
            audio_data=mock_audio,
            audio_format=config.output_format,
            language=config.language,
            processing_time_ms=100.0,
            provider=self.get_provider_name(),
            sample_rate=16000
        )
        
    def get_supported_languages(self) -> list[str]:
        return ["en", "ur", "ru"]
        
    def get_supported_voices(self, language: str) -> list[str]:
        return ["mock-voice-1", "mock-voice-2"]
        
    def get_provider_name(self) -> str:
        return "mock"
