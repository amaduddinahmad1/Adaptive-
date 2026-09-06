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
    assert start_response.json()["status"] == "started"
    assert start_response.json()["session_id"] == session_id

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


def test_voice_session_not_found(client: TestClient):
    missing_id = "does-not-exist"
    assert client.get(f"/api/v1/voice/sessions/{missing_id}").status_code == 404
    assert client.get(f"/api/v1/voice/sessions/{missing_id}/status").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{missing_id}/start").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{missing_id}/end").status_code == 404
