"""
Phase 3: real Interview Intelligence on the voice interview path.
Phase 2B: persist a real FinalAssessmentReport when genuine evaluations exist.
"""
from dataclasses import asdict
from unittest.mock import patch

import pytest

from app.agents.interview_agent import InterviewAgent
from app.integrations.pipecat.interview_bridge import (
    HttpInterviewBridge,
    InterviewIntelligenceBridge,
    MockInterviewBridge,
)
from app.models.application import Application
from app.models.interview_result import InterviewResult
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile
from app.schemas.voice_session import InterviewStatus
from app.services.assessment.assessment_service import AssessmentService
from app.services.assessment.day6_skill_gap_analysis import build_cv_claim_evidence
from app.services.interview_intelligence.day2_question_generation import generate_questions
from app.services.interview_intelligence.day4_adaptive_interview import decide_next_step
from app.services.interview_intelligence.models import AnswerEvaluation, Question
from app.services.voice.service import VoiceInterviewService
from tests.conftest import make_mock_voice_service
from tests.db_helpers import SAMPLE_CANDIDATE_PROFILE, SAMPLE_JOB_PROFILE


def _expected_questions(application: Application):
    candidate = CandidateProfile.model_validate(application.candidate_profile)
    job = JobRequirementProfile.model_validate(application.job_profile_snapshot)
    from app.services.interview_intelligence.day1_interview_plan import generate_interview_plan

    return generate_questions(job, candidate, generate_interview_plan(job, candidate))


def _fake_evaluation(question: Question, weighted_total: float = 72.0) -> AnswerEvaluation:
    return AnswerEvaluation(
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


def _patch_assess_answers(weighted_total: float = 72.0):
    def _assess(*args, **kwargs):
        question_set = args[1] if len(args) >= 3 else args[0]
        questions = list(question_set)
        assert questions, "AssessmentService.assess_answers received no questions"
        return [_fake_evaluation(questions[0], weighted_total=weighted_total)]

    return patch.object(AssessmentService, "assess_answers", side_effect=_assess)


def _expected_completion_artifacts(runtime):
    evidence = build_cv_claim_evidence(runtime.candidate, runtime.cv_claims)
    return AssessmentService().build_report_artifacts(
        runtime.candidate,
        runtime.job,
        list(runtime.asked),
        list(runtime.evaluations),
        cv_claims=evidence.matched_claims,
        unmatched_cv_claims=evidence.unmatched_claims,
        interview_plan=runtime.plan,
    )


async def _start_and_answer(service, application, weighted_total: float = 72.0):
    session = await service.create_session(application)
    await service.start_interview(session.session_id, application=application)
    with _patch_assess_answers(weighted_total=weighted_total):
        await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )
    return session


@pytest.mark.asyncio
async def test_eligible_application_starts_real_interview_intelligence(
    eligible_application: Application,
):
    service = make_mock_voice_service()
    session = await service.create_session(eligible_application)

    with patch(
        "app.integrations.pipecat.interview_bridge.generate_questions",
        wraps=generate_questions,
    ) as generate_spy:
        start_res = await service.start_interview(
            session.session_id, application=eligible_application
        )

    assert start_res["status"] == "started"
    assert isinstance(service.bridge, InterviewIntelligenceBridge)
    assert not isinstance(service.bridge, MockInterviewBridge)
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime is not None
    assert runtime.application_id == eligible_application.id
    assert runtime.questions
    generate_spy.assert_called_once()
    expected = _expected_questions(eligible_application)
    assert (await service.get_next_question(session.session_id)) == expected[0].question_text
    assert expected[0].question_text != "Could you tell me about yourself?"


@pytest.mark.asyncio
async def test_candidate_and_job_context_come_from_application(
    eligible_application: Application,
):
    service = VoiceInterviewService()
    session = await service.create_session(eligible_application)

    with patch(
        "app.integrations.pipecat.interview_bridge.generate_questions",
        wraps=generate_questions,
    ) as generate_spy:
        await service.start_interview(session.session_id, application=eligible_application)

    job_arg, candidate_arg, _plan = generate_spy.call_args.args
    assert session.candidate_id == str(eligible_application.candidate_id)
    assert session.job_id == str(eligible_application.job_posting_id)
    assert candidate_arg == CandidateProfile.model_validate(
        eligible_application.candidate_profile
    )
    assert job_arg == JobRequirementProfile.model_validate(
        eligible_application.job_profile_snapshot
    )
    assert eligible_application.candidate_profile == SAMPLE_CANDIDATE_PROFILE
    assert eligible_application.job_profile_snapshot == SAMPLE_JOB_PROFILE
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime.candidate_id == eligible_application.candidate_id
    assert runtime.job_posting_id == eligible_application.job_posting_id


@pytest.mark.asyncio
async def test_real_question_generation_and_answer_evaluation_and_adaptive_controller(
    eligible_application: Application,
):
    service = make_mock_voice_service()
    session = await service.create_session(eligible_application)
    await service.start_interview(session.session_id, application=eligible_application)

    expected = _expected_questions(eligible_application)
    first_question = await service.get_next_question(session.session_id)
    assert first_question == expected[0].question_text
    current = service.bridge.get_runtime(session.session_id).current
    assert current is not None

    with _patch_assess_answers(weighted_total=72.0) as assess_spy, patch(
        "app.integrations.pipecat.interview_bridge.decide_next_step",
        wraps=decide_next_step,
    ) as decide_spy:
        result = await service.process_candidate_response(
            session.session_id, "I used FastAPI with PostgreSQL in production."
        )

    assess_spy.assert_called_once()
    decide_spy.assert_called_once()
    evaluation = result["evaluation"]
    assert "score" not in evaluation
    assert evaluation.get("feedback") != "Good response"
    assert evaluation["weighted_total"] == 72.0
    assert result["evaluation"]["question_text"] == first_question
    assert result["next_question"]
    assert result["next_question"] != first_question
    assert result["next_question"] != "Could you tell me about yourself?"
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime.evaluations
    assert runtime.last_decision is not None
    assert runtime.transcript


