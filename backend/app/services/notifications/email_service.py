"""
app/services/notifications/email_service.py

Sends the interview-invitation email via Gmail SMTP (smtplib, stdlib only --
no new dependency). Deliberately has zero database access: this file only
knows how to send an email and report success/failure via
EmailServiceError. Whether/when to record that in the Application row
(email_sent_at) is the caller's job, via
application_repository.mark_invitation_sent() -- keeps this file testable
in isolation (mock smtplib) and keeps DB writes concentrated in the one
module that already owns them.

Requires a Gmail App Password (not the account's real password) --
generated at myaccount.google.com/apppasswords once 2-Step Verification is
enabled on the sending account. See SMTP_EMAIL/SMTP_APP_PASSWORD in
.env.example.

INTERVIEW_LINK_PATH_TEMPLATE is deliberately an env var, not a hardcoded
path: the actual frontend route for the interview page hasn't been
confirmed with the frontend side of this project yet, so the exact shape
(/interview/{token} vs. /interview?token=... vs. something else) needs to
stay a one-line .env change, not a code change, once that's settled.
"""
import os
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from app.core.security import PASSWORD_RESET_TOKEN_EXPIRE_MINUTES

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_INTERVIEW_LINK_PATH_TEMPLATE = "/interview/{token}"
DEFAULT_PASSWORD_RESET_PATH = "/reset-password"


class EmailServiceError(Exception):
    """Raised when sending the interview invitation email fails."""


def _absolute_frontend_base_url(*env_names: str) -> str:
    last_name = env_names[-1] if env_names else "FRONTEND_BASE_URL"
    for name in env_names:
        value = (os.getenv(name) or "").strip().rstrip("/")
        if not value:
            continue
        if not value.startswith(("http://", "https://")):
            raise EmailServiceError(
                f"{name} must be set to an absolute http(s) URL."
            )
        return value
    raise EmailServiceError(
        f"{last_name} must be set to an absolute http(s) URL."
    )


def _smtp_credentials() -> tuple[str, str]:
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_app_password = os.getenv("SMTP_APP_PASSWORD")
    if not smtp_email or not smtp_app_password:
        raise EmailServiceError("SMTP_EMAIL and SMTP_APP_PASSWORD must both be set.")
    return smtp_email, smtp_app_password


def _send_message(message: EmailMessage) -> None:
    smtp_email, smtp_app_password = _smtp_credentials()
    host = os.getenv("SMTP_HOST", DEFAULT_SMTP_HOST)
    port = int(os.getenv("SMTP_PORT", DEFAULT_SMTP_PORT))

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(smtp_email, smtp_app_password)
            server.send_message(message)
    except smtplib.SMTPException as err:
        raise EmailServiceError("Failed to send email.") from err
    except Exception as err:
        raise EmailServiceError("Unexpected error sending email.") from err


def _build_interview_link(interview_token: str) -> str:
    frontend_base_url = _absolute_frontend_base_url("FRONTEND_BASE_URL")
    path_template = os.getenv("INTERVIEW_LINK_PATH_TEMPLATE", DEFAULT_INTERVIEW_LINK_PATH_TEMPLATE)
    return frontend_base_url + path_template.format(token=interview_token)


def build_password_reset_link(raw_token: str) -> str:
    """Reset URLs use the recruiter UI origin when configured, else FRONTEND_BASE_URL."""
    frontend_base_url = _absolute_frontend_base_url(
        "RECRUITER_FRONTEND_BASE_URL",
        "FRONTEND_BASE_URL",
    )
    encoded_token = quote(raw_token, safe="")
    return f"{frontend_base_url}{DEFAULT_PASSWORD_RESET_PATH}?token={encoded_token}"


def _build_message(candidate_email: str, candidate_name: str, job_title: str, interview_token: str) -> EmailMessage:
    interview_link = _build_interview_link(interview_token)

    message = EmailMessage()
    message["Subject"] = f"Interview Invitation — {job_title}"
    message["From"] = os.getenv("SMTP_EMAIL")
    message["To"] = candidate_email
    message.set_content(
        f"Hi {candidate_name},\n\n"
        f"Congratulations — you've been selected to proceed to the interview stage "
        f"for the {job_title} position.\n\n"
        f"Please use the link below to begin your interview:\n\n"
        f"{interview_link}\n\n"
        f"This link is valid for 48 hours and can only be used once.\n\n"
        f"Best regards,\nThe Hiring Team"
    )
    return message


def send_interview_invitation(candidate_email: str, candidate_name: str, job_title: str, interview_token: str) -> None:
    """
    Sends the interview invitation email. Raises EmailServiceError on any
    failure (missing credentials, auth, connection, recipient refused,
    etc.) -- returns None on success. Never touches the database; see
    module docstring.
    """
    _smtp_credentials()
    message = _build_message(candidate_email, candidate_name, job_title, interview_token)
    try:
        _send_message(message)
    except EmailServiceError as err:
        if str(err) == "SMTP_EMAIL and SMTP_APP_PASSWORD must both be set.":
            raise
        raise EmailServiceError(
            f"Failed to send interview invitation to {candidate_email}: {err}"
        ) from err


def _build_password_reset_message(
    recruiter_email: str,
    recruiter_name: str,
    raw_token: str,
) -> EmailMessage:
    reset_link = build_password_reset_link(raw_token)
    greeting_name = (recruiter_name or "").strip() or "there"
    expire_minutes = PASSWORD_RESET_TOKEN_EXPIRE_MINUTES

    message = EmailMessage()
    message["Subject"] = "Reset your recruiter account password"
    message["From"] = os.getenv("SMTP_EMAIL")
    message["To"] = recruiter_email
    message.set_content(
        f"Hi {greeting_name},\n\n"
        "We received a request to reset the password for your InterviewAI "
        "recruiter account.\n\n"
        "Use the link below to choose a new password:\n\n"
        f"{reset_link}\n\n"
        f"This link expires in {expire_minutes} minutes and can only be used once.\n\n"
        "If you did not request a password reset, you can ignore this email. "
        "Your password will remain unchanged.\n\n"
        "Best regards,\nThe InterviewAI Team"
    )
    return message


def send_password_reset_email(
    recruiter_email: str,
    recruiter_name: str,
    raw_token: str,
) -> None:
    """
    Sends a recruiter password-reset email. Raises EmailServiceError on any
    failure. The raw token is included only in the reset URL, never as a
    standalone value, and is never written to the database by this module.
    """
    _smtp_credentials()
    message = _build_password_reset_message(recruiter_email, recruiter_name, raw_token)
    try:
        _send_message(message)
    except EmailServiceError:
        raise
    except Exception as err:
        raise EmailServiceError("Unexpected error sending password reset email.") from err
