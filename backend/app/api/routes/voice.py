"""
Voice API routes.
"""
from typing import Any, List, Optional
import logging

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session, joinedload

from app.core.auth import get_optional_current_user, require_recruiter
from app.core.ownership import owned_application_ids, recruiter_owns_application
from app.db.session import get_db
from app.models.application import Application
from app.models.interview_result import InterviewResult
from app.models.user import ROLE_RECRUITER, User
from app.schemas.voice_session import (
    VoiceSessionAnswerRequest,
    VoiceSessionCreate,
    VoiceSessionEndResponse,
    VoiceSessionNextQuestionResponse,
    VoiceSessionSchema,
    VoiceSessionStartResponse,
)
from app.services.persistence.application_repository import (
    interview_invitation_is_expired,
    mark_interview_token_used,
)
from app.services.voice.service import VoiceInterviewService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])


def get_voice_service(request: Request) -> VoiceInterviewService:
    """Return the application-scoped VoiceInterviewService."""
    service = getattr(request.app.state, "voice_service", None)
    if service is None:
        service = VoiceInterviewService()
        request.app.state.voice_service = service
    return service


def _enforce_recruiter_session_access(
    session,
    user: Optional[User],
    db: Session,
) -> None:
    """Candidate callers (no auth) keep access. Authenticated recruiters are scoped."""
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if user is None:
        return
    if user.role != ROLE_RECRUITER:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if not recruiter_owns_application(db, user, session.application_id):
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions", response_model=List[VoiceSessionSchema])
async def list_sessions(
    service: VoiceInterviewService = Depends(get_voice_service),
    recruiter: User = Depends(require_recruiter),
    db: Session = Depends(get_db),
) -> Any:
    """List in-memory voice sessions owned through the recruiter's jobs."""
    sessions = await service.list_sessions()
    owned_ids = owned_application_ids(
        db,
        recruiter,
        [session.application_id for session in sessions],
    )
    return [session for session in sessions if session.application_id in owned_ids]


@router.post("/sessions", response_model=VoiceSessionSchema)
async def create_session(
    request: VoiceSessionCreate,
    db: Session = Depends(get_db),
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Create a new voice session for an existing Application."""
    application = (
        db.query(Application)
        .options(joinedload(Application.job_posting))
        .filter(Application.id == request.application_id)
        .first()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if interview_invitation_is_expired(application):
        raise HTTPException(
            status_code=400,
            detail="This interview invitation has expired.",
        )
    existing_result = (
        db.query(InterviewResult)
        .filter(InterviewResult.application_id == application.id)
        .first()
    )
    if existing_result is not None:
        raise HTTPException(
            status_code=409,
            detail="This interview has already been completed.",
        )
    try:
        return await service.create_session(
            application=application,
            language=request.language,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions/{session_id}", response_model=VoiceSessionSchema)
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    service: VoiceInterviewService = Depends(get_voice_service),
    user: Optional[User] = Depends(get_optional_current_user),
) -> Any:
    """Get session details."""
    session = await service.get_session(session_id)
    _enforce_recruiter_session_access(session, user, db)
    return session


@router.post("/sessions/{session_id}/start", response_model=VoiceSessionStartResponse)
async def start_interview(
    session_id: str,
    db: Session = Depends(get_db),
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Start the interview pipeline and return the LiveKit join contract."""
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    application = (
        db.query(Application)
        .options(joinedload(Application.job_posting))
        .filter(Application.id == session.application_id)
        .first()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if interview_invitation_is_expired(application):
        raise HTTPException(
            status_code=400,
            detail="This interview invitation has expired.",
        )
    try:
        result = await service.start_interview(session_id, application=application)
    except ValueError as e:
        message = str(e)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message)
    except RuntimeError:
        logger.error(
            "Interview intelligence could not start session %s",
            session_id,
            extra={"application_id": session.application_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=409,
            detail="This interview cannot be started because the job profile is not ready.",
        )
    except Exception:
        logger.error(
            "Unexpected error starting session %s",
            session_id,
            extra={"application_id": session.application_id},
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="The interview session is unavailable right now.",
        )
    if application.interview_token:
        mark_interview_token_used(db, application)
        db.commit()
    return result


@router.post("/sessions/{session_id}/end", response_model=VoiceSessionEndResponse)
async def end_interview(
    session_id: str,
    db: Session = Depends(get_db),
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """End the interview pipeline and persist a real FinalAssessmentReport when possible."""
    try:
        return await service.end_interview(session_id, db=db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions/{session_id}/status")
async def get_status(
    session_id: str,
    db: Session = Depends(get_db),
    service: VoiceInterviewService = Depends(get_voice_service),
    user: Optional[User] = Depends(get_optional_current_user),
) -> Any:
    """Get the status of an interview session."""
    session = await service.get_session(session_id)
    _enforce_recruiter_session_access(session, user, db)
    return {
        "session_id": session.session_id,
        "interview_status": session.interview_status,
        "connection_status": session.connection_status,
    }


@router.get(
    "/sessions/{session_id}/next-question",
    response_model=VoiceSessionNextQuestionResponse,
)
async def get_next_question(
    session_id: str,
    claim_opening: bool = False,
    owner_id: Optional[str] = None,
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Return the current/next Question Engine question for the LiveKit agent."""
    try:
        if claim_opening:
            return await service.claim_agent_opening(session_id, owner_id or "unknown")
        question = await service.get_next_question(session_id)
        runtime = service.bridge.get_runtime(session_id)
        session = await service.get_session(session_id)
        completed = bool(
            runtime is not None and (runtime.completed or runtime.terminated)
        )
        return {
            "question": question,
            "completed": completed,
            "allow_opening_speech": False,
            "action": "completed" if completed else "question",
            "question_turn_budget": getattr(session, "question_turn_budget", None),
            "completed_turns": getattr(session, "completed_turns", None),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/sessions/{session_id}/response")
async def process_candidate_response(
    session_id: str,
    request: VoiceSessionAnswerRequest,
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Evaluate a candidate answer and advance the real interview controller."""
    try:
        return await service.process_candidate_response(
            session_id,
            request.text,
            question_text=request.question_text,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
