"""
Voice API routes.
"""
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.application import Application
from app.schemas.voice_session import (
    VoiceSessionAnswerRequest,
    VoiceSessionCreate,
    VoiceSessionEndResponse,
    VoiceSessionNextQuestionResponse,
    VoiceSessionSchema,
    VoiceSessionStartResponse,
)
from app.services.voice.service import VoiceInterviewService

router = APIRouter(prefix="/voice", tags=["voice"])


def get_voice_service(request: Request) -> VoiceInterviewService:
    """Return the application-scoped VoiceInterviewService."""
    service = getattr(request.app.state, "voice_service", None)
    if service is None:
        service = VoiceInterviewService()
        request.app.state.voice_service = service
    return service


@router.post("/sessions", response_model=VoiceSessionSchema)
async def create_session(
    request: VoiceSessionCreate,
    db: Session = Depends(get_db),
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Create a new voice session for an existing Application."""
    application = (
        db.query(Application).filter(Application.id == request.application_id).first()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
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
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Get session details."""
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
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
        db.query(Application).filter(Application.id == session.application_id).first()
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        return await service.start_interview(session_id, application=application)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Get the status of an interview session."""
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
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
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Return the current/next Question Engine question for the LiveKit agent."""
    try:
        question = await service.get_next_question(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"question": question}


@router.post("/sessions/{session_id}/response")
async def process_candidate_response(
    session_id: str,
    request: VoiceSessionAnswerRequest,
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Evaluate a candidate answer and advance the real interview controller."""
    try:
        return await service.process_candidate_response(session_id, request.text)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