@pytest.mark.asyncio
async def test_intelligence_failure_does_not_fall_back_to_mock(
    eligible_application: Application,
):
    service = make_mock_voice_service()
    session = await service.create_session(eligible_application)

    with patch(
        "app.integrations.pipecat.interview_bridge.generate_questions",
        return_value=[],
    ):
        with pytest.raises(RuntimeError, match="no questions"):
            await service.start_interview(
                session.session_id, application=eligible_application
            )

    retrieved = await service.get_session(session.session_id)
    assert retrieved.interview_status == InterviewStatus.PENDING
    assert service.bridge.get_runtime(session.session_id) is None


@pytest.mark.asyncio
async def test_end_with_zero_evaluations_does_not_create_interview_result(
    eligible_application: Application, db_session
):
    service = make_mock_voice_service()
    session = await service.create_session(eligible_application)
    await service.start_interview(session.session_id, application=eligible_application)
    before = db_session.query(InterviewResult).count()

    end_res = await service.end_interview(session.session_id, db=db_session)

    assert end_res["status"] == "ended"
    assert end_res["assessment_status"] == "not_persistable"
    assert "not persistable yet" in end_res["detail"]
    assert end_res["interview_result_id"] is None
    assert db_session.query(InterviewResult).count() == before
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime is not None
    assert runtime.evaluations == []
    assert runtime.plan is not None


@pytest.mark.asyncio
async def test_completed_interview_persists_one_interview_result_from_final_assessment(
    eligible_application: Application, db_session
):
    service = make_mock_voice_service()
    session = await _start_and_answer(service, eligible_application)
    runtime = service.bridge.get_runtime(session.session_id)
    assert runtime is not None
    assert runtime.evaluations
    expected_report, expected_gap = _expected_completion_artifacts(runtime)
    before = db_session.query(InterviewResult).count()

    end_res = await service.end_interview(session.session_id, db=db_session)

    assert end_res["status"] == "ended"
    assert end_res["assessment_status"] == "persisted"
    assert end_res["application_id"] == eligible_application.id
    assert end_res["recommendation"] == expected_report.recommendation
    assert end_res["interview_eligibility_result"] == expected_report.eligibility_result
    assert db_session.query(InterviewResult).count() == before + 1

    result = (
        db_session.query(InterviewResult)
        .filter(InterviewResult.application_id == eligible_application.id)
        .one()
    )
    assert result.id == end_res["interview_result_id"]
    assert result.application_id == runtime.application_id
    assert result.application_id == eligible_application.id
    assert result.recommendation == expected_report.recommendation
    assert result.interview_eligibility_result == expected_report.eligibility_result
    assert float(result.problem_solving_performance) == expected_report.problem_solving_performance
    assert float(result.communication_performance) == expected_report.communication_performance
    assert result.interview_plan == asdict(runtime.plan)
    assert result.qa_transcript == {"turns": runtime.transcript}
    assert result.gap_analysis == {"entries": [asdict(entry) for entry in expected_gap]}
    assert result.final_report == asdict(expected_report)
    assert service.bridge.get_runtime(session.session_id) is runtime
    assert runtime.evaluations


@pytest.mark.asyncio
async def test_repeated_end_does_not_create_duplicate_interview_result(
    eligible_application: Application, db_session
):
    service = make_mock_voice_service()
    session = await _start_and_answer(service, eligible_application)

    first = await service.end_interview(session.session_id, db=db_session)
    second = await service.end_interview(session.session_id, db=db_session)

    assert first["assessment_status"] == "persisted"
    assert second["assessment_status"] == "already_persisted"
    assert second["interview_result_id"] == first["interview_result_id"]
    assert (
        db_session.query(InterviewResult)
        .filter(InterviewResult.application_id == eligible_application.id)
        .count()
        == 1
    )


@pytest.mark.asyncio
async def test_ineligible_application_cannot_produce_interview_result(
    eligible_application: Application, db_session
):
    service = make_mock_voice_service()
    session = await _start_and_answer(service, eligible_application)
    before = db_session.query(InterviewResult).count()

    eligible_application.overall_eligible = False
    db_session.commit()

    end_res = await service.end_interview(session.session_id, db=db_session)

    assert end_res["assessment_status"] == "not_persistable"
    assert "not eligible" in end_res["detail"]
    assert end_res["interview_result_id"] is None
    assert db_session.query(InterviewResult).count() == before
    assert service.bridge.get_runtime(session.session_id) is not None


def test_voice_agent_default_bridge_is_http_not_mock():
    from unittest.mock import MagicMock, patch as patch_fn

    with patch_fn("app.agents.interview_agent.Agent.__init__", return_value=None), patch_fn(
        "app.agents.interview_agent.WhisperLocalSTTProvider", return_value=MagicMock()
    ):
        agent = InterviewAgent()

    assert isinstance(agent._bridge, HttpInterviewBridge)
    assert not isinstance(agent._bridge, MockInterviewBridge)
