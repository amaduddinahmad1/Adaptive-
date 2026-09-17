"""Read-only recruiter dashboard API tests for Phase 4A."""
from decimal import Decimal

from app.models.application import HIRING_DECISION_PENDING, HIRING_DECISION_REJECTED, Application
from app.models.candidate import Candidate
from app.models.interview_result import InterviewResult
from app.models.job_posting import JobPosting
from app.schemas.job import JobRequirementProfile
from tests.db_helpers import seed_application


def test_list_applications_includes_invitation_fields(
    auth_client, eligible_application
):
    response = auth_client.get("/api/v1/dashboard/applications")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    row = payload[0]
    assert row["id"] == eligible_application.id
    assert row["overall_eligible"] is True
    assert row["has_interview_result"] is False
    assert row["token_used"] is False
    assert row["email_sent_at"] is None
    assert row["hiring_decision"] == "pending"


def test_eligible_only_filter(auth_client, db_session, eligible_application):
    seed_application(db_session, overall_eligible=False, email="ineligible@example.com")
    all_rows = auth_client.get("/api/v1/dashboard/applications").json()
    eligible_rows = auth_client.get("/api/v1/dashboard/applications?eligible_only=true").json()
    assert len(all_rows) == 2
    assert len(eligible_rows) == 1
    assert eligible_rows[0]["id"] == eligible_application.id


