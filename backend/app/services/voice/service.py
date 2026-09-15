"""
Voice Interview Service.
"""
import uuid
import logging
from typing import Optional, Dict, Any
from app.models.application import Application
from app.schemas.voice_session import VoiceSessionSchema, InterviewStatus, ConnectionStatus
from app.core.config import settings
from app.integrations.livekit.config import LiveKitConfig
from app.integrations.livekit.service import LiveKitService
from app.integrations.stt.factory import STTProviderFactory
from app.integrations.pipecat.pipeline import InterviewPipeline
from app.integrations.pipecat.interview_bridge import MockInterviewBridge
from .session_manager import SessionManager

logger = logging.getLogger(__name__)

class VoiceInterviewService:
    def __init__(self, livekit_service: Optional[LiveKitService] = None):
        self.session_manager = SessionManager()
        self.pipelines: Dict[str, InterviewPipeline] = {}
        self.bridge = MockInterviewBridge()
        self.livekit = livekit_service or LiveKitService(
            LiveKitConfig(
                url=settings.livekit_url,
                api_key=settings.livekit_api_key,
                api_secret=settings.livekit_api_secret,
            )
        )

    async def create_session(
        self, application: Application, language: str = "en"
    ) -> VoiceSessionSchema:
        """Create an in-memory voice session bound to a validated Application."""
        if application.overall_eligible is False:
            raise ValueError("Application is not eligible for interview")

        session_id = str(uuid.uuid4())
        session = VoiceSessionSchema(
            session_id=session_id,
            application_id=application.id,
            candidate_id=str(application.candidate_id),
            job_id=str(application.job_posting_id),
            language=language,
        )
        self.session_manager.create_session(session)
        logger.info(
            f"Created session {session_id} for application {application.id}"
        )
        return session

    async def start_interview(self, session_id: str) -> Dict[str, Any]:
        """Start the interview pipeline for a session."""
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        if session.application_id is None:
            raise ValueError("Session is not linked to an application")

        stt_provider = STTProviderFactory.get_provider()

        pipeline = InterviewPipeline()
        await pipeline.start(
            session_id,
            stt_provider=stt_provider,
            bridge=self.bridge,
            language=session.language,
        )
        self.pipelines[session_id] = pipeline

        room_name = f"interview-{session_id}"
        identity = f"candidate-{session.candidate_id}"
        try:
            await self.livekit.create_room(room_name)
        except Exception:
            logger.warning(
                "LiveKit create_room failed for session %s; continuing with token issuance",
                session_id,
                exc_info=True,
            )
        token = self.livekit.generate_token(room_name, identity)

        session.interview_status = InterviewStatus.IN_PROGRESS
        session.connection_status = ConnectionStatus.CONNECTED
        logger.info(f"Started interview for session {session_id}")

        return {
            "status": "started",
            "session_id": session_id,
            "livekit_url": self.livekit.config.url,
            "room_name": room_name,
            "token": token,
            "identity": identity,
        }

    async def end_interview(self, session_id: str) -> Dict[str, Any]:
        """End the interview and clean up resources."""
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError("Session not found")

        pipeline = self.pipelines.get(session_id)
        if pipeline:
            await pipeline.stop()
            del self.pipelines[session_id]

        try:
            await self.livekit.delete_room(f"interview-{session_id}")
        except Exception:
            logger.warning(
                "Best-effort LiveKit room delete failed for session %s",
                session_id,
                exc_info=True,
            )

        session.interview_status = InterviewStatus.COMPLETED
        session.connection_status = ConnectionStatus.DISCONNECTED
        logger.info(f"Ended interview for session {session_id}")

        return {"status": "ended", "session_id": session_id}

    async def get_session(self, session_id: str) -> Optional[VoiceSessionSchema]:
        """Get session details."""
        return self.session_manager.get_session(session_id)

    async def process_audio_chunk(self, session_id: str, audio_data: bytes) -> Optional[Dict[str, Any]]:
        """Process incoming audio for a session."""
        pipeline = self.pipelines.get(session_id)
        if not pipeline:
            return None
            
        processed_audio = await pipeline.process_audio(audio_data)
        return {"processed": True, "audio": processed_audio}
