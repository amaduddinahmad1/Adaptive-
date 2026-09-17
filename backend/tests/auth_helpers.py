"""Helpers for recruiter authentication tests."""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.user import ROLE_RECRUITER, User


class AuthenticatedClient:
    """TestClient wrapper that attaches a Bearer token to every request."""

    def __init__(self, client: TestClient, headers: dict):
        self._client = client
        self._headers = headers

    def _merge(self, kwargs: dict) -> dict:
        headers = {**self._headers, **(kwargs.pop("headers", None) or {})}
        kwargs["headers"] = headers
        return kwargs

    def get(self, url, **kwargs):
        return self._client.get(url, **self._merge(kwargs))

    def post(self, url, **kwargs):
        return self._client.post(url, **self._merge(kwargs))

    def put(self, url, **kwargs):
        return self._client.put(url, **self._merge(kwargs))

    def patch(self, url, **kwargs):
        return self._client.patch(url, **self._merge(kwargs))

    def delete(self, url, **kwargs):
        return self._client.delete(url, **self._merge(kwargs))


def seed_user(
    db: Session,
    *,
    full_name: str = "Test Recruiter",
    email: str = "recruiter@example.com",
    password: str = "SecurePass1",
    role: str = ROLE_RECRUITER,
    is_active: bool = True,
    token_version: int = 0,
) -> User:
    user = User(
        full_name=full_name,
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        token_version=token_version,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def bearer_headers(user: User) -> dict:
    token = create_access_token(
        subject=str(user.id),
        email=user.email,
        role=user.role,
        token_version=user.token_version,
    )
    return {"Authorization": f"Bearer {token}"}


def authenticated_client(client: TestClient, user: User) -> AuthenticatedClient:
    return AuthenticatedClient(client, bearer_headers(user))
