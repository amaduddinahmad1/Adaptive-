"""Recruiter data isolation: each recruiter only sees their own records."""
from decimal import Decimal

from fastapi.testclient import TestClient

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.interview_result import InterviewResult
from app.models.job_posting import JobPosting
from app.schemas.job import JobRequirementProfile
from tests.auth_helpers import authenticated_client, seed_user
from tests.db_helpers import SAMPLE_CANDIDATE_PROFILE, SAMPLE_JOB_PROFILE, seed_application
from tests.unit.test_apply_api import _apply_form, _patch_cv_pipeline


def _two_recruiter_world(db_session):
    user_a = seed_user(
        db_session, email="recruiter-a@example.com", full_name="Recruiter A"
    )
    user_b = seed_user(
        db_session, email="recruiter-b@example.com", full_name="Recruiter B"
    )
    app_a = seed_application(
        db_session,
        email="candidate-a@example.com",
        created_by_user_id=user_a.id,
    )
    app_b = seed_application(
        db_session,
        email="candidate-b@example.com",
        created_by_user_id=user_b.id,
    )
    result_b = InterviewResult(
        application_id=app_b.id,
        final_report={"recommendation": "Hire"},
        recommendation="Hire",
        interview_eligibility_result="Pass",
        qa_transcript={"turns": [{"question": "secret", "answer": "nope"}]},
    )
    db_session.add(result_b)
    db_session.commit()
    db_session.refresh(result_b)
    return user_a, user_b, app_a, app_b, result_b


def _ids(rows):
    return {row["id"] for row in rows}


def test_each_recruiter_only_lists_own_jobs_applications_and_candidates(
    client: TestClient, db_session
):
    user_a, user_b, app_a, app_b, _result_b = _two_recruiter_world(db_session)
    client_a = authenticated_client(client, user_a)
    client_b = authenticated_client(client, user_b)

    jobs_a = client_a.get("/api/v1/dashboard/jobs").json()
    jobs_b = client_b.get("/api/v1/dashboard/jobs").json()
    assert _ids(jobs_a) == {app_a.job_posting_id}
    assert _ids(jobs_b) == {app_b.job_posting_id}

    apps_a = client_a.get("/api/v1/dashboard/applications").json()
    apps_b = client_b.get("/api/v1/dashboard/applications").json()
    assert _ids(apps_a) == {app_a.id}
    assert _ids(apps_b) == {app_b.id}

    cands_a = client_a.get("/api/v1/dashboard/candidates").json()
    cands_b = client_b.get("/api/v1/dashboard/candidates").json()
    assert _ids(cands_a) == {app_a.candidate_id}
    assert _ids(cands_b) == {app_b.candidate_id}
    assert cands_a[0]["application_count"] == 1
    assert cands_b[0]["application_count"] == 1


def test_direct_access_to_another_recruiters_records_is_blocked(
    client: TestClient, db_session
):
    user_a, _user_b, _app_a, app_b, _result_b = _two_recruiter_world(db_session)
    client_a = authenticated_client(client, user_a)

    assert client_a.get(f"/api/v1/dashboard/jobs/{app_b.job_posting_id}").status_code == 404
    assert client_a.get(f"/api/v1/dashboard/applications/{app_b.id}").status_code == 404
    assert client_a.get(f"/api/v1/dashboard/candidates/{app_b.candidate_id}").status_code == 404
    assert (
        client_a.get(
            f"/api/v1/dashboard/applications/{app_b.id}/interview-result"
        ).status_code
        == 404
    )
    reject = client_a.post(
        f"/api/v1/dashboard/applications/{app_b.id}/decision",
        json={"decision": "rejected"},
    )
    assert reject.status_code == 404
    db_session.refresh(app_b)
    assert app_b.hiring_decision != "rejected"


