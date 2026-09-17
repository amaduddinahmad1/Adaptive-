"""Candidate apply API tests for Phase 4B."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.models.application import HIRING_DECISION_REJECTED, Application
from app.models.candidate import Candidate
from app.models.interview_result import InterviewResult
from app.models.job_posting import JobPosting
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile
from app.services.cv_intelligence.extraction.extract import extract_cv_text
from app.services.cv_intelligence.extraction import CVExtractionError
from app.services.persistence.application_repository import generate_interview_token
from tests.db_helpers import SAMPLE_CANDIDATE_PROFILE, SAMPLE_JOB_PROFILE
from tests.unit.test_eligibility_engine import ScriptedSkillProvider


def _apply_form(**overrides):
    data = {
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "+1 555 000 0000",
        "joining_availability": "immediate",
        "salary_expectation": "120000",
    }
    data.update(overrides)
    files = {"cv": ("resume.pdf", b"%PDF-fake-content", "application/pdf")}
    return data, files


def _patch_cv_pipeline(monkeypatch, *, provider=None):
    monkeypatch.setattr(
        "app.api.routes.apply.extract_cv_text",
        lambda path: "Jane Doe Python FastAPI PostgreSQL",
    )
    monkeypatch.setattr(
        "app.api.routes.apply.parse_cv",
        lambda text: CandidateProfile.model_validate(SAMPLE_CANDIDATE_PROFILE),
    )
    semantic_provider = provider if provider is not None else ScriptedSkillProvider(matched=False)
    monkeypatch.setattr(
        "app.api.routes.apply.get_default_provider",
        lambda: semantic_provider,
    )


def test_extract_cv_text_rejects_unsupported_format(tmp_path):
    path = tmp_path / "resume.doc"
    path.write_bytes(b"not-a-real-doc")
    try:
        extract_cv_text(str(path))
        assert False, "expected CVExtractionError"
    except CVExtractionError as exc:
        assert "Unsupported CV format" in str(exc)


def test_list_open_jobs(client: TestClient, eligible_application):
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["id"] == eligible_application.job_posting_id
    assert jobs[0]["job_title"] == "Backend Engineer"
    assert "raw_jd_text" not in jobs[0]
    assert "application_count" not in jobs[0]


def test_apply_eligible_reuses_existing_job_and_sends_invitation(
    client: TestClient, db_session, eligible_application, monkeypatch
):
    _patch_cv_pipeline(monkeypatch)
    send = MagicMock()
    monkeypatch.setattr("app.api.routes.apply.send_interview_invitation", send)

    data, files = _apply_form()
    response = client.post(
        f"/api/v1/jobs/{eligible_application.job_posting_id}/apply",
        data=data,
        files=files,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall_eligible"] is True
    assert body["invitation_sent"] is True
    assert body["job_posting_id"] == eligible_application.job_posting_id
    assert body["job_title"] == "Backend Engineer"
    assert "interview_token" not in body
    send.assert_called_once()
    assert send.call_args.kwargs["candidate_email"] == "jane@example.com"

    stored = (
        db_session.query(Application)
        .filter(Application.id == body["application_id"])
        .one()
    )
    assert stored.job_posting_id == eligible_application.job_posting_id
    assert stored.overall_eligible is True
    assert stored.interview_token is not None
    assert stored.email_sent_at is not None
    assert db_session.query(JobPosting).count() == 1


def test_apply_to_job_passes_semantic_provider_to_check_eligibility(
    client: TestClient, eligible_application, monkeypatch
):
    import inspect

    from app.api.routes import apply as apply_module
    from app.api.routes import pipeline as pipeline_module

    apply_source = inspect.getsource(apply_module.apply_to_job)
    assert "provider=get_default_provider()" in apply_source
    assert "provider=get_default_provider()" in inspect.getsource(
        pipeline_module.check_eligibility_endpoint
    )
    assert "provider=get_default_provider()" in inspect.getsource(pipeline_module.submit_application)

    provider = ScriptedSkillProvider(matched=False)
    _patch_cv_pipeline(monkeypatch, provider=provider)
    monkeypatch.setattr("app.api.routes.apply.send_interview_invitation", MagicMock())

    captured = {}
    from app.api.routes.apply import check_eligibility as real_check_eligibility

    def _spy(*args, **kwargs):
        captured["provider"] = kwargs.get("provider")
        return real_check_eligibility(*args, **kwargs)

    monkeypatch.setattr("app.api.routes.apply.check_eligibility", _spy)

    data, files = _apply_form(email="provider-wire@example.com")
    response = client.post(
        f"/api/v1/jobs/{eligible_application.job_posting_id}/apply",
        data=data,
        files=files,
    )
    assert response.status_code == 200
    assert captured.get("provider") is provider


def test_apply_ineligible_does_not_send_invitation(
    client: TestClient, db_session, monkeypatch
):
    _patch_cv_pipeline(monkeypatch)
    send = MagicMock()
    monkeypatch.setattr("app.api.routes.apply.send_interview_invitation", send)

    job = JobPosting(
        job_title="COBOL Engineer",
        raw_jd_text="Need COBOL.",
        parsed_profile=JobRequirementProfile(
            job_title="COBOL Engineer",
            required_skills=["COBOL"],
            required_technologies=["COBOL"],
        ).model_dump(mode="json"),
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    data, files = _apply_form(email="ineligible@example.com")
    response = client.post(f"/api/v1/jobs/{job.id}/apply", data=data, files=files)
    assert response.status_code == 200
    body = response.json()
    assert body["overall_eligible"] is False
    assert body["invitation_sent"] is False
    send.assert_not_called()

    stored = (
        db_session.query(Application)
        .filter(Application.id == body["application_id"])
        .one()
    )
    assert stored.overall_eligible is False
    assert stored.interview_token is None
    assert stored.email_sent_at is None


def test_apply_email_failure_still_persists_eligible_application(
    client: TestClient, db_session, eligible_application, monkeypatch
):
    _patch_cv_pipeline(monkeypatch)

    def _fail(**kwargs):
        from app.services.notifications.email_service import EmailServiceError

        raise EmailServiceError("SMTP down")

    monkeypatch.setattr("app.api.routes.apply.send_interview_invitation", _fail)

    data, files = _apply_form(email="smtp-fail@example.com")
    response = client.post(
        f"/api/v1/jobs/{eligible_application.job_posting_id}/apply",
        data=data,
        files=files,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["overall_eligible"] is True
    assert body["invitation_sent"] is False

    stored = (
        db_session.query(Application)
        .filter(Application.id == body["application_id"])
        .one()
    )
    assert stored.interview_token is not None
    assert stored.email_sent_at is None


def test_apply_missing_job(client: TestClient, monkeypatch):
    _patch_cv_pipeline(monkeypatch)
    data, files = _apply_form()
    response = client.post("/api/v1/jobs/99999/apply", data=data, files=files)
    assert response.status_code == 404


def test_apply_rejects_unsupported_cv_type(client: TestClient, eligible_application):
    data, _ = _apply_form()
    files = {"cv": ("resume.doc", b"legacy-doc", "application/msword")}
    response = client.post(
        f"/api/v1/jobs/{eligible_application.job_posting_id}/apply",
        data=data,
        files=files,
    )
    assert response.status_code == 400
    assert "PDF or DOCX" in response.json()["detail"]


def test_apply_rejects_invalid_email(client: TestClient, eligible_application, monkeypatch):
    _patch_cv_pipeline(monkeypatch)
    data, files = _apply_form(email="not-an-email")
    response = client.post(
        f"/api/v1/jobs/{eligible_application.job_posting_id}/apply",
        data=data,
        files=files,
    )
    assert response.status_code == 400
    assert "interview_token" not in response.json()


def test_apply_reuses_candidate_and_updates_name(
    client: TestClient, db_session, eligible_application, monkeypatch
):
    _patch_cv_pipeline(monkeypatch)
    monkeypatch.setattr("app.api.routes.apply.send_interview_invitation", MagicMock())
    data, files = _apply_form(full_name="Jane Doe", email="reuse@example.com")
    first = client.post(
        f"/api/v1/jobs/{eligible_application.job_posting_id}/apply",
        data=data,
        files=files,
    )
    assert first.status_code == 200
    first_candidate_id = first.json()["candidate_id"]

    data, files = _apply_form(full_name="Janet Doe", email="reuse@example.com")
    second = client.post(
        f"/api/v1/jobs/{eligible_application.job_posting_id}/apply",
        data=data,
        files=files,
    )
    assert second.status_code == 200
    assert second.json()["candidate_id"] == first_candidate_id
    stored = db_session.query(Candidate).filter(Candidate.id == first_candidate_id).one()
    assert stored.full_name == "Janet Doe"


def test_resolve_invitation_returns_application_without_token(
    client: TestClient, db_session, eligible_application
):
    generate_interview_token(db_session, eligible_application)
    db_session.commit()
    db_session.refresh(eligible_application)
    token = eligible_application.interview_token

    response = client.post(
        "/api/v1/interview-invitations/resolve",
        json={"token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == eligible_application.id
    assert body["candidate_id"] == eligible_application.candidate_id
    assert body["job_posting_id"] == eligible_application.job_posting_id
    assert body["job_title"] == "Backend Engineer"
    assert body["candidate_full_name"] == "Test Candidate"
    assert "interview_token" not in body
    assert "token" not in body


def test_resolve_invitation_rejects_invalid_expired_ineligible_and_completed(
    client: TestClient, db_session, eligible_application, ineligible_application
):
    missing = client.post(
        "/api/v1/interview-invitations/resolve",
        json={"token": "does-not-exist"},
    )
    assert missing.status_code == 404
    assert "interview_token" not in missing.json()

    generate_interview_token(db_session, eligible_application)
    db_session.commit()
    db_session.refresh(eligible_application)
    expired_token = eligible_application.interview_token
    eligible_application.token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()
    expired = client.post(
        "/api/v1/interview-invitations/resolve",
        json={"token": expired_token},
    )
    assert expired.status_code == 410

    ineligible_application.interview_token = "ineligible-token-value"
    ineligible_application.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
    db_session.commit()
    ineligible = client.post(
        "/api/v1/interview-invitations/resolve",
        json={"token": "ineligible-token-value"},
    )
    assert ineligible.status_code == 403

    other = eligible_application
    other.token_expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
    db_session.add(
        InterviewResult(
            application_id=other.id,
            final_report={},
            recommendation="Hire",
            interview_eligibility_result="Pass",
        )
    )
    db_session.commit()
    completed = client.post(
        "/api/v1/interview-invitations/resolve",
        json={"token": expired_token},
    )
    assert completed.status_code == 409


def test_resolve_invitation_rejects_rejected_application(
    client: TestClient, db_session, eligible_application
):
    generate_interview_token(db_session, eligible_application)
    eligible_application.hiring_decision = HIRING_DECISION_REJECTED
    db_session.commit()
    db_session.refresh(eligible_application)
    response = client.post(
        "/api/v1/interview-invitations/resolve",
        json={"token": eligible_application.interview_token},
    )
    assert response.status_code == 403
    assert "rejected" in response.json()["detail"].lower()
