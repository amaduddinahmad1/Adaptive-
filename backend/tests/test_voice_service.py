"""
Tests for Voice Service.
"""
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from app.services.voice.service import VoiceInterviewService
from app.schemas.voice_session import InterviewStatus, ConnectionStatus
from app.integrations.livekit.config import LiveKitConfig
from app.integrations.livekit.service import LiveKitService


class _FailingLiveKit:
    """Stub LiveKit layer that raises on room create/delete."""

    def __init__(self):
        self.config = LiveKitConfig(
            url="http://localhost:7880",
            api_key="test-api-key",
            api_secret="test-api-secret-not-real",
        )

    async def create_room(self, room_name: str):
        raise RuntimeError("create_room failed")

    def generate_token(self, room_name: str, participant_identity: str) -> str:
        return f"token-for-{room_name}-{participant_identity}"

    async def delete_room(self, room_name: str):
        raise RuntimeError("delete_room failed")

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
    assert start_res["session_id"] == session.session_id
    assert start_res["room_name"] == f"interview-{session.session_id}"
    assert start_res["identity"] == "candidate-cand_1"
    assert start_res["token"] == (
        f"mock_token_interview-{session.session_id}_candidate-cand_1"
    )
    assert "livekit_url" in start_res
    
    retrieved = await service.get_session(session.session_id)
    assert retrieved.interview_status == InterviewStatus.IN_PROGRESS
    assert retrieved.connection_status == ConnectionStatus.CONNECTED
    assert "token" not in retrieved.model_dump()
    
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


@pytest.mark.asyncio
async def test_start_succeeds_when_livekit_create_room_fails():
    service = VoiceInterviewService(livekit_service=_FailingLiveKit())
    session = await service.create_session("cand_1", "job_1")

    start_res = await service.start_interview(session.session_id)

    assert start_res["status"] == "started"
    assert start_res["session_id"] == session.session_id
    assert start_res["room_name"] == f"interview-{session.session_id}"
    assert start_res["identity"] == "candidate-cand_1"
    assert start_res["token"] == (
        f"token-for-interview-{session.session_id}-candidate-cand_1"
    )
    retrieved = await service.get_session(session.session_id)
    assert retrieved.interview_status == InterviewStatus.IN_PROGRESS
    assert retrieved.connection_status == ConnectionStatus.CONNECTED


@pytest.mark.asyncio
async def test_end_succeeds_when_livekit_delete_room_fails():
    service = VoiceInterviewService(livekit_service=_FailingLiveKit())
    session = await service.create_session("cand_1", "job_1")
    await service.start_interview(session.session_id)

    end_res = await service.end_interview(session.session_id)

    assert end_res["status"] == "ended"
    assert end_res["session_id"] == session.session_id
    retrieved = await service.get_session(session.session_id)
    assert retrieved.interview_status == InterviewStatus.COMPLETED
    assert retrieved.connection_status == ConnectionStatus.DISCONNECTED


JOIN_CONTRACT_FIELDS = {
    "status",
    "session_id",
    "livekit_url",
    "room_name",
    "token",
    "identity",
}


@pytest.mark.asyncio
async def test_start_mock_mode_join_contract_fields():
    service = VoiceInterviewService()
    session = await service.create_session("cand_1", "job_1")

    start_res = await service.start_interview(session.session_id)

    assert set(start_res.keys()) == JOIN_CONTRACT_FIELDS
    assert start_res["status"] == "started"
    assert start_res["room_name"] == f"interview-{session.session_id}"
    assert start_res["identity"] == "candidate-cand_1"
    assert start_res["token"] == (
        f"mock_token_interview-{session.session_id}_candidate-cand_1"
    )
    assert isinstance(start_res["livekit_url"], str)
    assert "token" not in (await service.get_session(session.session_id)).model_dump()


@pytest.mark.asyncio
async def test_start_credentialed_token_matches_room_and_identity():
    livekit = LiveKitService(
        LiveKitConfig(
            url="wss://example.livekit.cloud",
            api_key="devkey",
            api_secret="secretsecretsecretsecretsecretsecre",
        )
    )
    service = VoiceInterviewService(livekit_service=livekit)
    session = await service.create_session("cand_1", "job_1")
    expected_room = f"interview-{session.session_id}"
    expected_identity = "candidate-cand_1"

    create_room = AsyncMock(return_value={"name": expected_room, "sid": ""})
    with patch.object(livekit, "create_room", new=create_room):
        start_res = await service.start_interview(session.session_id)

    assert set(start_res.keys()) == JOIN_CONTRACT_FIELDS
    assert start_res["livekit_url"] == "wss://example.livekit.cloud"
    assert start_res["room_name"] == expected_room
    assert start_res["identity"] == expected_identity
    claims = jwt.decode(start_res["token"], options={"verify_signature": False})
    assert claims["video"]["room"] == expected_room
    assert claims["sub"] == expected_identity
    create_room.assert_awaited_once_with(expected_room)
