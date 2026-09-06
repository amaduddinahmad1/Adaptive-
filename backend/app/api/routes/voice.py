"""
Voice API routes.
"""
from typing import Any

from fastapi import APIRouter, HTTPException, Depends, Request

from app.schemas.voice_session import VoiceSessionCreate, VoiceSessionSchema
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
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Create a new voice session."""
    return await service.create_session(
        candidate_id=request.candidate_id,
        job_id=request.job_id,
        language=request.language,
    )


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


@router.post("/sessions/{session_id}/start")
async def start_interview(
    session_id: str,
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """Start the interview pipeline."""
    try:
        return await service.start_interview(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sessions/{session_id}/end")
async def end_interview(
    session_id: str,
    service: VoiceInterviewService = Depends(get_voice_service),
) -> Any:
    """End the interview pipeline."""
    try:
        return await service.end_interview(session_id)
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
