"""
FastAPI dependencies that resolve the authenticated recruiter from a JWT.

Identity always comes from a verified token. Client-supplied recruiter IDs
are never trusted as authentication.
"""
from __future__ import annotations

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import AuthConfigError, decode_access_token
from app.db.session import get_db
from app.models.user import ROLE_RECRUITER, User

_NOT_AUTHENTICATED = "Not authenticated"
_INSUFFICIENT_PERMISSIONS = "Insufficient permissions"


def _unauthorized(detail: str = _NOT_AUTHENTICATED) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def extract_bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization") or ""
    scheme, _, remainder = header.partition(" ")
    token = remainder.strip()
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    return token


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = extract_bearer_token(request)
    try:
        payload = decode_access_token(token)
    except AuthConfigError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication is not configured.",
        ) from None
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Not authenticated") from None
    except jwt.InvalidTokenError:
        raise _unauthorized() from None

    subject = payload.get("sub")
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise _unauthorized() from None

    user: Optional[User] = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise _unauthorized()

    token_version = payload.get("ver")
    try:
        version = int(token_version)
    except (TypeError, ValueError):
        raise _unauthorized() from None
    if version != user.token_version:
        raise _unauthorized()

    return user


def require_recruiter(user: User = Depends(get_current_user)) -> User:
    if user.role != ROLE_RECRUITER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_INSUFFICIENT_PERMISSIONS,
        )
    return user


def get_optional_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Resolve a user only when an Authorization header is present.

    Candidate interview routes stay public when no header is sent. Recruiter
    UI calls that include a Bearer token still authenticate normally.
    """
    header = request.headers.get("Authorization") or ""
    if not header.strip():
        return None
    return get_current_user(request, db)
