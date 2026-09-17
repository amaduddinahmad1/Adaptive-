"""Recruiter authentication API tests."""
from fastapi.testclient import TestClient

from app.core.security import create_access_token, verify_password
from app.models.user import User
from tests.auth_helpers import bearer_headers, seed_user


SIGNUP_PAYLOAD = {
    "full_name": "Alex Mercer",
    "email": "alex@example.com",
    "password": "SecurePass1",
}


def test_recruiter_signup_success(client: TestClient, db_session):
    response = client.post("/api/v1/auth/recruiter/signup", json=SIGNUP_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["recruiter"]["email"] == "alex@example.com"
    assert body["recruiter"]["full_name"] == "Alex Mercer"
    assert body["recruiter"]["role"] == "recruiter"
    assert "password" not in body
    assert "password_hash" not in body
    assert "password" not in body["recruiter"]
    assert "password_hash" not in body["recruiter"]

    stored = db_session.query(User).filter(User.email == "alex@example.com").one()
    assert stored.password_hash != SIGNUP_PAYLOAD["password"]
    assert SIGNUP_PAYLOAD["password"] not in stored.password_hash
    assert stored.password_hash.startswith("$2")
    assert verify_password(SIGNUP_PAYLOAD["password"], stored.password_hash)
    assert stored.role == "recruiter"


def test_recruiter_signup_normalizes_email(client: TestClient, db_session):
    response = client.post(
        "/api/v1/auth/recruiter/signup",
        json={**SIGNUP_PAYLOAD, "email": "Alex@Example.COM"},
    )
    assert response.status_code == 201
    stored = db_session.query(User).filter(User.email == "alex@example.com").one()
    assert stored.email == "alex@example.com"


def test_duplicate_email_rejected(client: TestClient, db_session):
    assert client.post("/api/v1/auth/recruiter/signup", json=SIGNUP_PAYLOAD).status_code == 201
    response = client.post(
        "/api/v1/auth/recruiter/signup",
        json={**SIGNUP_PAYLOAD, "full_name": "Other Recruiter"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "An account with this email already exists."
    assert db_session.query(User).count() == 1


def test_invalid_email_rejected(client: TestClient):
    response = client.post(
        "/api/v1/auth/recruiter/signup",
        json={**SIGNUP_PAYLOAD, "email": "not-an-email"},
    )
    assert response.status_code == 422


def test_weak_password_rejected(client: TestClient, db_session):
    for password in ("short1", "nodigitshere", "12345678"):
        response = client.post(
            "/api/v1/auth/recruiter/signup",
            json={**SIGNUP_PAYLOAD, "email": f"{password}@example.com", "password": password},
        )
        assert response.status_code == 422
    assert db_session.query(User).count() == 0


def test_plaintext_password_is_never_persisted(client: TestClient, db_session):
    client.post("/api/v1/auth/recruiter/signup", json=SIGNUP_PAYLOAD)
    stored = db_session.query(User).one()
    dumped = {column.name: getattr(stored, column.name) for column in User.__table__.columns}
    assert SIGNUP_PAYLOAD["password"] not in dumped.values()
    assert "SecurePass1" not in str(dumped)


def test_recruiter_login_success(client: TestClient, recruiter_user):
    response = client.post(
        "/api/v1/auth/recruiter/login",
        json={"email": "recruiter@example.com", "password": "SecurePass1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["recruiter"]["id"] == recruiter_user.id
    assert body["recruiter"]["email"] == "recruiter@example.com"
    assert "password" not in body
    assert "password_hash" not in body["recruiter"]


def test_wrong_password_rejected(client: TestClient, recruiter_user):
    response = client.post(
        "/api/v1/auth/recruiter/login",
        json={"email": recruiter_user.email, "password": "WrongPass1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_unknown_email_rejected_safely(client: TestClient):
    response = client.post(
        "/api/v1/auth/recruiter/login",
        json={"email": "missing@example.com", "password": "SecurePass1"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
    assert "missing@example.com" not in response.text or response.json()["detail"] == "Invalid email or password."


def test_me_returns_authenticated_recruiter(auth_client, recruiter_user):
    response = auth_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": recruiter_user.id,
        "full_name": recruiter_user.full_name,
        "email": recruiter_user.email,
        "role": "recruiter",
    }
    assert "password" not in body
    assert "password_hash" not in body


def test_me_rejects_unauthenticated_request(client: TestClient):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_recruiter_api_rejects_unauthenticated_request(client: TestClient):
    response = client.get("/api/v1/dashboard/applications")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    sessions = client.get("/api/v1/voice/sessions")
    assert sessions.status_code == 401
    analyze = client.post("/analyze-jd", json={"jd_text": "Need Python."})
    assert analyze.status_code == 401


def test_authenticated_recruiter_can_access_recruiter_api(auth_client):
    response = auth_client.get("/api/v1/dashboard/applications")
    assert response.status_code == 200
    assert response.json() == []


def test_non_recruiter_role_cannot_access_recruiter_api(client: TestClient, db_session):
    user = seed_user(db_session, email="admin@example.com", role="admin")
    headers = bearer_headers(user)
    response = client.get("/api/v1/dashboard/applications", headers=headers)
    assert response.status_code == 403
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 403


def test_logout_invalidates_existing_token(client: TestClient, recruiter_user, db_session):
    headers = bearer_headers(recruiter_user)
    before = client.get("/api/v1/auth/me", headers=headers)
    assert before.status_code == 200

    logout = client.post("/api/v1/auth/logout", headers=headers)
    assert logout.status_code == 200

    after = client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401
    dashboard = client.get("/api/v1/dashboard/applications", headers=headers)
    assert dashboard.status_code == 401

    db_session.refresh(recruiter_user)
    assert recruiter_user.token_version == 1


def test_existing_recruiter_apis_work_when_authenticated(
    auth_client, eligible_application
):
    applications = auth_client.get("/api/v1/dashboard/applications")
    assert applications.status_code == 200
    assert applications.json()[0]["id"] == eligible_application.id

    jobs = auth_client.get("/api/v1/dashboard/jobs")
    assert jobs.status_code == 200
    assert jobs.json()[0]["id"] == eligible_application.job_posting_id

    sessions = auth_client.get("/api/v1/voice/sessions")
    assert sessions.status_code == 200
    assert sessions.json() == []


def test_candidate_apply_routes_remain_public(client: TestClient, eligible_application):
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    assert response.json()[0]["id"] == eligible_application.job_posting_id


def test_expired_or_tampered_token_is_rejected(client: TestClient, recruiter_user, monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    token = create_access_token(
        subject=str(recruiter_user.id),
        email=recruiter_user.email,
        role=recruiter_user.role,
        token_version=recruiter_user.token_version,
    )
    tampered = token[:-4] + "abcd"
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert response.status_code == 401