def test_get_application_detail_exposes_persisted_profiles(
    auth_client, eligible_application
):
    response = auth_client.get(f"/api/v1/dashboard/applications/{eligible_application.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["candidate_profile"]["skills"]
    assert body["job_profile_snapshot"]["job_title"] == "Backend Engineer"
    assert "interview_token" not in body
    assert body["interview_result_id"] is None


def test_get_application_missing(auth_client):
    response = auth_client.get("/api/v1/dashboard/applications/99999")
    assert response.status_code == 404


def test_interview_result_404_when_missing(auth_client, eligible_application):
    response = auth_client.get(
        f"/api/v1/dashboard/applications/{eligible_application.id}/interview-result"
    )
    assert response.status_code == 404


def test_interview_result_returns_persisted_row(
    auth_client, db_session, eligible_application
):
    result = InterviewResult(
        application_id=eligible_application.id,
        final_report={"recommendation": "Hire", "recommendation_reason": "Strong answers"},
        recommendation="Hire",
        interview_eligibility_result="Pass",
        problem_solving_performance=Decimal("82.0"),
        communication_performance=Decimal("79.0"),
        interview_plan={"skill_areas": ["Python"]},
        qa_transcript={"turns": [{"question": "Q1", "answer": "A1"}]},
        gap_analysis={"entries": [{"skill": "Redis", "alignment": "gap"}]},
    )
    db_session.add(result)
    db_session.commit()

    response = auth_client.get(
        f"/api/v1/dashboard/applications/{eligible_application.id}/interview-result"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommendation"] == "Hire"
    assert body["interview_eligibility_result"] == "Pass"
    assert body["qa_transcript"]["turns"][0]["question"] == "Q1"
    assert float(body["problem_solving_performance"]) == 82.0


def test_get_job_detail(auth_client, eligible_application):
    job_id = eligible_application.job_posting_id
    response = auth_client.get(f"/api/v1/dashboard/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["job_title"] == "Backend Engineer"
    assert body["application_count"] == 1
    assert body["interview_question_count"] == 7
    assert "Python" in body["parsed_profile"]["required_skills"]


def test_list_jobs_includes_parsed_skills(auth_client, eligible_application):
    response = auth_client.get("/api/v1/dashboard/jobs")
    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert "Python" in jobs[0]["required_skills"]


def test_list_voice_sessions_starts_empty(auth_client):
    response = auth_client.get("/api/v1/voice/sessions")
    assert response.status_code == 200
    assert response.json() == []


def _mock_jd_parse(monkeypatch, title="Backend Engineer"):
    profile = JobRequirementProfile(
        job_title=title,
        required_skills=["Python"],
        required_technologies=["Python"],
    )
    monkeypatch.setattr(
        "app.api.routes.dashboard.parse_job_description",
        lambda text: profile,
    )
    return profile


def test_create_job_persists_and_returns_question_count(
    auth_client, db_session, recruiter_user, monkeypatch
):
    _mock_jd_parse(monkeypatch)
    response = auth_client.post(
        "/api/v1/dashboard/jobs",
        json={
            "job_title": "Backend Engineer",
            "jd_text": "Need Python experience.",
            "interview_question_count": 7,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["interview_question_count"] == 7
    stored = db_session.query(JobPosting).filter(JobPosting.id == body["id"]).one()
    assert stored.interview_question_count == 7
    assert stored.created_by_user_id == recruiter_user.id
    listed = auth_client.get("/api/v1/dashboard/jobs").json()
    created = next(job for job in listed if job["id"] == body["id"])
    assert created["interview_question_count"] == 7


def test_create_job_defaults_question_count_when_omitted(auth_client, db_session, monkeypatch):
    _mock_jd_parse(monkeypatch)
    response = auth_client.post(
        "/api/v1/dashboard/jobs",
        json={"job_title": "Backend Engineer", "jd_text": "Need Python experience."},
    )
    assert response.status_code == 200
    assert response.json()["interview_question_count"] == 7


def test_create_job_rejects_zero_and_negative_question_count(auth_client, monkeypatch):
    _mock_jd_parse(monkeypatch)
    for invalid in (0, -1):
        response = auth_client.post(
            "/api/v1/dashboard/jobs",
            json={
                "job_title": "Backend Engineer",
                "jd_text": "Need Python experience.",
                "interview_question_count": invalid,
            },
        )
        assert response.status_code == 422


def test_existing_job_without_explicit_count_uses_default(
    auth_client, eligible_application
):
    response = auth_client.get(f"/api/v1/dashboard/jobs/{eligible_application.job_posting_id}")
    assert response.status_code == 200
    assert response.json()["interview_question_count"] == 7


def test_reject_application_is_persisted_and_idempotent(
    auth_client, db_session, eligible_application
):
    other = seed_application(db_session, email="other@example.com")
    result = InterviewResult(
        application_id=eligible_application.id,
        final_report={"recommendation": "Hire"},
        recommendation="Hire",
        interview_eligibility_result="Pass",
        qa_transcript={"turns": [{"question": "Q1", "answer": "A1"}]},
    )
    db_session.add(result)
    db_session.commit()
    db_session.refresh(result)
    candidate_count = db_session.query(Candidate).count()
    application_count = db_session.query(Application).count()
    interview_count = db_session.query(InterviewResult).count()

    response = auth_client.post(
        f"/api/v1/dashboard/applications/{eligible_application.id}/decision",
        json={"decision": "rejected"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["hiring_decision"] == HIRING_DECISION_REJECTED
    assert body["id"] == eligible_application.id
    assert "interview_token" not in body

    db_session.refresh(eligible_application)
    db_session.refresh(other)
    assert eligible_application.hiring_decision == HIRING_DECISION_REJECTED
    assert other.hiring_decision == HIRING_DECISION_PENDING
    assert db_session.query(Candidate).count() == candidate_count
    assert db_session.query(Application).count() == application_count
    assert db_session.query(InterviewResult).count() == interview_count

    assessment = auth_client.get(
        f"/api/v1/dashboard/applications/{eligible_application.id}/interview-result"
    )
    assert assessment.status_code == 200
    assert assessment.json()["qa_transcript"]["turns"][0]["question"] == "Q1"

    listed = auth_client.get("/api/v1/dashboard/applications").json()
    rejected_row = next(row for row in listed if row["id"] == eligible_application.id)
    other_row = next(row for row in listed if row["id"] == other.id)
    assert rejected_row["hiring_decision"] == HIRING_DECISION_REJECTED
    assert other_row["hiring_decision"] == HIRING_DECISION_PENDING

    again = auth_client.post(
        f"/api/v1/dashboard/applications/{eligible_application.id}/decision",
        json={"decision": "rejected"},
    )
    assert again.status_code == 200
    assert again.json()["hiring_decision"] == HIRING_DECISION_REJECTED
    assert db_session.query(InterviewResult).count() == interview_count


def test_reject_missing_application_returns_safe_error(auth_client):
    response = auth_client.post(
        "/api/v1/dashboard/applications/99999/decision",
        json={"decision": "rejected"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"
