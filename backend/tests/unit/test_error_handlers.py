"""User-facing error handlers must not leak internals or secrets."""
from fastapi.testclient import TestClient

from app.main import _CV_ANALYSIS_UNAVAILABLE, _GENERIC_SERVER_ERROR_MESSAGE, _JD_ANALYSIS_UNAVAILABLE
from app.services.cv_intelligence.cv_parser import CVParserError
from app.services.jd_intelligence.jd_parser import JDParserError


def test_http_404_still_returns_specific_message(auth_client):
    response = auth_client.get("/api/v1/dashboard/applications/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"
    assert "traceback" not in response.text.lower()


def test_unhandled_exception_returns_generic_json(db_session, monkeypatch):
    from app.db.session import get_db
    from app.main import app
    from tests.conftest import make_mock_voice_service

    def boom(*args, **kwargs):
        raise RuntimeError("password=supersecret sqlalchemy.exc.OperationalError internals")

    monkeypatch.setattr(db_session, "query", boom)

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.voice_service = make_mock_voice_service()
    with TestClient(app, raise_server_exceptions=False) as silent_client:
        response = silent_client.get("/api/v1/jobs")
    app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 500
    assert response.json()["detail"] == _GENERIC_SERVER_ERROR_MESSAGE
    assert "password" not in response.text
    assert "supersecret" not in response.text
    assert "OperationalError" not in response.text
    assert "traceback" not in response.text.lower()


def test_cv_parser_error_does_not_leak_llm_details(client: TestClient, eligible_application, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.apply.extract_cv_text",
        lambda path: "candidate cv text",
    )
    monkeypatch.setattr(
        "app.api.routes.apply.parse_cv",
        lambda text: (_ for _ in ()).throw(CVParserError("GEMINI_API_KEY leaked")),
    )
    response = client.post(
        f"/api/v1/jobs/{eligible_application.job_posting_id}/apply",
        data={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "+1 555 000 0000",
            "joining_availability": "immediate",
            "salary_expectation": "120000",
        },
        files={"cv": ("resume.pdf", b"%PDF-fake-content", "application/pdf")},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == _CV_ANALYSIS_UNAVAILABLE
    assert "GEMINI_API_KEY" not in response.text


def test_jd_parser_error_does_not_leak_llm_details(auth_client, monkeypatch):
    monkeypatch.setattr(
        "app.api.routes.dashboard.parse_job_description",
        lambda text: (_ for _ in ()).throw(JDParserError("GEMINI_API_KEY leaked")),
    )
    response = auth_client.post(
        "/api/v1/dashboard/jobs",
        json={"job_title": "Backend Engineer", "jd_text": "Need Python and FastAPI."},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == _JD_ANALYSIS_UNAVAILABLE
    assert "GEMINI_API_KEY" not in response.text
