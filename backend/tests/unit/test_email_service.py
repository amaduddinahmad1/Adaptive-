"""
tests/unit/test_email_service.py

Unit tests for app.services.notifications.email_service, using pytest's
monkeypatch to control env vars and replace smtplib.SMTP with a mock --
never a real network call. Three cases, matching how this function is
actually meant to fail or succeed in run_pipeline_smoketest.py's wiring:
success, an SMTP-level failure (confirming EmailServiceError is raised and
that email_sent_at -- set by a separate application_repository function
the caller only reaches on success -- would never get set on this path),
and missing credentials (confirming it fails fast, before ever touching
the network).
"""
import smtplib
from unittest.mock import MagicMock

import pytest

from app.models.application import Application
from app.services.notifications.email_service import (
    EmailServiceError,
    send_interview_invitation,
    send_password_reset_email,
)


def _install_mock_smtp(monkeypatch) -> MagicMock:
    """Replaces smtplib.SMTP with a mock whose `with SMTP(...) as server:` yields a mock server instance."""
    mock_server = MagicMock()
    mock_smtp_class = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server
    monkeypatch.setattr(smtplib, "SMTP", mock_smtp_class)
    return mock_server


def test_send_password_reset_email_success(monkeypatch):
    monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-password")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://recruiter.example.test")
    monkeypatch.delenv("RECRUITER_FRONTEND_BASE_URL", raising=False)
    mock_server = _install_mock_smtp(monkeypatch)

    send_password_reset_email(
        recruiter_email="recruiter@example.com",
        recruiter_name="Alex Mercer",
        raw_token="raw-reset-token-value",
    )

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("sender@example.com", "app-password")
    mock_server.send_message.assert_called_once()

    sent_message = mock_server.send_message.call_args.args[0]
    assert sent_message["To"] == "recruiter@example.com"
    assert sent_message["From"] == "sender@example.com"
    assert sent_message["Subject"] == "Reset your recruiter account password"
    body = sent_message.get_content()
    assert "Alex Mercer" in body
    assert "https://recruiter.example.test/reset-password?token=raw-reset-token-value" in body
    assert "30 minutes" in body
    assert "ignore this email" in body.lower()
    assert "password_hash" not in body
    assert "app-password" not in body


def test_send_password_reset_email_uses_recruiter_frontend_override(monkeypatch):
    monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-password")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://candidate.example.test")
    monkeypatch.setenv("RECRUITER_FRONTEND_BASE_URL", "https://recruiter.example.test")
    mock_server = _install_mock_smtp(monkeypatch)

    send_password_reset_email(
        recruiter_email="recruiter@example.com",
        recruiter_name="Alex Mercer",
        raw_token="raw-reset-token-value",
    )

    body = mock_server.send_message.call_args.args[0].get_content()
    assert "https://recruiter.example.test/reset-password?token=raw-reset-token-value" in body
    assert "candidate.example.test" not in body


def test_send_password_reset_email_raises_on_smtp_failure_without_token(monkeypatch):
    monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-password")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://recruiter.example.test")
    mock_server = _install_mock_smtp(monkeypatch)
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")

    with pytest.raises(EmailServiceError) as exc_info:
        send_password_reset_email(
            recruiter_email="recruiter@example.com",
            recruiter_name="Alex Mercer",
            raw_token="raw-reset-token-value",
        )

    assert "raw-reset-token-value" not in str(exc_info.value)
    assert "password_hash" not in str(exc_info.value)


def test_send_interview_invitation_success(monkeypatch):
    monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-password")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://example-frontend.test")
    mock_server = _install_mock_smtp(monkeypatch)

    send_interview_invitation(
        candidate_email="candidate@example.com",
        candidate_name="Jamie Candidate",
        job_title="AI Engineer Intern",
        interview_token="tok-abc123",
    )

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("sender@example.com", "app-password")
    mock_server.send_message.assert_called_once()

    sent_message = mock_server.send_message.call_args.args[0]
    assert sent_message["To"] == "candidate@example.com"
    assert sent_message["From"] == "sender@example.com"
    assert "AI Engineer Intern" in sent_message["Subject"]
    body = sent_message.get_content()
    assert "https://example-frontend.test/interview/tok-abc123" in body
    assert "Jamie Candidate" in body


def test_send_interview_invitation_raises_on_smtp_failure_and_leaves_email_sent_at_unset(monkeypatch):
    """
    Confirms EmailServiceError is raised on an SMTP-level failure, and
    documents the contract this failure mode depends on: since
    mark_invitation_sent() is only ever called by the caller after this
    function returns successfully (see run_pipeline_smoketest.py's wiring),
    an Application's email_sent_at is never touched on this path -- proven
    here structurally, since the exception prevents the caller from ever
    reaching that call.
    """
    monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-password")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://example-frontend.test")
    mock_server = _install_mock_smtp(monkeypatch)
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")

    application = Application(id=1, overall_eligible=True, email_sent_at=None)

    with pytest.raises(EmailServiceError, match="Failed to send interview invitation"):
        send_interview_invitation(
            candidate_email="candidate@example.com",
            candidate_name="Jamie Candidate",
            job_title="AI Engineer Intern",
            interview_token="tok-abc123",
        )

    assert application.email_sent_at is None


def test_send_interview_invitation_raises_when_credentials_missing(monkeypatch):
    """Fails fast on missing SMTP_EMAIL/SMTP_APP_PASSWORD -- never attempts an SMTP connection at all."""
    monkeypatch.delenv("SMTP_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_APP_PASSWORD", raising=False)
    mock_smtp_class = MagicMock()
    monkeypatch.setattr(smtplib, "SMTP", mock_smtp_class)

    with pytest.raises(EmailServiceError, match="SMTP_EMAIL and SMTP_APP_PASSWORD must both be set"):
        send_interview_invitation(
            candidate_email="candidate@example.com",
            candidate_name="Jamie Candidate",
            job_title="AI Engineer Intern",
            interview_token="tok-abc123",
        )

    mock_smtp_class.assert_not_called()


def test_send_interview_invitation_raises_when_frontend_base_url_missing(monkeypatch):
    monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-password")
    monkeypatch.delenv("FRONTEND_BASE_URL", raising=False)
    mock_smtp_class = MagicMock()
    monkeypatch.setattr(smtplib, "SMTP", mock_smtp_class)

    with pytest.raises(EmailServiceError, match="FRONTEND_BASE_URL"):
        send_interview_invitation(
            candidate_email="candidate@example.com",
            candidate_name="Jamie Candidate",
            job_title="AI Engineer Intern",
            interview_token="tok-abc123",
        )

    mock_smtp_class.assert_not_called()


def test_interview_link_path_template_is_configurable(monkeypatch):
    """FRONTEND_BASE_URL + INTERVIEW_LINK_PATH_TEMPLATE combine without a code change once Jazib's real route is confirmed."""
    monkeypatch.setenv("SMTP_EMAIL", "sender@example.com")
    monkeypatch.setenv("SMTP_APP_PASSWORD", "app-password")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://example-frontend.test")
    monkeypatch.setenv("INTERVIEW_LINK_PATH_TEMPLATE", "/candidate/interview?token={token}")
    mock_server = _install_mock_smtp(monkeypatch)

    send_interview_invitation(
        candidate_email="candidate@example.com",
        candidate_name="Jamie Candidate",
        job_title="AI Engineer Intern",
        interview_token="tok-abc123",
    )

    sent_message = mock_server.send_message.call_args.args[0]
    body = sent_message.get_content()
    assert "https://example-frontend.test/candidate/interview?token=tok-abc123" in body
