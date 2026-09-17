"""Recruiter forgot-password and reset-password API tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.core.security import (
    hash_password_reset_token,
    verify_password,
)
from app.models.password_reset_token import PasswordResetToken
from app.services.notifications.email_service import EmailServiceError
from tests.auth_helpers import bearer_headers, seed_user


GENERIC_FORGOT = (
    "If an account exists for that email, a password reset link has been sent."
)
INVALID_RESET = "Invalid or expired password reset token."
NEW_PASSWORD = "NewPass99"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _capture_reset_email(monkeypatch) -> list[dict]:
    captured: list[dict] = []

    def _fake_send(*, recruiter_email, recruiter_name, raw_token):
        captured.append(
            {
                "email": recruiter_email,
                "name": recruiter_name,
                "token": raw_token,
            }
        )

    monkeypatch.setattr("app.api.routes.auth.send_password_reset_email", _fake_send)
    return captured


def _assert_no_secrets(body: dict, response_text: str, raw_token: str | None = None) -> None:
    assert "token" not in body
    assert "access_token" not in body
    assert "password" not in body
    assert "new_password" not in body
    assert "password_hash" not in body
    assert "token_hash" not in body
    assert "SMTP" not in response_text
    assert "traceback" not in response_text.lower()
    if raw_token:
        assert raw_token not in response_text


def _stored_tokens(db_session, user_id: int) -> list[PasswordResetToken]:
    return (
        db_session.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == user_id)
        .order_by(PasswordResetToken.id.asc())
        .all()
    )


def test_forgot_password_existing_recruiter_succeeds(client: TestClient, recruiter_user, db_session, monkeypatch):
    captured = _capture_reset_email(monkeypatch)
    response = client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": "recruiter@example.com"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"message": GENERIC_FORGOT}
    _assert_no_secrets(body, response.text, captured[0]["token"])
    assert len(captured) == 1
    assert captured[0]["email"] == recruiter_user.email
    assert captured[0]["name"] == recruiter_user.full_name

    rows = _stored_tokens(db_session, recruiter_user.id)
    assert len(rows) == 1
    raw = captured[0]["token"]
    assert rows[0].token_hash == hash_password_reset_token(raw)
    assert raw not in rows[0].token_hash
    assert rows[0].used_at is None
    assert _as_utc(rows[0].expires_at) > datetime.now(timezone.utc)


def test_forgot_password_unknown_email_same_response(client: TestClient, db_session, monkeypatch):
    send = MagicMock()
    monkeypatch.setattr("app.api.routes.auth.send_password_reset_email", send)
    response = client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": "missing@example.com"},
    )
    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_FORGOT}
    _assert_no_secrets(response.json(), response.text)
    send.assert_not_called()
    assert db_session.query(PasswordResetToken).count() == 0


def test_forgot_password_inactive_account_same_response(client: TestClient, db_session, monkeypatch):
    seed_user(db_session, email="inactive@example.com", is_active=False)
    send = MagicMock()
    monkeypatch.setattr("app.api.routes.auth.send_password_reset_email", send)
    response = client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": "inactive@example.com"},
    )
    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_FORGOT}
    _assert_no_secrets(response.json(), response.text)
    send.assert_not_called()
    assert db_session.query(PasswordResetToken).count() == 0


def test_forgot_password_normalizes_email(client: TestClient, recruiter_user, monkeypatch):
    captured = _capture_reset_email(monkeypatch)
    response = client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": "Recruiter@Example.COM"},
    )
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0]["email"] == "recruiter@example.com"


def test_second_forgot_password_invalidates_previous_token(
    client: TestClient, recruiter_user, db_session, monkeypatch
):
    captured = _capture_reset_email(monkeypatch)
    first = client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": recruiter_user.email},
    )
    second = client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": recruiter_user.email},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json() == {"message": GENERIC_FORGOT}
    assert len(captured) == 2
    assert captured[0]["token"] != captured[1]["token"]

    rows = _stored_tokens(db_session, recruiter_user.id)
    assert len(rows) == 2
    db_session.refresh(rows[0])
    db_session.refresh(rows[1])
    assert rows[0].used_at is not None
    assert rows[1].used_at is None
    assert rows[1].token_hash == hash_password_reset_token(captured[1]["token"])

    reused = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": captured[0]["token"], "new_password": NEW_PASSWORD},
    )
    assert reused.status_code == 400
    assert reused.json()["detail"] == INVALID_RESET


def test_forgot_password_smtp_failure_does_not_leak_details(
    client: TestClient, recruiter_user, db_session, monkeypatch
):
    def _fail(*, recruiter_email, recruiter_name, raw_token):
        raise EmailServiceError("SMTP_APP_PASSWORD rejected by smtp.gmail.com")

    monkeypatch.setattr("app.api.routes.auth.send_password_reset_email", _fail)
    response = client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": recruiter_user.email},
    )
    assert response.status_code == 200
    assert response.json() == {"message": GENERIC_FORGOT}
    assert "SMTP" not in response.text
    assert "smtp.gmail.com" not in response.text
    assert "APP_PASSWORD" not in response.text
    assert db_session.query(PasswordResetToken).count() == 1


def test_reset_password_success_and_invalidates_old_credentials(
    client: TestClient, recruiter_user, db_session, monkeypatch
):
    captured = _capture_reset_email(monkeypatch)
    old_headers = bearer_headers(recruiter_user)
    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 200

    client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": recruiter_user.email},
    )
    raw = captured[0]["token"]
    response = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": raw, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Password reset successfully."}
    _assert_no_secrets(response.json(), response.text, raw)

    db_session.refresh(recruiter_user)
    assert recruiter_user.token_version == 1
    assert verify_password(NEW_PASSWORD, recruiter_user.password_hash)
    assert not verify_password("SecurePass1", recruiter_user.password_hash)

    row = _stored_tokens(db_session, recruiter_user.id)[0]
    assert row.used_at is not None

    assert client.get("/api/v1/auth/me", headers=old_headers).status_code == 401
    old_login = client.post(
        "/api/v1/auth/recruiter/login",
        json={"email": recruiter_user.email, "password": "SecurePass1"},
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/api/v1/auth/recruiter/login",
        json={"email": recruiter_user.email, "password": NEW_PASSWORD},
    )
    assert new_login.status_code == 200
    assert new_login.json()["access_token"]


def test_used_reset_token_cannot_be_reused(client: TestClient, recruiter_user, monkeypatch):
    captured = _capture_reset_email(monkeypatch)
    client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": recruiter_user.email},
    )
    raw = captured[0]["token"]
    first = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": raw, "new_password": NEW_PASSWORD},
    )
    assert first.status_code == 200
    second = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": raw, "new_password": "AnotherPass1"},
    )
    assert second.status_code == 400
    assert second.json()["detail"] == INVALID_RESET
    assert "user" not in second.json()


def test_expired_reset_token_rejected(client: TestClient, recruiter_user, db_session):
    from app.core.security import generate_password_reset_token

    raw = generate_password_reset_token()
    db_session.add(
        PasswordResetToken(
            user_id=recruiter_user.id,
            token_hash=hash_password_reset_token(raw),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    )
    db_session.commit()
    response = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": raw, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == INVALID_RESET
    _assert_no_secrets(response.json(), response.text, raw)
    db_session.refresh(recruiter_user)
    assert verify_password("SecurePass1", recruiter_user.password_hash)


def test_invalid_reset_token_rejected_without_revealing_user(client: TestClient, recruiter_user):
    response = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": "not-a-real-reset-token", "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == INVALID_RESET
    assert recruiter_user.email not in response.text
    assert "recruiter@example.com" not in response.text
    _assert_no_secrets(response.json(), response.text)


def test_reset_password_inactive_user_rejected(client: TestClient, db_session):
    from app.core.security import generate_password_reset_token

    user = seed_user(db_session, email="paused@example.com", is_active=False)
    raw = generate_password_reset_token()
    db_session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
    )
    db_session.commit()
    response = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": raw, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == INVALID_RESET
    assert "paused@example.com" not in response.text


def test_reset_invalidates_other_outstanding_tokens(
    client: TestClient, recruiter_user, db_session
):
    from app.core.security import generate_password_reset_token

    raw_keep = generate_password_reset_token()
    raw_other = generate_password_reset_token()
    keep = PasswordResetToken(
        user_id=recruiter_user.id,
        token_hash=hash_password_reset_token(raw_keep),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    other = PasswordResetToken(
        user_id=recruiter_user.id,
        token_hash=hash_password_reset_token(raw_other),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    db_session.add_all([keep, other])
    db_session.commit()

    response = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": raw_keep, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    db_session.refresh(keep)
    db_session.refresh(other)
    assert keep.used_at is not None
    assert other.used_at is not None

    reused = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": raw_other, "new_password": "ThirdPass1"},
    )
    assert reused.status_code == 400
    assert reused.json()["detail"] == INVALID_RESET


def test_reset_password_weak_password_rejected(client: TestClient, recruiter_user, monkeypatch):
    captured = _capture_reset_email(monkeypatch)
    client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": recruiter_user.email},
    )
    raw = captured[0]["token"]
    for password in ("short1", "nodigitshere", "12345678"):
        response = client.post(
            "/api/v1/auth/recruiter/reset-password",
            json={"token": raw, "new_password": password},
        )
        assert response.status_code == 422
    db_session_user = recruiter_user
    assert verify_password("SecurePass1", db_session_user.password_hash)


def test_reset_password_valid_password_accepted(client: TestClient, recruiter_user, monkeypatch):
    captured = _capture_reset_email(monkeypatch)
    client.post(
        "/api/v1/auth/recruiter/forgot-password",
        json={"email": recruiter_user.email},
    )
    response = client.post(
        "/api/v1/auth/recruiter/reset-password",
        json={"token": captured[0]["token"], "new_password": "ValidPass1"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Password reset successfully."