def test_recruiter_can_access_own_candidate_detail_and_result(
    client: TestClient, db_session
):
    _user_a, user_b, _app_a, app_b, result_b = _two_recruiter_world(db_session)
    client_b = authenticated_client(client, user_b)

    detail = client_b.get(f"/api/v1/dashboard/candidates/{app_b.candidate_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == app_b.candidate_id
    assert [row["id"] for row in body["applications"]] == [app_b.id]

    result = client_b.get(
        f"/api/v1/dashboard/applications/{app_b.id}/interview-result"
    )
    assert result.status_code == 200
    assert result.json()["id"] == result_b.id
    assert result.json()["application_id"] == app_b.id


def test_shared_candidate_only_exposes_owned_applications(
    client: TestClient, db_session
):
    user_a = seed_user(db_session, email="shared-a@example.com")
    user_b = seed_user(db_session, email="shared-b@example.com")
    candidate = Candidate(
        full_name="Shared Candidate",
        email="shared-candidate@example.com",
    )
    job_a = JobPosting(
        job_title="Backend Engineer",
        raw_jd_text="Python role A",
        parsed_profile=SAMPLE_JOB_PROFILE,
        created_by_user_id=user_a.id,
    )
    job_b = JobPosting(
        job_title="Backend Engineer",
        raw_jd_text="Python role B",
        parsed_profile=SAMPLE_JOB_PROFILE,
        created_by_user_id=user_b.id,
    )
    db_session.add_all([candidate, job_a, job_b])
    db_session.flush()
    app_a = Application(
        candidate_id=candidate.id,
        job_posting_id=job_a.id,
        candidate_profile=SAMPLE_CANDIDATE_PROFILE,
        job_profile_snapshot=SAMPLE_JOB_PROFILE,
        joining_availability="immediate",
        salary_expectation=Decimal("120000"),
        eligibility_result={"overall_eligible": True},
        overall_eligible=True,
        token_used=False,
    )
    app_b = Application(
        candidate_id=candidate.id,
        job_posting_id=job_b.id,
        candidate_profile=SAMPLE_CANDIDATE_PROFILE,
        job_profile_snapshot=SAMPLE_JOB_PROFILE,
        joining_availability="immediate",
        salary_expectation=Decimal("120000"),
        eligibility_result={"overall_eligible": True},
        overall_eligible=True,
        token_used=False,
    )
    db_session.add_all([app_a, app_b])
    db_session.commit()
    db_session.refresh(app_a)
    db_session.refresh(app_b)

    client_a = authenticated_client(client, user_a)
    detail = client_a.get(f"/api/v1/dashboard/candidates/{candidate.id}")
    assert detail.status_code == 200
    application_ids = [row["id"] for row in detail.json()["applications"]]
    assert application_ids == [app_a.id]
    listed = client_a.get("/api/v1/dashboard/candidates").json()
    assert listed[0]["id"] == candidate.id
    assert listed[0]["application_count"] == 1


def test_new_job_belongs_to_authenticated_recruiter(
    client: TestClient, db_session, monkeypatch
):
    user_a = seed_user(db_session, email="owner-a@example.com")
    user_b = seed_user(db_session, email="owner-b@example.com")
    profile = JobRequirementProfile(
        job_title="Owned Role",
        required_skills=["Python"],
        required_technologies=["Python"],
    )
    monkeypatch.setattr(
        "app.api.routes.dashboard.parse_job_description",
        lambda text: profile,
    )
    client_a = authenticated_client(client, user_a)
    client_b = authenticated_client(client, user_b)
    created = client_a.post(
        "/api/v1/dashboard/jobs",
        json={"job_title": "Owned Role", "jd_text": "Need Python."},
    )
    assert created.status_code == 200
    job_id = created.json()["id"]
    stored = db_session.query(JobPosting).filter(JobPosting.id == job_id).one()
    assert stored.created_by_user_id == user_a.id
    assert client_a.get(f"/api/v1/dashboard/jobs/{job_id}").status_code == 200
    assert client_b.get(f"/api/v1/dashboard/jobs/{job_id}").status_code == 404
    assert _ids(client_b.get("/api/v1/dashboard/jobs").json()) == set()


def test_voice_sessions_are_scoped_to_owning_recruiter(
    client: TestClient, db_session
):
    user_a = seed_user(db_session, email="session-a@example.com")
    user_b = seed_user(db_session, email="session-b@example.com")
    app_a = seed_application(
        db_session, email="session-cand-a@example.com", created_by_user_id=user_a.id
    )
    app_b = seed_application(
        db_session, email="session-cand-b@example.com", created_by_user_id=user_b.id
    )

    session_a = client.post(
        "/api/v1/voice/sessions", json={"application_id": app_a.id, "language": "en"}
    )
    session_b = client.post(
        "/api/v1/voice/sessions", json={"application_id": app_b.id, "language": "en"}
    )
    assert session_a.status_code == 200
    assert session_b.status_code == 200
    sid_a = session_a.json()["session_id"]
    sid_b = session_b.json()["session_id"]

    client_a = authenticated_client(client, user_a)
    client_b = authenticated_client(client, user_b)
    listed_a = client_a.get("/api/v1/voice/sessions").json()
    listed_b = client_b.get("/api/v1/voice/sessions").json()
    assert {row["session_id"] for row in listed_a} == {sid_a}
    assert {row["session_id"] for row in listed_b} == {sid_b}

    assert client_a.get(f"/api/v1/voice/sessions/{sid_b}").status_code == 404
    assert client_a.get(f"/api/v1/voice/sessions/{sid_b}/status").status_code == 404
    assert client.get(f"/api/v1/voice/sessions/{sid_b}").status_code == 200
    assert client.get(f"/api/v1/voice/sessions/{sid_b}/status").status_code == 200


def test_candidate_apply_and_interview_flow_remain_public(
    client: TestClient, db_session, monkeypatch
):
    user_a, user_b, app_a, app_b, _result_b = _two_recruiter_world(db_session)
    public_jobs = client.get("/api/v1/jobs")
    assert public_jobs.status_code == 200
    public_ids = _ids(public_jobs.json())
    assert app_a.job_posting_id in public_ids
    assert app_b.job_posting_id in public_ids

    _patch_cv_pipeline(monkeypatch)
    monkeypatch.setattr(
        "app.api.routes.apply.send_interview_invitation",
        lambda **kwargs: None,
    )
    data, files = _apply_form(email="public-applicant@example.com")
    apply_response = client.post(
        f"/api/v1/jobs/{app_a.job_posting_id}/apply",
        data=data,
        files=files,
    )
    assert apply_response.status_code == 200
    body = apply_response.json()
    assert body["job_posting_id"] == app_a.job_posting_id
    assert body["overall_eligible"] is True

    stored = (
        db_session.query(Application)
        .filter(Application.id == body["application_id"])
        .one()
    )
    assert stored.interview_token is not None
    resolve = client.post(
        "/api/v1/interview-invitations/resolve",
        json={"token": stored.interview_token},
    )
    assert resolve.status_code == 200
    assert resolve.json()["application_id"] == stored.id

    session = client.post(
        "/api/v1/voice/sessions",
        json={"application_id": stored.id, "language": "en"},
    )
    assert session.status_code == 200
    start = client.post(f"/api/v1/voice/sessions/{session.json()['session_id']}/start")
    assert start.status_code == 200

    client_b = authenticated_client(client, user_b)
    assert client_b.get(f"/api/v1/dashboard/applications/{stored.id}").status_code == 404
    client_a = authenticated_client(client, user_a)
    assert client_a.get(f"/api/v1/dashboard/applications/{stored.id}").status_code == 200


def test_unowned_legacy_jobs_are_hidden_from_recruiter_apis(
    client: TestClient, db_session
):
    user = seed_user(db_session, email="legacy-owner@example.com")
    legacy = seed_application(
        db_session,
        email="legacy-candidate@example.com",
        created_by_user_id=None,
    )
    owned = seed_application(
        db_session,
        email="owned-candidate@example.com",
        created_by_user_id=user.id,
    )
    auth = authenticated_client(client, user)
    jobs = auth.get("/api/v1/dashboard/jobs").json()
    apps = auth.get("/api/v1/dashboard/applications").json()
    assert _ids(jobs) == {owned.job_posting_id}
    assert _ids(apps) == {owned.id}
    assert auth.get(f"/api/v1/dashboard/jobs/{legacy.job_posting_id}").status_code == 404

    public_jobs = _ids(client.get("/api/v1/jobs").json())
    assert legacy.job_posting_id in public_jobs
    assert owned.job_posting_id in public_jobs
