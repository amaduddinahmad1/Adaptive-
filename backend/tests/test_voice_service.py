"""
Tests for Voice Service.

Sessions are created from a real Application row. candidate_id / job_id on the
in-memory session are derived from Application.candidate_id and
Application.job_posting_id (stringified only at the schema boundary).
"""
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from app.models.application import HIRING_DECISION_REJECTED, Application
from app.services.voice.service import VoiceInterviewService
from app.schemas.voice_session import InterviewStatus, ConnectionStatus
from app.integrations.livekit.config import LiveKitConfig
from app.integrations.livekit.service import LiveKitService
from tests.conftest import make_mock_voice_service


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


def _identity(application: Application) -> str:
    return f"candidate-{application.candidate_id}"


@pytest.mark.asyncio
async def test_voice_interview_service_lifecycle(eligible_application: Application):
    service = make_mock_voice_service()
    identity = _identity(eligible_application)

    session = await service.create_session(eligible_application)
    assert session.application_id == eligible_application.id
    assert session.candidate_id == str(eligible_application.candidate_id)
    assert session.job_id == str(eligible_application.job_posting_id)
    assert session.interview_status == InterviewStatus.PENDING

    retrieved = await service.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.session_id == session.session_id
    assert retrieved.application_id == eligible_application.id

    start_res = await service.start_interview(session.session_id)
    assert start_res["status"] == "started"
    assert start_res["session_id"] == session.session_id
    assert start_res["room_name"] == f"interview-{session.session_id}"
    assert start_res["identity"] == identity
    assert start_res["token"] == (
        f"mock_token_interview-{session.session_id}_{identity}"
    )
    assert "livekit_url" in start_res

    retrieved = await service.get_session(session.session_id)
    assert retrieved.interview_status == InterviewStatus.IN_PROGRESS
    assert retrieved.connection_status == ConnectionStatus.CONNECTED
    assert "token" not in retrieved.model_dump()

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
async def test_create_session_rejects_ineligible_application(
    ineligible_application: Application,
):
    service = VoiceInterviewService()
    with pytest.raises(ValueError, match="Application is not eligible for interview"):
        await service.create_session(ineligible_application)
    assert service.session_manager.list_sessions() == []


@pytest.mark.asyncio
async def test_start_succeeds_when_livekit_create_room_fails(
    eligible_application: Application,
):
    service = VoiceInterviewService(livekit_service=_FailingLiveKit())
    session = await service.create_session(eligible_application)
    identity = _identity(eligible_application)

    start_res = await service.start_interview(session.session_id)

    assert start_res["status"] == "started"
    assert start_res["session_id"] == session.session_id
    assert start_res["room_name"] == f"interview-{session.session_id}"
    assert start_res["identity"] == identity
    assert start_res["token"] == (
        f"token-for-interview-{session.session_id}-{identity}"
    )
    retrieved = await service.get_session(session.session_id)
    assert retrieved.interview_status == InterviewStatus.IN_PROGRESS
    assert retrieved.connection_status == ConnectionStatus.CONNECTED


@pytest.mark.asyncio
async def test_end_succeeds_when_livekit_delete_room_fails(
    eligible_application: Application,
):
    service = VoiceInterviewService(livekit_service=_FailingLiveKit())
    session = await service.create_session(eligible_application)
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
async def test_start_mock_mode_join_contract_fields(eligible_application: Application):
    service = make_mock_voice_service()
    session = await service.create_session(eligible_application)
    identity = _identity(eligible_application)

    start_res = await service.start_interview(session.session_id)

    assert set(start_res.keys()) == JOIN_CONTRACT_FIELDS
    assert start_res["status"] == "started"
    assert start_res["room_name"] == f"interview-{session.session_id}"
    assert start_res["identity"] == identity
    assert start_res["token"] == (
        f"mock_token_interview-{session.session_id}_{identity}"
    )
    assert isinstance(start_res["livekit_url"], str)
    assert "token" not in (await service.get_session(session.session_id)).model_dump()


@pytest.mark.asyncio
async def test_start_credentialed_token_matches_room_and_identity(
    eligible_application: Application,
):
    livekit = LiveKitService(
        LiveKitConfig(
            url="wss://example.livekit.cloud",
            api_key="devkey",
            api_secret="secretsecretsecretsecretsecretsecre",
        )
    )
    service = VoiceInterviewService(livekit_service=livekit)
    session = await service.create_session(eligible_application)
    expected_room = f"interview-{session.session_id}"
    expected_identity = _identity(eligible_application)

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


@pytest.mark.asyncio
async def test_create_session_does_not_query_db_again(
    eligible_application: Application, db_session
):
    """Service receives the already-loaded Application; it must not insert rows."""
    service = VoiceInterviewService()
    application_count = db_session.query(Application).count()

    session = await service.create_session(eligible_application)

    assert session.application_id == eligible_application.id
    assert db_session.query(Application).count() == application_count
    assert service.session_manager.get_session(session.session_id) is not None


@pytest.mark.asyncio
async def test_start_interview_does_not_delete_livekit_room(
    eligible_application: Application,
):
    service = make_mock_voice_service()
    with patch.object(service.livekit, "delete_room", new_callable=AsyncMock) as delete_spy:
        session = await service.create_session(eligible_application)
        await service.start_interview(session.session_id, application=eligible_application)
        delete_spy.assert_not_awaited()
        await service.end_interview(session.session_id)
        delete_spy.assert_awaited()


@pytest.mark.asyncio
async def test_create_session_rejects_rejected_application(
    eligible_application: Application,
):
    eligible_application.hiring_decision = HIRING_DECISION_REJECTED
    service = make_mock_voice_service()
    with pytest.raises(ValueError, match="rejected"):
        await service.create_session(eligible_application)


@pytest.mark.asyncio
async def test_start_blocks_rejected_application_unless_already_in_progress(
    eligible_application: Application,
):
    service = make_mock_voice_service()
    session = await service.create_session(eligible_application)
    eligible_application.hiring_decision = HIRING_DECISION_REJECTED
    with pytest.raises(ValueError, match="rejected"):
        await service.start_interview(session.session_id, application=eligible_application)

    eligible_application.hiring_decision = "pending"
    await service.start_interview(session.session_id, application=eligible_application)
    eligible_application.hiring_decision = HIRING_DECISION_REJECTED
    again = await service.start_interview(
        session.session_id, application=eligible_application
    )
    assert again["status"] == "started"
