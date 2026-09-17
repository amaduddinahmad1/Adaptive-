"""
Shared pytest fixtures for backend tests.
"""
import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.integrations.livekit.config import LiveKitConfig
from app.integrations.livekit.service import LiveKitService
from app.main import app
from app.services.voice.service import VoiceInterviewService
from tests.auth_helpers import AuthenticatedClient, bearer_headers, seed_user
from tests.db_helpers import create_test_engine, create_test_session, seed_application


def make_mock_voice_service() -> VoiceInterviewService:
    """Voice service with empty LiveKit config so tests stay in mock-token mode."""
    return VoiceInterviewService(
        livekit_service=LiveKitService(LiveKitConfig())
    )


@pytest.fixture
def db_engine():
    engine = create_test_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    session = create_test_session(db_engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def eligible_application(db_session, recruiter_user):
    return seed_application(
        db_session,
        overall_eligible=True,
        created_by_user_id=recruiter_user.id,
    )


@pytest.fixture
def ineligible_application(db_session, recruiter_user):
    return seed_application(
        db_session,
        overall_eligible=False,
        created_by_user_id=recruiter_user.id,
    )


@pytest.fixture(autouse=True)
def jwt_test_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-test-jwt-secret-key-32b-min")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")


@pytest.fixture
def client(db_session):
    """Fresh application-scoped voice service and SQLite get_db override per test."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.voice_service = make_mock_voice_service()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def recruiter_user(db_session):
    return seed_user(db_session)


@pytest.fixture
def auth_headers(recruiter_user):
    return bearer_headers(recruiter_user)


@pytest.fixture
def auth_client(client, auth_headers):
    return AuthenticatedClient(client, auth_headers)
