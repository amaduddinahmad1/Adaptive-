"""
tests/unit/test_application_repository.py

Unit tests for app.services.persistence.application_repository.generate_interview_token(),
Phase 1 of the interview-invitation email feature. Uses a plain, unpersisted
Application() instance and a MagicMock Session -- these tests only need to
confirm the function's own logic (guards, field assignment, flush-not-commit
discipline), not real database behavior, which is covered separately by the
live smoketest run.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.application import Application
from app.services.persistence.application_repository import generate_interview_token


def _make_eligible_application(**overrides) -> Application:
    defaults = dict(
        id=1,
        overall_eligible=True,
        interview_token=None,
        token_expires_at=None,
        token_used=False,
    )
    defaults.update(overrides)
    return Application(**defaults)


def test_raises_when_application_is_not_eligible():
    """Mirrors run_interview_for_application.py's own re-verification discipline: never trust the caller alone."""
    application = _make_eligible_application(overall_eligible=False)

    with pytest.raises(ValueError, match="not eligible"):
        generate_interview_token(MagicMock(), application)


def test_raises_when_an_active_unexpired_token_already_exists():
    """The real footgun this guards against: silently invalidating a link already sitting in the candidate's inbox."""
    application = _make_eligible_application(
        interview_token="existing-token",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        token_used=False,
    )

    with pytest.raises(ValueError, match="already has an active"):
        generate_interview_token(MagicMock(), application)


def test_allows_regeneration_when_existing_token_is_expired():
    """An expired token is not "active" -- regenerating it is the expected, fine case."""
    application = _make_eligible_application(
        interview_token="old-token",
        token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        token_used=False,
    )

    generate_interview_token(MagicMock(), application)

    assert application.interview_token != "old-token"


def test_allows_regeneration_when_existing_token_was_already_used():
    """A used token is not "active" either, regardless of expiry -- regenerating it is expected (e.g. a resend request)."""
    application = _make_eligible_application(
        interview_token="used-token",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        token_used=True,
    )

    generate_interview_token(MagicMock(), application)

    assert application.interview_token != "used-token"


def test_successful_generation_sets_token_and_48_hour_expiry():
    application = _make_eligible_application()

    before = datetime.now(timezone.utc)
    generate_interview_token(MagicMock(), application)
    after = datetime.now(timezone.utc)

    assert application.interview_token is not None
    assert len(application.interview_token) > 20  # secrets.token_urlsafe(32) -- ~43 chars
    assert (before + timedelta(hours=48)) <= application.token_expires_at <= (after + timedelta(hours=48))


def test_generated_tokens_are_unique_across_calls():
    """Basic sanity check on secrets.token_urlsafe's uniqueness, not a cryptographic proof."""
    app_a = _make_eligible_application(id=1)
    app_b = _make_eligible_application(id=2)

    generate_interview_token(MagicMock(), app_a)
    generate_interview_token(MagicMock(), app_b)

    assert app_a.interview_token != app_b.interview_token


def test_flushes_but_never_commits():
    """
    Same discipline as every other function in this module: the caller
    commits once, after every step in its pipeline succeeds -- this function
    must never commit on its own, or a failure later in the caller's
    transaction would leave a token durably persisted for a pipeline run
    that never actually completed.
    """
    application = _make_eligible_application()
    db = MagicMock()

    generate_interview_token(db, application)

    db.flush.assert_called_once()
    db.commit.assert_not_called()
