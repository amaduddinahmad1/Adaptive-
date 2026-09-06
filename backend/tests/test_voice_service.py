"""
Tests for Voice Service.
"""
import pytest
from app.services.voice.service import VoiceInterviewService
from app.schemas.voice_session import InterviewStatus, ConnectionStatus

@pytest.mark.asyncio
async def test_voice_interview_service_lifecycle():
    service = VoiceInterviewService()
    
    # Create
    session = await service.create_session("cand_1", "job_1")
    assert session.candidate_id == "cand_1"
    assert session.interview_status == InterviewStatus.PENDING
    
    # Retrieve
    retrieved = await service.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id
    
    # Start
    start_res = await service.start_interview(session.session_id)
    assert start_res["status"] == "started"
    
    retrieved = await service.get_session(session.session_id)
    assert retrieved.interview_status == InterviewStatus.IN_PROGRESS
    assert retrieved.connection_status == ConnectionStatus.CONNECTED
    
    # End
    end_res = await service.end_interview(session.session_id)
    assert end_res["status"] == "ended"
    
    retrieved = await service.get_session(session.session_id)
    assert retrieved.interview_status == InterviewStatus.COMPLETED
    assert retrieved.connection_status == ConnectionStatus.DISCONNECTED

@pytest.mark.asyncio
async def test_voice_service_invalid_session():
    service = VoiceInterviewService()
    with pytest.raises(ValueError):
        await service.start_interview("invalid_id")
