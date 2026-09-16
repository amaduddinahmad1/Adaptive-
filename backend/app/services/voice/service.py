"""
Voice Interview Service.
"""
import uuid
import logging
from typing import Optional, Dict, Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.interview_result import InterviewResult
from app.schemas.voice_session import VoiceSessionSchema, InterviewStatus, ConnectionStatus
from app.core.config import settings
from app.integrations.livekit.config import LiveKitConfig
from app.integrations.livekit.service import LiveKitService
from app.integrations.stt.factory import STTProviderFactory
from app.integrations.pipecat.pipeline import InterviewPipeline
from app.integrations.pipecat.interview_bridge import InterviewIntelligenceBridge
from app.services.persistence.application_repository import create_interview_result
from .session_manager import SessionManager

logger = logging.getLogger(__name__)

class VoiceInterviewService:
    def __init__(self, livekit_service: Optional[LiveKitService] = None):
        self.session_manager = SessionManager()
        self.pipelines: Dict[str, InterviewPipeline] = {}
        self.bridge = InterviewIntelligenceBridge()
        self._application_context: Dict[str, Dict[str, Any]] = {}
        self.livekit = livekit_service or LiveKitService(
            LiveKitConfig(
                url=settings.livekit_url,
                api_key=settings.livekit_api_key,
                api_secret=settings.livekit_api_secret,
            )
        )

    def _store_application_context(self, session_id: str, application: Application) -> None:
        self._application_context[session_id] = {
            "application_id": application.id,
            "candidate_id": application.candidate_id,
            "job_posting_id": application.job_posting_id,
            "candidate_profile": application.candidate_profile,
            "job_profile_snapshot": application.job_profile_snapshot,
        }

    def _initialize_interview_intelligence(
        self, session_id: str, application: Optional[Application] = None
    ) -> None:
        if application is not None:
            self._store_application_context(session_id, application)
        context = self._application_context.get(session_id)
        if context is None:
            raise ValueError("Session is not linked to an application")
        self.bridge.initialize(session_id, **context)

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
        self._store_application_context(session_id, application)
        logger.info(
            f"Created session {session_id} for application {application.id}"
        )
        return session

    async def start_interview(
        self, session_id: str, application: Optional[Application] = None
    ) -> Dict[str, Any]:
        """Start the interview pipeline for a session."""
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        if session.application_id is None:
            raise ValueError("Session is not linked to an application")
        if application is not None and application.id != session.application_id:
            raise ValueError("Application does not match this session")

        self._initialize_interview_intelligence(session_id, application)
        first_question = await self.bridge.get_next_question(session_id)
        session.current_question = first_question

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

    async def end_interview(
        self, session_id: str, db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """End the interview, clean up resources, then persist a real assessment if possible."""
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

        persistence = self._persist_completion(session_id, db)
        return {
            "status": "ended",
            "session_id": session_id,
            **persistence,
        }

    def _persist_completion(
        self, session_id: str, db: Optional[Session]
    ) -> Dict[str, Any]:
        """Persist one InterviewResult from retained InterviewRuntime evidence.

        InterviewRuntime is the source of truth for application_id and must remain
        available through this call. Never writes placeholder or canned scores.
        """
        runtime = self.bridge.get_runtime(session_id)
        application_id = runtime.application_id if runtime is not None else None
        empty = {
            "application_id": application_id,
            "interview_result_id": None,
            "assessment_status": "not_persistable",
            "recommendation": None,
            "interview_eligibility_result": None,
        }

        if runtime is None or not runtime.evaluations:
            empty["detail"] = (
                "Final assessment is not persistable yet because this interview "
                "has no genuine answer evaluations."
            )
            return empty

        if db is None:
            logger.warning(
                "Session %s has genuine evaluations but no database session; "
                "skipping InterviewResult persistence",
                session_id,
            )
            empty["detail"] = (
                "Final assessment is not persistable yet because no database "
                "session was provided."
            )
            return empty

        application = (
            db.query(Application)
            .filter(Application.id == runtime.application_id)
            .first()
        )
        if application is None:
            empty["detail"] = (
                "Application not found; InterviewResult was not created."
            )
            return empty

        empty["application_id"] = application.id
        if application.overall_eligible is False:
            empty["detail"] = (
                "Application is not eligible for interview; InterviewResult was not created."
            )
            return empty

        existing = (
            db.query(InterviewResult)
            .filter(InterviewResult.application_id == application.id)
            .first()
        )
        if existing is not None:
            return {
                "application_id": application.id,
                "interview_result_id": existing.id,
                "assessment_status": "already_persisted",
                "recommendation": existing.recommendation,
                "interview_eligibility_result": existing.interview_eligibility_result,
                "detail": None,
            }

        artifacts = self.bridge.build_completion_assessment(session_id)
        if artifacts is None:
            empty["detail"] = (
                "Final assessment is not persistable yet because this interview "
                "has no genuine answer evaluations."
            )
            return empty

        report, gap_analysis = artifacts
        try:
            interview_result = create_interview_result(
                db,
                application=application,
                final_report=report,
                interview_plan=runtime.plan,
                qa_transcript=list(runtime.transcript),
                gap_analysis=gap_analysis,
            )
            db.commit()
            db.refresh(interview_result)
        except IntegrityError:
            db.rollback()
            interview_result = (
                db.query(InterviewResult)
                .filter(InterviewResult.application_id == application.id)
                .first()
            )
            if interview_result is None:
                raise
            return {
                "application_id": application.id,
                "interview_result_id": interview_result.id,
                "assessment_status": "already_persisted",
                "recommendation": interview_result.recommendation,
                "interview_eligibility_result": interview_result.interview_eligibility_result,
                "detail": None,
            }

        logger.info(
            "Persisted InterviewResult %s for application %s (session %s)",
            interview_result.id,
            application.id,
            session_id,
        )
        return {
            "application_id": application.id,
            "interview_result_id": interview_result.id,
            "assessment_status": "persisted",
            "recommendation": report.recommendation,
            "interview_eligibility_result": report.eligibility_result,
            "detail": None,
        }

    async def get_session(self, session_id: str) -> Optional[VoiceSessionSchema]:
        """Get session details."""
        return self.session_manager.get_session(session_id)

    async def get_next_question(self, session_id: str) -> Optional[str]:
        """Return the current or next Question Engine question for a live session."""
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        question = await self.bridge.get_next_question(session_id)
        session.current_question = question
        return question

    async def process_candidate_response(
        self, session_id: str, text: str
    ) -> Dict[str, Any]:
        """Evaluate a candidate answer with the real assessment path and advance."""
        session = self.session_manager.get_session(session_id)
        if not session:
            raise ValueError("Session not found")
        result = await self.bridge.process_candidate_response(text, session_id)
        next_question = await self.bridge.get_next_question(session_id)
        session.current_question = next_question
        result["next_question"] = next_question
        return result

    async def process_audio_chunk(self, session_id: str, audio_data: bytes) -> Optional[Dict[str, Any]]:
        """Process incoming audio for a session."""
        pipeline = self.pipelines.get(session_id)
        if not pipeline:
            return None
            
        processed_audio = await pipeline.process_audio(audio_data)
        return {"processed": True, "audio": processed_audio}
