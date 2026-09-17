"""
Password hashing and JWT helpers for recruiter authentication.

Secrets are read from the environment on each use so tests can set
JWT_SECRET_KEY without reloading Settings. Tokens never include passwords.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import bcrypt
import jwt
from dotenv import load_dotenv

load_dotenv()

_DEFAULT_ALGORITHM = "HS256"
_DEFAULT_EXPIRE_MINUTES = 60
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30
_DUMMY_PASSWORD_HASH = bcrypt.hashpw(b"invalid-password", bcrypt.gensalt()).decode("utf-8")


class AuthConfigError(RuntimeError):
    """Raised when JWT environment configuration is missing."""


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def generate_password_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password_reset_token(raw_token: str) -> str:
    return hashlib.sha256((raw_token or "").encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    digest = password_hash or _DUMMY_PASSWORD_HASH
    try:
        return bcrypt.checkpw(password.encode("utf-8"), digest.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def get_jwt_secret() -> str:
    secret = (os.getenv("JWT_SECRET_KEY") or "").strip()
    if not secret:
        raise AuthConfigError("JWT_SECRET_KEY is not set. Set it in .env (see .env.example).")
    return secret


def get_jwt_algorithm() -> str:
    return (os.getenv("JWT_ALGORITHM") or _DEFAULT_ALGORITHM).strip() or _DEFAULT_ALGORITHM


def get_access_token_expire_minutes() -> int:
    raw = os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    if raw is None or raw.strip() == "":
        return _DEFAULT_EXPIRE_MINUTES
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise AuthConfigError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be an integer.") from exc
    if minutes <= 0:
        raise AuthConfigError("JWT_ACCESS_TOKEN_EXPIRE_MINUTES must be greater than 0.")
    return minutes


def create_access_token(
    *,
    subject: str,
    email: str,
    role: str,
    token_version: int,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=get_access_token_expire_minutes())
    payload = {
        "sub": str(subject),
        "email": email,
        "role": role,
        "ver": int(token_version),
        "jti": uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": expire,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=get_jwt_algorithm())


def decode_access_token(token: str) -> Dict[str, Any]:
    return jwt.decode(
        token,
        get_jwt_secret(),
        algorithms=[get_jwt_algorithm()],
    )
