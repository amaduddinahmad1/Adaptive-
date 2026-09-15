"""
HTTP lifecycle tests for voice session endpoints.

Voice sessions are in-memory and must be created from a real Application row.
candidate_id and job_id are not accepted on the create request; the Application
is the sole source of truth for candidate and job identity.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.models.application import Application
from app.models.interview_result import InterviewResult
from app.schemas.voice_session import InterviewStatus, ConnectionStatus
from tests.conftest import make_mock_voice_service


def _create_payload(application: Application, language: str = "en") -> dict:
    return {"application_id": application.id, "language": language}


def _expected_identity(application: Application) -> str:
    return f"candidate-{application.candidate_id}"


def test_health():
    app.state.voice_service = make_mock_voice_service()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "app" in body


def test_voice_session_http_lifecycle(client: TestClient, eligible_application: Application):
    create_response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    )
    assert create_response.status_code == 200
    created = create_response.json()
    session_id = created["session_id"]
    assert created["application_id"] == eligible_application.id
    assert created["candidate_id"] == str(eligible_application.candidate_id)
    assert created["job_id"] == str(eligible_application.job_posting_id)
    assert created["interview_status"] == InterviewStatus.PENDING
    assert created["connection_status"] == ConnectionStatus.DISCONNECTED

    get_response = client.get(f"/api/v1/voice/sessions/{session_id}")
    assert get_response.status_code == 200
    assert get_response.json()["session_id"] == session_id
    assert get_response.json()["interview_status"] == InterviewStatus.PENDING
    assert get_response.json()["application_id"] == eligible_application.id

    start_response = client.post(f"/api/v1/voice/sessions/{session_id}/start")
    assert start_response.status_code == 200
    start_body = start_response.json()
    identity = _expected_identity(eligible_application)
    assert start_body["status"] == "started"
    assert start_body["session_id"] == session_id
    assert start_body["room_name"] == f"interview-{session_id}"
    assert start_body["identity"] == identity
    assert start_body["token"] == f"mock_token_interview-{session_id}_{identity}"
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


def test_start_returns_frontend_livekit_join_contract(
    client: TestClient, eligible_application: Application
):
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    session_id = created["session_id"]
    identity = _expected_identity(eligible_application)

    start_body = client.post(f"/api/v1/voice/sessions/{session_id}/start").json()

    assert set(start_body.keys()) == JOIN_CONTRACT_FIELDS
    assert start_body["status"] == "started"
    assert start_body["session_id"] == session_id
    assert start_body["room_name"] == f"interview-{session_id}"
    assert start_body["identity"] == identity
    assert start_body["token"] == f"mock_token_interview-{session_id}_{identity}"
    assert isinstance(start_body["livekit_url"], str)

    stored = client.get(f"/api/v1/voice/sessions/{session_id}").json()
    assert "token" not in stored
    assert stored["session_id"] == session_id
    assert stored["application_id"] == eligible_application.id


def test_create_session_from_valid_application(
    client: TestClient, eligible_application: Application
):
    response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["application_id"] == eligible_application.id
    assert body["candidate_id"] == str(eligible_application.candidate_id)
    assert body["job_id"] == str(eligible_application.job_posting_id)
    assert isinstance(body["application_id"], int)


def test_create_session_nonexistent_application_does_not_store_or_insert(
    client: TestClient, db_session
):
    application_count = db_session.query(Application).count()
    interview_result_count = db_session.query(InterviewResult).count()
    missing_id = 999999

    response = client.post(
        "/api/v1/voice/sessions",
        json={"application_id": missing_id, "language": "en"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"
    assert app.state.voice_service.session_manager.list_sessions() == []
    assert db_session.query(Application).count() == application_count
    assert db_session.query(InterviewResult).count() == interview_result_count


def test_create_session_ineligible_application_is_rejected(
    client: TestClient, ineligible_application: Application
):
    response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(ineligible_application),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Application is not eligible for interview"
    assert app.state.voice_service.session_manager.list_sessions() == []


def test_create_request_uses_application_as_sole_source_of_truth(
    client: TestClient, eligible_application: Application
):
    """
    candidate_id and job_id were removed from POST /voice/sessions.
    Extra caller IDs must not become the session's candidate/job identity.
    """
    response = client.post(
        "/api/v1/voice/sessions",
        json={
            "application_id": eligible_application.id,
            "candidate_id": "unrelated-candidate",
            "job_id": "unrelated-job",
            "language": "en",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == eligible_application.id
    assert body["candidate_id"] == str(eligible_application.candidate_id)
    assert body["job_id"] == str(eligible_application.job_posting_id)
    assert body["candidate_id"] != "unrelated-candidate"
    assert body["job_id"] != "unrelated-job"


def test_start_uses_application_candidate_identity_not_query_param(
    client: TestClient, eligible_application: Application
):
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    session_id = created["session_id"]
    identity = _expected_identity(eligible_application)

    start_body = client.post(
        f"/api/v1/voice/sessions/{session_id}/start",
        params={"candidate": "unrelated-candidate"},
    ).json()

    assert start_body["identity"] == identity
    assert start_body["identity"] != "candidate-unrelated-candidate"


def test_voice_session_not_found(client: TestClient):
    missing_id = "does-not-exist"
    assert client.get(f"/api/v1/voice/sessions/{missing_id}").status_code == 404
    assert client.get(f"/api/v1/voice/sessions/{missing_id}/status").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{missing_id}/start").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{missing_id}/end").status_code == 404
