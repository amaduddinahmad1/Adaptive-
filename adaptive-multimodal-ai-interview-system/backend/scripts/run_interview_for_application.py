"""
run_interview_for_application.py

Runs the live interview stage for an already-eligible Application row
(created by run_pipeline_smoketest.py) and persists the result to Postgres
-- the first time this codebase's interview pipeline (Days 1-7) has been
exercised end-to-end with a real database write, and the first time an
InterviewResult row has ever been created.

Deliberately separate from run_pipeline_smoketest.py, and deliberately
loads CandidateProfile/JobRequirementProfile back out of the Application's
own stored JSONB (candidate_profile / job_profile_snapshot) rather than
re-parsing the JD/CV via Gemini again -- this guarantees the interview runs
against exactly what was actually judged eligible, and costs two fewer real
API calls.

No manual application_id input: _find_next_application_to_interview()
auto-selects the most recent (highest id) application that is
overall_eligible=True and has no existing interview_result, via a query
verified empirically against the real database before being finalized
(SELECT ... WHERE overall_eligible AND NOT EXISTS(interview_result),
ORDER BY id DESC). If more than one application qualifies, the full list
is printed as a visibility warning before auto-picking the newest -- this
is a real, observed case, not hypothetical: application_id=4 (eligible via
a fail-safe MANUAL_REVIEW_REQUIRED path during a provider outage, not a
genuine confirmed match) sat alongside application_id=6 (genuinely
confirmed) as simultaneously "qualifying" the first time this ran, and
would have been silently auto-picked instead of 6 had 6 not existed.

The overall_eligible=True and no-existing-interview-result checks are then
re-verified explicitly against the selected row regardless -- structurally
redundant given the query above, but kept anyway as a safety net against a
race condition or a manual DB edit between the query and the check, per
explicit instruction not to remove it just because the new selection logic
is supposed to prevent that case.

No .txt transcript file this time -- the qa_transcript/interview_plan/
gap_analysis JSONB columns on interview_results are meant to fully replace
that (per the reasoning already recorded in app/models/interview_result.py
when those columns were designed).

Known tradeoff, not addressed here: the database write happens once, at the
very end, after every question has been answered and the final assessment
generated. A crash partway through the live interview loses that run's
persistence entirely (though everything up to that point still printed to
your terminal in real time) -- unlike the old run_real_interview.py, which
flushed every line to its transcript file immediately. Incremental
persistence would fix this but wasn't part of what was approved for this
script; worth revisiting if a long interview session's resilience becomes
a real concern.

Per-question resilience to a total provider-chain outage (this crashed the
script on an earlier real run -- Gemini 503, xAI out of credits, no other
link existed yet): a question whose evaluate_answer() call exhausts every
provider in the chain is recorded in qa_transcript with
evaluation_failed=True and the error, but is NOT added to
answer_evaluations at all -- the interview continues to the next question
rather than crashing. generate_final_assessment() already tolerates
answer_evaluations being shorter than question_set (its own
reasoning_summary reports both counts), so a skipped question is correctly
excluded from the score average, never fabricated as a 0 or a pass. If
EVERY question fails this way, the script deliberately refuses to generate
a final assessment or persist an InterviewResult at all -- averaging over
zero real evaluations would silently produce the worst possible score
rather than honestly reporting "no data available."
"""

import io
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from dataclasses import asdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.llm.base import LLMProviderError
from app.db.session import get_db, get_engine
from app.models.application import Application
from app.models.interview_result import InterviewResult
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile
from app.services.assessment.day5_answer_evaluation import evaluate_answer
from app.services.assessment.day6_skill_gap_analysis import (
    analyze_cv_interview_gap,
    build_cv_claim_evidence,
    build_skill_matrix,
)
from app.services.assessment.day7_final_assessment import generate_final_assessment
from app.services.interview_intelligence.day1_interview_plan import generate_interview_plan
from app.services.interview_intelligence.day2_question_generation import generate_questions
from app.services.interview_intelligence.day3_cv_verification import verify_cv_claims
from app.services.interview_intelligence.day4_adaptive_interview import decide_next_step
from app.services.persistence.application_repository import create_interview_result


def _check_database_target() -> None:
    engine = get_engine()
    db_name = engine.url.database
    print(f"Connecting to database: {db_name!r} on {engine.url.host}:{engine.url.port}")
    assert db_name, (
        "DATABASE_URL has no database name configured (empty after the final '/') -- "
        "fix .env before proceeding."
    )


