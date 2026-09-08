"""
HTTP lifecycle tests for voice session endpoints.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.voice.service import VoiceInterviewService
from app.schemas.voice_session import InterviewStatus, ConnectionStatus


@pytest.fixture
def client():
    """Fresh application-scoped voice service for each test."""
    app.state.voice_service = VoiceInterviewService()
    with TestClient(app) as test_client:
        yield test_client


def test_health():
    app.state.voice_service = VoiceInterviewService()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "app" in body


def test_voice_session_http_lifecycle(client: TestClient):
    create_response = client.post(
        "/api/v1/voice/sessions",
        json={"candidate_id": "cand_1", "job_id": "job_1", "language": "en"},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    session_id = created["session_id"]
    assert created["candidate_id"] == "cand_1"
    assert created["job_id"] == "job_1"
    assert created["interview_status"] == InterviewStatus.PENDING
    assert created["connection_status"] == ConnectionStatus.DISCONNECTED

    get_response = client.get(f"/api/v1/voice/sessions/{session_id}")
    assert get_response.status_code == 200
    assert get_response.json()["session_id"] == session_id
    assert get_response.json()["interview_status"] == InterviewStatus.PENDING

    start_response = client.post(f"/api/v1/voice/sessions/{session_id}/start")
    assert start_response.status_code == 200
    start_body = start_response.json()
    assert start_body["status"] == "started"
    assert start_body["session_id"] == session_id
    assert start_body["room_name"] == f"interview-{session_id}"
    assert start_body["identity"] == "candidate-cand_1"
    assert start_body["token"] == f"mock_token_interview-{session_id}_candidate-cand_1"
    assert "livekit_url" in start_body

    session_after_start = client.get(f"/api/v1/voice/sessions/{session_id}")
    assert session_after_start.status_code == 200
    assert "token" not in session_after_start.json()

    status_response = client.get(f"/api/v1/voice/sessions/{session_id}/status")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["session_id"] == session_id
    assert status_body["interview_status"] == InterviewStatus.IN_PROGRESS
    assert status_body["connection_status"] == ConnectionStatus.CONNECTED

    end_response = client.post(f"/api/v1/voice/sessions/{session_id}/end")
    assert end_response.status_code == 200
    assert end_response.json()["status"] == "ended"
    assert end_response.json()["session_id"] == session_id

    completed_status = client.get(f"/api/v1/voice/sessions/{session_id}/status")
    assert completed_status.status_code == 200
    completed_body = completed_status.json()
    assert completed_body["interview_status"] == InterviewStatus.COMPLETED
    assert completed_body["connection_status"] == ConnectionStatus.DISCONNECTED

    completed_session = client.get(f"/api/v1/voice/sessions/{session_id}")
    assert completed_session.status_code == 200
    assert completed_session.json()["interview_status"] == InterviewStatus.COMPLETED


JOIN_CONTRACT_FIELDS = {
    "status",
    "session_id",
    "livekit_url",
    "room_name",
    "token",
    "identity",
}


def test_start_returns_frontend_livekit_join_contract(client: TestClient):
    created = client.post(
        "/api/v1/voice/sessions",
        json={"candidate_id": "cand_1", "job_id": "job_1", "language": "en"},
    ).json()
    session_id = created["session_id"]

    start_body = client.post(f"/api/v1/voice/sessions/{session_id}/start").json()

    assert set(start_body.keys()) == JOIN_CONTRACT_FIELDS
    assert start_body["status"] == "started"
    assert start_body["session_id"] == session_id
    assert start_body["room_name"] == f"interview-{session_id}"
    assert start_body["identity"] == "candidate-cand_1"
    assert start_body["token"] == f"mock_token_interview-{session_id}_candidate-cand_1"
    assert isinstance(start_body["livekit_url"], str)

    stored = client.get(f"/api/v1/voice/sessions/{session_id}").json()
    assert "token" not in stored
    assert stored["session_id"] == session_id


def test_voice_session_not_found(client: TestClient):
    missing_id = "does-not-exist"
    assert client.get(f"/api/v1/voice/sessions/{missing_id}").status_code == 404
    assert client.get(f"/api/v1/voice/sessions/{missing_id}/status").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{missing_id}/start").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{missing_id}/end").status_code == 404
