"""
Pipecat Interview Pipeline orchestration.
"""
import logging
from typing import Optional

from app.integrations.pipecat.interview_bridge import InterviewBridge
from app.integrations.stt.base import STTProvider
from app.integrations.stt.factory import STTProviderFactory
from app.integrations.tts.base import TTSProvider
from app.integrations.tts.factory import TTSProviderFactory
from app.schemas.stt import STTConfig
from app.schemas.tts import TTSConfig

logger = logging.getLogger(__name__)


class InterviewPipeline:
    """
    Orchestrates the Audio -> STT -> Interview Intelligence -> TTS -> Audio pipeline.
    This uses Pipecat logic conceptually, providing the structure for real implementation.
    """
    def __init__(self):
        self.session_id: Optional[str] = None
        self.stt_provider: Optional[STTProvider] = None
        self.tts_provider: Optional[TTSProvider] = None
        self.bridge: Optional[InterviewBridge] = None
        self.language: str = "en"
        self.is_running: bool = False

    async def start(
        self,
        session_id: str,
        stt_provider: Optional[STTProvider] = None,
        tts_provider: Optional[TTSProvider] = None,
        bridge: Optional[InterviewBridge] = None,
        language: str = "en",
    ):
        """Start the pipeline."""
        self.session_id = session_id
        self.stt_provider = stt_provider
        self.tts_provider = tts_provider
        self.bridge = bridge
        self.language = language or "en"
        self.is_running = True
        logger.info(f"Started pipeline for session {session_id}")

    async def stop(self):
        """Stop the pipeline."""
        self.is_running = False
        logger.info(f"Stopped pipeline for session {self.session_id}")

    async def process_audio(self, audio_data: bytes) -> Optional[bytes]:
        """Transcribe candidate audio, obtain an AI reply, and synthesize speech."""
        if not self.is_running:
            return None
        if not audio_data:
            return None

        stt_provider = self.stt_provider or STTProviderFactory.get_provider()
        stt_config = STTConfig(
            provider=stt_provider.get_provider_name(),
            language=self.language,
        )
        stt_result = await stt_provider.transcribe(audio_data, stt_config)
        transcript = (stt_result.text or "").strip()
        if not transcript:
            logger.debug(
                "STT produced an empty transcript for session %s; skipping TTS",
                self.session_id,
            )
            return None

        reply_text = await self._next_ai_utterance(transcript)
        if not reply_text:
            logger.info(
                "No AI response text to synthesize for session %s",
                self.session_id,
            )
            return None

        tts_config = TTSConfig(
            provider="elevenlabs",
            language=self.language,
            output_format="wav",
        )
        tts_result = await TTSProviderFactory.synthesize_with_fallback(reply_text, tts_config)
        return tts_result.audio_data

    async def _next_ai_utterance(self, transcript: str) -> Optional[str]:
        if self.bridge is None or self.session_id is None:
            return None
        result = await self.bridge.process_candidate_response(transcript, self.session_id)
        if isinstance(result, dict):
            spoken_reply = (result.get("spoken_reply") or "").strip()
            if spoken_reply:
                return spoken_reply
            if result.get("status") == "ignored":
                return None
            next_question = result.get("next_question")
            if next_question:
                return str(next_question).strip()
            if result.get("completed"):
                return None
        reply = await self.bridge.get_next_question(self.session_id)
        if reply is None:
            return None
        reply_text = reply.strip()
        return reply_text or None

    def get_pipeline_status(self) -> str:
        """Return the current status."""
        return "RUNNING" if self.is_running else "STOPPED"
