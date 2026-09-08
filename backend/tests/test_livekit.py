"""
Tests for LiveKit room/token support.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from app.integrations.livekit.config import LiveKitConfig
from app.integrations.livekit.service import LiveKitService


def _mock_service() -> LiveKitService:
    return LiveKitService(LiveKitConfig(url="", api_key="", api_secret=""))


def _credentialed_service() -> LiveKitService:
    return LiveKitService(
        LiveKitConfig(
            url="http://localhost:7880",
            api_key="devkey",
            api_secret="secretsecretsecretsecretsecretsecre",
        )
    )


def test_livekit_mock_mode_without_credentials():
    service = _mock_service()
    assert service.is_mock_mode() is True
    token = service.generate_token("interview-abc", "candidate-1")
    assert token == "mock_token_interview-abc_candidate-1"


@pytest.mark.asyncio
async def test_livekit_mock_create_and_delete_room():
    service = _mock_service()
    room = await service.create_room("interview-abc")
    assert room["name"] == "interview-abc"
    assert room["sid"] == "mock_rm_interview-abc"
    assert await service.delete_room("interview-abc") is True


def test_livekit_real_token_generation_with_credentials():
    service = _credentialed_service()
    assert service.is_mock_mode() is False
    token = service.generate_token("interview-abc", "candidate-1")
    parts = token.split(".")
    assert len(parts) == 3
    assert not token.startswith("mock_token_")

    claims = jwt.decode(token, options={"verify_signature": False})
    video = claims["video"]
    assert video["roomJoin"] is True
    assert video["room"] == "interview-abc"
    assert claims["sub"] == "candidate-1"
    assert video["canPublish"] is True
    assert video["canSubscribe"] is True


def _failing_livekit_api() -> MagicMock:
    mock_api = MagicMock()
    mock_api.room.create_room = AsyncMock(side_effect=RuntimeError("create_room failed"))
    mock_api.room.delete_room = AsyncMock(side_effect=RuntimeError("delete_room failed"))
    mock_api.aclose = AsyncMock()
    return mock_api


@pytest.mark.asyncio
async def test_create_room_handles_api_failure():
    service = _credentialed_service()
    mock_api = _failing_livekit_api()
    with patch("app.integrations.livekit.service.api.LiveKitAPI", return_value=mock_api):
        result = await service.create_room("interview-abc")

    assert result == {"name": "interview-abc", "sid": ""}
    mock_api.room.create_room.assert_awaited()
    mock_api.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_delete_room_handles_api_failure():
    service = _credentialed_service()
    mock_api = _failing_livekit_api()
    with patch("app.integrations.livekit.service.api.LiveKitAPI", return_value=mock_api):
        result = await service.delete_room("interview-abc")

    assert result is False
    mock_api.room.delete_room.assert_awaited()
    mock_api.aclose.assert_awaited()


@pytest.mark.asyncio
async def test_livekit_api_receives_configured_credentials():
    config = LiveKitConfig(
        url="http://localhost:7880",
        api_key="test-api-key",
        api_secret="test-api-secret-not-real",
    )
    service = LiveKitService(config)
    mock_api = MagicMock()
    mock_api.room.create_room = AsyncMock(return_value=MagicMock(name="interview-abc", sid="RM_1"))
    mock_api.aclose = AsyncMock()

    with patch(
        "app.integrations.livekit.service.api.LiveKitAPI",
        return_value=mock_api,
    ) as livekit_api_cls:
        await service.create_room("interview-abc")

    livekit_api_cls.assert_called_once_with(
        "http://localhost:7880",
        "test-api-key",
        "test-api-secret-not-real",
    )
