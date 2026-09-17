"""
HTTP lifecycle tests for voice session endpoints.

Voice sessions are in-memory and must be created from a real Application row.
candidate_id and job_id are not accepted on the create request; the Application
is the sole source of truth for candidate and job identity.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.models.application import HIRING_DECISION_REJECTED, Application
from app.models.interview_result import InterviewResult
from app.schemas.voice_session import InterviewStatus, ConnectionStatus
from tests.conftest import make_mock_voice_service


def _create_payload(application: Application, language: str = "en") -> dict:
    return {"application_id": application.id, "language": language}


def _expected_identity(application: Application) -> str:
    return f"candidate-{application.candidate_id}"


def test_health():
    app.state.voice_service = make_mock_voice_service()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert "app" in body


def test_voice_session_http_lifecycle(client: TestClient, eligible_application: Application):
    create_response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    )
    assert create_response.status_code == 200
    created = create_response.json()
    session_id = created["session_id"]
    assert created["application_id"] == eligible_application.id
    assert created["candidate_id"] == str(eligible_application.candidate_id)
    assert created["job_id"] == str(eligible_application.job_posting_id)
    assert created["interview_status"] == InterviewStatus.PENDING
    assert created["connection_status"] == ConnectionStatus.DISCONNECTED

    get_response = client.get(f"/api/v1/voice/sessions/{session_id}")
    assert get_response.status_code == 200
    assert get_response.json()["session_id"] == session_id
    assert get_response.json()["interview_status"] == InterviewStatus.PENDING
    assert get_response.json()["application_id"] == eligible_application.id

    start_response = client.post(f"/api/v1/voice/sessions/{session_id}/start")
    assert start_response.status_code == 200
    start_body = start_response.json()
    identity = _expected_identity(eligible_application)
    assert start_body["status"] == "started"
    assert start_body["session_id"] == session_id
    assert start_body["room_name"] == f"interview-{session_id}"
    assert start_body["identity"] == identity
    assert start_body["token"] == f"mock_token_interview-{session_id}_{identity}"
    assert "livekit_url" in start_body

    session_after_start = client.get(f"/api/v1/voice/sessions/{session_id}")
    assert session_after_start.status_code == 200
    assert "token" not in session_after_start.json()

    status_response = client.get(f"/api/v1/voice/sessions/{session_id}/status")
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["session_id"] == session_id
    assert status_body["interview_status"] == InterviewStatus.IN_PROGRESS
    assert status_body["connection_status"] == ConnectionStatus.CONNECTED

    end_response = client.post(f"/api/v1/voice/sessions/{session_id}/end")
    assert end_response.status_code == 200
    assert end_response.json()["status"] == "ended"
    assert end_response.json()["session_id"] == session_id

    completed_status = client.get(f"/api/v1/voice/sessions/{session_id}/status")
    assert completed_status.status_code == 200
    completed_body = completed_status.json()
    assert completed_body["interview_status"] == InterviewStatus.COMPLETED
    assert completed_body["connection_status"] == ConnectionStatus.DISCONNECTED

    completed_session = client.get(f"/api/v1/voice/sessions/{session_id}")
    assert completed_session.status_code == 200
    assert completed_session.json()["interview_status"] == InterviewStatus.COMPLETED

    restart = client.post(f"/api/v1/voice/sessions/{session_id}/start")
    assert restart.status_code == 400
    opening = client.get(
        f"/api/v1/voice/sessions/{session_id}/next-question",
        params={"claim_opening": "true", "owner_id": "job-late"},
    ).json()
    assert opening["allow_opening_speech"] is False
    assert opening["question"] is None


JOIN_CONTRACT_FIELDS = {
    "status",
    "session_id",
    "livekit_url",
    "room_name",
    "token",
    "identity",
}


def test_start_returns_frontend_livekit_join_contract(
    client: TestClient, eligible_application: Application
):
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    session_id = created["session_id"]
    identity = _expected_identity(eligible_application)

    start_body = client.post(f"/api/v1/voice/sessions/{session_id}/start").json()

    assert set(start_body.keys()) == JOIN_CONTRACT_FIELDS
    assert start_body["status"] == "started"
    assert start_body["session_id"] == session_id
    assert start_body["room_name"] == f"interview-{session_id}"
    assert start_body["identity"] == identity
    assert start_body["token"] == f"mock_token_interview-{session_id}_{identity}"
    assert isinstance(start_body["livekit_url"], str)

    stored = client.get(f"/api/v1/voice/sessions/{session_id}").json()
    assert "token" not in stored
    assert stored["session_id"] == session_id
    assert stored["application_id"] == eligible_application.id


def test_create_session_from_valid_application(
    client: TestClient, eligible_application: Application
):
    response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["application_id"] == eligible_application.id
    assert body["candidate_id"] == str(eligible_application.candidate_id)
    assert body["job_id"] == str(eligible_application.job_posting_id)
    assert isinstance(body["application_id"], int)


def test_create_session_nonexistent_application_does_not_store_or_insert(
    client: TestClient, db_session
):
    application_count = db_session.query(Application).count()
    interview_result_count = db_session.query(InterviewResult).count()
    missing_id = 999999

    response = client.post(
        "/api/v1/voice/sessions",
        json={"application_id": missing_id, "language": "en"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"
    assert app.state.voice_service.session_manager.list_sessions() == []
    assert db_session.query(Application).count() == application_count
    assert db_session.query(InterviewResult).count() == interview_result_count


def test_create_session_ineligible_application_is_rejected(
    client: TestClient, ineligible_application: Application
):
    response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(ineligible_application),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Application is not eligible for interview"
    assert app.state.voice_service.session_manager.list_sessions() == []


def test_create_request_uses_application_as_sole_source_of_truth(
    client: TestClient, eligible_application: Application
):
    """
    candidate_id and job_id were removed from POST /voice/sessions.
    Extra caller IDs must not become the session's candidate/job identity.
    """
    response = client.post(
        "/api/v1/voice/sessions",
        json={
            "application_id": eligible_application.id,
            "candidate_id": "unrelated-candidate",
            "job_id": "unrelated-job",
            "language": "en",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["application_id"] == eligible_application.id
    assert body["candidate_id"] == str(eligible_application.candidate_id)
    assert body["job_id"] == str(eligible_application.job_posting_id)
    assert body["candidate_id"] != "unrelated-candidate"
    assert body["job_id"] != "unrelated-job"


def test_start_uses_application_candidate_identity_not_query_param(
    client: TestClient, eligible_application: Application
):
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    session_id = created["session_id"]
    identity = _expected_identity(eligible_application)

    start_body = client.post(
        f"/api/v1/voice/sessions/{session_id}/start",
        params={"candidate": "unrelated-candidate"},
    ).json()

    assert start_body["identity"] == identity
    assert start_body["identity"] != "candidate-unrelated-candidate"


def test_voice_session_not_found(client: TestClient):
    missing_id = "does-not-exist"
    assert client.get(f"/api/v1/voice/sessions/{missing_id}").status_code == 404
    assert client.get(f"/api/v1/voice/sessions/{missing_id}/status").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{missing_id}/start").status_code == 404
    assert client.post(f"/api/v1/voice/sessions/{missing_id}/end").status_code == 404
    assert client.get(f"/api/v1/voice/sessions/{missing_id}/next-question").status_code == 404
    assert (
        client.post(
            f"/api/v1/voice/sessions/{missing_id}/response",
            json={"text": "hello"},
        ).status_code
        == 404
    )


def test_start_initializes_real_question_engine_over_http(
    client: TestClient, eligible_application: Application, db_session
):
    from app.schemas.candidate import CandidateProfile
    from app.schemas.job import JobRequirementProfile
    from app.services.interview_intelligence.day1_interview_plan import generate_interview_plan
    from app.services.interview_intelligence.day2_question_generation import generate_questions

    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    session_id = created["session_id"]
    interview_result_count = db_session.query(InterviewResult).count()

    start_body = client.post(f"/api/v1/voice/sessions/{session_id}/start").json()
    assert start_body["status"] == "started"
    assert start_body["identity"] == _expected_identity(eligible_application)
    assert start_body["room_name"] == f"interview-{session_id}"

    expected = generate_questions(
        JobRequirementProfile.model_validate(eligible_application.job_profile_snapshot),
        CandidateProfile.model_validate(eligible_application.candidate_profile),
        generate_interview_plan(
            JobRequirementProfile.model_validate(eligible_application.job_profile_snapshot),
            CandidateProfile.model_validate(eligible_application.candidate_profile),
        ),
    )
    question_body = client.get(
        f"/api/v1/voice/sessions/{session_id}/next-question"
    ).json()
    assert question_body["question"] == expected[0].question_text
    assert question_body["question"] != "Could you tell me about yourself?"
    assert question_body["allow_opening_speech"] is False
    assert db_session.query(InterviewResult).count() == interview_result_count

    first_open = client.get(
        f"/api/v1/voice/sessions/{session_id}/next-question",
        params={"claim_opening": "true", "owner_id": "job-1"},
    ).json()
    second_open = client.get(
        f"/api/v1/voice/sessions/{session_id}/next-question",
        params={"claim_opening": "true", "owner_id": "job-2"},
    ).json()
    assert first_open["allow_opening_speech"] is True
    assert first_open["question"] == expected[0].question_text
    assert second_open["allow_opening_speech"] is False
    assert second_open["action"] == "stand_down"
    assert second_open["question"] == expected[0].question_text


def _patch_http_assess_answers(weighted_total: float = 72.0):
    from app.services.assessment.assessment_service import AssessmentService
    from app.services.interview_intelligence.models import AnswerEvaluation

    def _assess(*args, **kwargs):
        question_set = args[1] if len(args) >= 3 else args[0]
        question = list(question_set)[0]
        return [
            AnswerEvaluation(
                question_text=question.question_text,
                expected_knowledge_area=question.expected_knowledge_area,
                question_type=question.question_type,
                weighted_total=weighted_total,
                technical_correctness=weighted_total,
                problem_solving=weighted_total,
                completeness=weighted_total,
                reasoning=weighted_total,
                communication=weighted_total,
                pass_fail=weighted_total >= 65.0,
                skills_covered=list(question.skills_covered),
                recommendation_note="test evaluation",
            )
        ]

    from unittest.mock import patch

    return patch.object(AssessmentService, "assess_answers", side_effect=_assess)


def test_http_end_without_answers_does_not_persist_interview_result(
    client: TestClient, eligible_application: Application, db_session
):
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    session_id = created["session_id"]
    client.post(f"/api/v1/voice/sessions/{session_id}/start")
    before = db_session.query(InterviewResult).count()

    end_response = client.post(f"/api/v1/voice/sessions/{session_id}/end")

    assert end_response.status_code == 200
    body = end_response.json()
    assert body["status"] == "ended"
    assert body["session_id"] == session_id
    assert body["assessment_status"] == "not_persistable"
    assert "not persistable yet" in body["detail"]
    assert body["interview_result_id"] is None
    assert db_session.query(InterviewResult).count() == before


def test_http_completed_interview_persists_one_interview_result(
    client: TestClient, eligible_application: Application, db_session
):
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    session_id = created["session_id"]
    start_body = client.post(f"/api/v1/voice/sessions/{session_id}/start").json()
    assert start_body["status"] == "started"

    question = client.get(f"/api/v1/voice/sessions/{session_id}/next-question").json()
    assert question["question"]
    assert question["question"] != "Could you tell me about yourself?"

    with _patch_http_assess_answers():
        response_body = client.post(
            f"/api/v1/voice/sessions/{session_id}/response",
            json={"text": "I used FastAPI with PostgreSQL in production."},
        ).json()

    assert response_body["evaluation"]["weighted_total"] == 72.0
    assert "score" not in response_body["evaluation"]
    assert response_body["next_question"] != "Could you tell me about yourself?"
    before = db_session.query(InterviewResult).count()

    end_response = client.post(f"/api/v1/voice/sessions/{session_id}/end")
    assert end_response.status_code == 200
    body = end_response.json()
    assert body["status"] == "ended"
    assert body["assessment_status"] == "persisted"
    assert body["application_id"] == eligible_application.id
    assert body["interview_result_id"] is not None
    assert body["recommendation"]
    assert body["interview_eligibility_result"]

    results = (
        db_session.query(InterviewResult)
        .filter(InterviewResult.application_id == eligible_application.id)
        .all()
    )
    assert len(results) == before + 1
    result = results[0]
    assert result.application_id == eligible_application.id
    assert result.recommendation == body["recommendation"]
    assert result.interview_eligibility_result == body["interview_eligibility_result"]
    assert result.interview_plan is not None
    assert result.qa_transcript is not None
    assert "turns" in result.qa_transcript
    assert result.gap_analysis is not None
    assert "entries" in result.gap_analysis

    repeat = client.post(f"/api/v1/voice/sessions/{session_id}/end").json()
    assert repeat["assessment_status"] == "already_persisted"
    assert repeat["interview_result_id"] == body["interview_result_id"]
    assert (
        db_session.query(InterviewResult)
        .filter(InterviewResult.application_id == eligible_application.id)
        .count()
        == 1
    )


def test_http_ineligible_application_end_does_not_persist(
    client: TestClient, eligible_application: Application, db_session
):
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    session_id = created["session_id"]
    client.post(f"/api/v1/voice/sessions/{session_id}/start")
    with _patch_http_assess_answers():
        client.post(
            f"/api/v1/voice/sessions/{session_id}/response",
            json={"text": "A detailed production answer."},
        )

    eligible_application.overall_eligible = False
    db_session.commit()
    before = db_session.query(InterviewResult).count()

    body = client.post(f"/api/v1/voice/sessions/{session_id}/end").json()
    assert body["assessment_status"] == "not_persistable"
    assert "not eligible" in body["detail"]
    assert db_session.query(InterviewResult).count() == before


def test_start_marks_invitation_token_used(
    client: TestClient, db_session, eligible_application: Application
):
    from app.services.persistence.application_repository import generate_interview_token

    generate_interview_token(db_session, eligible_application)
    db_session.commit()
    db_session.refresh(eligible_application)
    assert eligible_application.token_used is False

    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    client.post(f"/api/v1/voice/sessions/{created['session_id']}/start")

    db_session.refresh(eligible_application)
    assert bool(eligible_application.token_used) is True


def test_create_session_rejects_expired_invitation(
    client: TestClient, db_session, eligible_application: Application
):
    from datetime import datetime, timedelta, timezone

    eligible_application.interview_token = "expired-session-token"
    eligible_application.token_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()

    response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_create_session_rejects_completed_interview(
    client: TestClient, db_session, eligible_application: Application
):
    db_session.add(
        InterviewResult(
            application_id=eligible_application.id,
            final_report={},
            recommendation="Hire",
            interview_eligibility_result="Pass",
        )
    )
    db_session.commit()

    response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    )
    assert response.status_code == 409
    assert "already been completed" in response.json()["detail"]


def test_create_session_rejects_rejected_application(
    client: TestClient, db_session, eligible_application: Application
):
    eligible_application.hiring_decision = HIRING_DECISION_REJECTED
    db_session.commit()
    response = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    )
    assert response.status_code == 400
    assert "rejected" in response.json()["detail"].lower()
    assert app.state.voice_service.session_manager.list_sessions() == []


def test_start_rejects_rejected_application_before_interview_begins(
    client: TestClient, db_session, eligible_application: Application
):
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    eligible_application.hiring_decision = HIRING_DECISION_REJECTED
    db_session.commit()
    response = client.post(f"/api/v1/voice/sessions/{created['session_id']}/start")
    assert response.status_code == 400
    assert "rejected" in response.json()["detail"].lower()


def test_start_question_engine_crash_fails_without_exposing_traceback(
    client: TestClient, eligible_application: Application, monkeypatch
):
    def _crash(*args, **kwargs):
        raise IndexError("list index out of range")

    monkeypatch.setattr(
        "app.integrations.pipecat.interview_bridge.generate_questions",
        _crash,
    )
    created = client.post(
        "/api/v1/voice/sessions",
        json=_create_payload(eligible_application),
    ).json()
    response = client.post(f"/api/v1/voice/sessions/{created['session_id']}/start")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "The interview session is unavailable right now."
    assert "IndexError" not in str(body)
    assert "Traceback" not in str(body)
