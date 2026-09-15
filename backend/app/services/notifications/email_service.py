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

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
DEFAULT_INTERVIEW_LINK_PATH_TEMPLATE = "/interview/{token}"


class EmailServiceError(Exception):
    """Raised when sending the interview invitation email fails."""


def _build_interview_link(interview_token: str) -> str:
    frontend_base_url = os.getenv("FRONTEND_BASE_URL", "").rstrip("/")
    path_template = os.getenv("INTERVIEW_LINK_PATH_TEMPLATE", DEFAULT_INTERVIEW_LINK_PATH_TEMPLATE)
    return frontend_base_url + path_template.format(token=interview_token)


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
    smtp_email = os.getenv("SMTP_EMAIL")
    smtp_app_password = os.getenv("SMTP_APP_PASSWORD")
    if not smtp_email or not smtp_app_password:
        raise EmailServiceError("SMTP_EMAIL and SMTP_APP_PASSWORD must both be set.")

    message = _build_message(candidate_email, candidate_name, job_title, interview_token)
    host = os.getenv("SMTP_HOST", DEFAULT_SMTP_HOST)
    port = int(os.getenv("SMTP_PORT", DEFAULT_SMTP_PORT))

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(smtp_email, smtp_app_password)
            server.send_message(message)
    except smtplib.SMTPException as err:
        raise EmailServiceError(f"Failed to send interview invitation to {candidate_email}: {err}") from err
    except Exception as err:
        raise EmailServiceError(f"Unexpected error sending interview invitation to {candidate_email}: {err}") from err