def _find_next_application_to_interview(db: Session) -> Optional[Application]:
    """
    Returns the most recent (highest id) application that is
    overall_eligible=True and has no existing interview_result, or None if
    none qualify. If more than one qualifies, prints the full list as a
    visibility warning before returning the newest -- silent in the common
    single-candidate case.
    """
    stmt = (
        select(Application)
        .where(Application.overall_eligible.is_(True))
        .where(~Application.interview_result.has())
        .order_by(Application.id.desc())
    )
    qualifying = db.execute(stmt).scalars().all()

    if not qualifying:
        return None

    if len(qualifying) > 1:
        print(
            f"WARNING: {len(qualifying)} eligible, not-yet-interviewed applications found: "
            f"{[a.id for a in qualifying]}. Using the most recent: application_id={qualifying[0].id}."
        )

    return qualifying[0]


def main() -> None:
    _check_database_target()

    db = next(get_db())
    application = _find_next_application_to_interview(db)
    if application is None:
        raise SystemExit(
            "No eligible, uninterviewed applications found. "
            "Run scripts/run_pipeline_smoketest.py first to generate one."
        )

    application_id = application.id

    # Structurally redundant given the query above, but kept anyway as a
    # safety net against a race condition or a manual DB edit between the
    # query and here -- see module docstring.
    if application.interview_result is not None:
        existing = application.interview_result
        raise SystemExit(
            f"Application {application_id} already has an interview result "
            f"(interview_result_id={existing.id}, created {existing.created_at}).\n"
            "Refusing to overwrite existing interview history. Pick a different application_id, "
            "or delete that row yourself first if you specifically intend to replace it."
        )
    if not application.overall_eligible:
        raise SystemExit(
            f"Application {application_id} is not eligible (overall_eligible=False) -- "
            "the interview stage does not run for ineligible candidates."
        )

    print(f"Loaded application_id={application.id} (candidate_id={application.candidate_id}, "
          f"job_posting_id={application.job_posting_id}), confirmed overall_eligible=True.")

    candidate = CandidateProfile.model_validate(application.candidate_profile)
    jd_profile = JobRequirementProfile.model_validate(application.job_profile_snapshot)

    print("\n" + "=" * 90)
    print("STAGE 1: generate_interview_plan() [Day 1]")
    print("=" * 90)
    plan = generate_interview_plan(jd_profile, candidate)
    print(f"Skill areas: {plan.skill_areas}")
    print(f"Estimated time: {plan.estimated_time} minutes")

    print("\n" + "=" * 90)
    print("STAGE 2: generate_questions() [Day 2]")
    print("=" * 90)
    questions = generate_questions(jd_profile, candidate, plan)
    print(f"{len(questions)} question(s) generated.")

    print("\n" + "=" * 90)
    print("STAGE 3: verify_cv_claims() [Day 3]")
    print("=" * 90)
    cv_claims = verify_cv_claims(candidate)
    print(f"{len(cv_claims)} CV claim(s) identified for verification.")

    print("\n" + "=" * 90)
    print("STAGE 4: LIVE INTERVIEW -- your real answers -> evaluate_answer() [Day 5, real Gemini calls] "
          "-> decide_next_step() [Day 4]")
    print("=" * 90)

    qa_transcript = []
    answer_evaluations = []
    current_difficulty = questions[0].baseline_difficulty if questions else "Mid-Level"
    previous_question_type = questions[0].question_type if questions else "Role-specific"

    for i, question in enumerate(questions):
        print(f"\n>>> Question {i + 1}/{len(questions)} "
              f"({question.question_type} / {question.expected_knowledge_area}, "
              f"difficulty: {question.baseline_difficulty}):")
        print(question.question_text)

        print()
        answer_text = input("Your answer: ").strip()

        try:
            evaluation = evaluate_answer(question, answer_text)
        except LLMProviderError as exc:
            # Every provider in the chain failed for this question (the
            # exact failure mode that crashed this script previously): skip
            # it rather than crash the whole session. Not added to
            # answer_evaluations at all -- generate_final_assessment()
            # already averages over however many answers actually scored
            # (question_set and answer_evaluations are allowed to differ in
            # length; see its reasoning_summary), so a skipped question is
            # correctly excluded rather than fabricated as a 0 or a pass.
            print(f"  -> EVALUATION FAILED (all providers exhausted): {exc}")
            print("  -> Skipping this question; continuing to the next one.")
            qa_transcript.append({
                "question": asdict(question),
                "answer": answer_text,
                "evaluation": None,
                "evaluation_failed": True,
                "error": str(exc),
            })
            continue

        print(f"  -> weighted_total={evaluation.weighted_total}, pass_fail={evaluation.pass_fail}")
        answer_evaluations.append(evaluation)

        decision = decide_next_step(
            current_difficulty=current_difficulty,
            previous_question_type=previous_question_type,
            answer_evaluation=asdict(evaluation),
        )
        current_difficulty = decision.next_difficulty
        previous_question_type = decision.next_question_type

        qa_transcript.append({
            "question": asdict(question),
            "answer": answer_text,
            "evaluation": asdict(evaluation),
            "evaluation_failed": False,
            "error": None,
        })

    failed_count = sum(1 for turn in qa_transcript if turn["evaluation_failed"])
    if failed_count:
        print(f"\n{failed_count}/{len(questions)} question(s) could not be evaluated (provider chain exhausted).")

    if not answer_evaluations:
        print("\n" + "=" * 90)
        print("INTERVIEW COULD NOT BE SCORED")
        print("=" * 90)
        print(
            f"All {len(questions)} question(s) failed evaluation (every provider in the chain was "
            "exhausted for every question). Refusing to generate a final assessment or persist an "
            "InterviewResult from zero real data -- that would silently produce the worst possible "
            "score (an average over an empty list) rather than honestly reporting 'no data', and could "
            "wrongly recommend declining a candidate who was never actually evaluated. Re-run this "
            "script once the provider outage has cleared."
        )
        db.close()
        return

    print("\n" + "=" * 90)
    print("STAGE 5: build_cv_claim_evidence() / build_skill_matrix() / analyze_cv_interview_gap() [Day 6]")
    print("=" * 90)
    cv_claim_evidence = build_cv_claim_evidence(candidate, cv_claims)
    skill_matrix = build_skill_matrix(answer_evaluations, jd_profile.required_skills)
    gap_analysis = analyze_cv_interview_gap(cv_claim_evidence.matched_claims, skill_matrix)

    print("\n" + "=" * 90)
    print("STAGE 6: generate_final_assessment() [Day 7]")
    print("=" * 90)
    final_report = generate_final_assessment(
        candidate_profile=candidate,
        job_requirements=jd_profile,
        interview_plan=plan,
        question_set=questions,
        answer_evaluations=answer_evaluations,
        skill_matrix=skill_matrix,
        gap_analysis=gap_analysis,
        unmatched_cv_claims=cv_claim_evidence.unmatched_claims,
    )

    print("\n" + "=" * 90)
    print("FINAL ASSESSMENT REPORT")
    print("=" * 90)
    print(f"Recommendation: {final_report.recommendation}")
    print(f"Reason: {final_report.recommendation_reason}")
    print(f"Eligibility result (interview-stage recheck): {final_report.eligibility_result}")
    print(f"Problem-solving performance: {final_report.problem_solving_performance}")
    print(f"Communication performance: {final_report.communication_performance}")
    print(f"Strengths: {final_report.strengths}")
    print(f"Areas requiring evaluation: {final_report.areas_requiring_evaluation}")
    print(f"Reasoning summary: {final_report.reasoning_summary}")

    print("\n" + "=" * 90)
    print("PERSISTING TO DATABASE")
    print("=" * 90)
    try:
        interview_result = create_interview_result(db, application, final_report, plan, qa_transcript, gap_analysis)
        db.commit()
        print(f"Committed: interview_result_id={interview_result.id}, application_id={application.id}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\n" + "=" * 90)
    print("RE-QUERYING FROM THE DATABASE TO CONFIRM THE WRITE LANDED")
    print("=" * 90)
    verify_db = next(get_db())
    try:
        row = verify_db.get(InterviewResult, interview_result.id)
        print(f"interview_results: id={row.id}, application_id={row.application_id}, "
              f"recommendation={row.recommendation}, interview_eligibility_result={row.interview_eligibility_result}")
    finally:
        verify_db.close()


if __name__ == "__main__":
    main()
