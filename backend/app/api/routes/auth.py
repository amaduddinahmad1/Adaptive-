"""Recruiter signup, login, current-user, logout, and password-reset endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_recruiter
from app.core.security import (
    AuthConfigError,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    generate_password_reset_token,
    hash_password,
    hash_password_reset_token,
    verify_password,
)
from app.db.session import get_db
from app.models.password_reset_token import PasswordResetToken
from app.models.user import ROLE_RECRUITER, User
from app.schemas.auth import (
    RecruiterAuthResponse,
    RecruiterForgotPasswordRequest,
    RecruiterLoginRequest,
    RecruiterPasswordResetResponse,
    RecruiterPublic,
    RecruiterResetPasswordRequest,
    RecruiterSignupRequest,
)
from app.services.notifications.email_service import (
    EmailServiceError,
    send_password_reset_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

_INVALID_CREDENTIALS = "Invalid email or password."
_DUPLICATE_EMAIL = "An account with this email already exists."
_AUTH_UNAVAILABLE = "Authentication is not configured."
_FORGOT_PASSWORD_MESSAGE = (
    "If an account exists for that email, a password reset link has been sent."
)
_RESET_PASSWORD_MESSAGE = "Password reset successfully."
_INVALID_RESET_TOKEN = "Invalid or expired password reset token."


def _to_public(user: User) -> RecruiterPublic:
    return RecruiterPublic(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        role=user.role,
    )


def _issue_auth_response(user: User) -> RecruiterAuthResponse:
    try:
        token = create_access_token(
            subject=str(user.id),
            email=user.email,
            role=user.role,
            token_version=user.token_version,
        )
    except AuthConfigError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_AUTH_UNAVAILABLE,
        ) from None
    return RecruiterAuthResponse(access_token=token, recruiter=_to_public(user))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _invalidate_outstanding_reset_tokens(
    db: Session,
    user_id: int,
    *,
    now: datetime,
    exclude_id: int | None = None,
) -> None:
    query = db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user_id,
        PasswordResetToken.used_at.is_(None),
    )
    if exclude_id is not None:
        query = query.filter(PasswordResetToken.id != exclude_id)
    for row in query.all():
        row.used_at = now


def _issue_password_reset_token(db: Session, user: User) -> str:
    now = datetime.now(timezone.utc)
    _invalidate_outstanding_reset_tokens(db, user.id, now=now)
    raw_token = generate_password_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_password_reset_token(raw_token),
            expires_at=now + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )
    db.commit()
    return raw_token


def _load_usable_reset_token(db: Session, raw_token: str) -> PasswordResetToken | None:
    token_hash = hash_password_reset_token(raw_token)
    row = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )
    if row is None or row.used_at is not None:
        return None
    if _as_utc(row.expires_at) <= datetime.now(timezone.utc):
        return None
    return row


@router.post(
    "/recruiter/signup",
    response_model=RecruiterAuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def recruiter_signup(
    payload: RecruiterSignupRequest,
    db: Session = Depends(get_db),
) -> RecruiterAuthResponse:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_EMAIL)

    user = User(
        full_name=payload.full_name,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=ROLE_RECRUITER,
        is_active=True,
        token_version=0,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE_EMAIL) from None

    return _issue_auth_response(user)


@router.post("/recruiter/login", response_model=RecruiterAuthResponse)
def recruiter_login(
    payload: RecruiterLoginRequest,
    db: Session = Depends(get_db),
) -> RecruiterAuthResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    password_ok = verify_password(payload.password, user.password_hash if user else None)
    if (
        user is None
        or not password_ok
        or user.role != ROLE_RECRUITER
        or not user.is_active
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_CREDENTIALS,
        )
    return _issue_auth_response(user)


@router.get("/me", response_model=RecruiterPublic)
def read_current_recruiter(user: User = Depends(require_recruiter)) -> RecruiterPublic:
    return _to_public(user)


@router.post("/logout")
def logout_current_recruiter(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user.token_version = int(user.token_version or 0) + 1
    db.commit()
    return {"detail": "Logged out"}


@router.post(
    "/recruiter/forgot-password",
    response_model=RecruiterPasswordResetResponse,
)
def recruiter_forgot_password(
    payload: RecruiterForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> RecruiterPasswordResetResponse:
    generic = RecruiterPasswordResetResponse(message=_FORGOT_PASSWORD_MESSAGE)
    user = (
        db.query(User)
        .filter(User.email == payload.email, User.role == ROLE_RECRUITER)
        .first()
    )
    if user is None or not user.is_active:
        return generic

    try:
        raw_token = _issue_password_reset_token(db, user)
    except Exception:
        db.rollback()
        logger.error(
            "Failed to issue a password reset token for user %s",
            user.id,
            exc_info=True,
        )
        return generic

    try:
        send_password_reset_email(
            recruiter_email=user.email,
            recruiter_name=user.full_name,
            raw_token=raw_token,
        )
    except EmailServiceError:
        logger.error(
            "Password reset email failed for user %s",
            user.id,
            exc_info=True,
        )
    return generic


@router.post(
    "/recruiter/reset-password",
    response_model=RecruiterPasswordResetResponse,
)
def recruiter_reset_password(
    payload: RecruiterResetPasswordRequest,
    db: Session = Depends(get_db),
) -> RecruiterPasswordResetResponse:
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=_INVALID_RESET_TOKEN,
    )
    row = _load_usable_reset_token(db, payload.token)
    if row is None:
        raise invalid

    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None or not user.is_active or user.role != ROLE_RECRUITER:
        raise invalid

    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(payload.new_password)
    user.token_version = int(user.token_version or 0) + 1
    row.used_at = now
    _invalidate_outstanding_reset_tokens(
        db,
        user.id,
        now=now,
        exclude_id=row.id,
    )
    db.commit()
    return RecruiterPasswordResetResponse(message=_RESET_PASSWORD_MESSAGE)
