"""
run_real_interview.py

A real, interactive interview run: the candidate's actual CV file and a real
JD, with the candidate typing real answers live in the terminal -- as
opposed to test_full_pipeline_e2e.py, which feeds pre-written simulated
answers through the same pipeline for automated/discovery testing.

Chain exercised (same pipeline as test_full_pipeline_e2e.py, real Gemini
calls at every LLM stage, no hand-crafted intermediate objects):

    JD text --parse_job_description()--> JobRequirementProfile
    CV file --extract_text_from_pdf/docx()--> CV text --parse_cv()--> CandidateProfile
    JobRequirementProfile --classify_requirements()--> List[ClassifiedRequirement]
    (..., ApplicationDetails [live input], RecruiterConstraints) --check_eligibility()--> EligibilityResult
    IF eligible:
        (JobRequirementProfile, CandidateProfile) --generate_interview_plan()--> InterviewPlan
        (..., InterviewPlan) --generate_questions()--> List[Question]
        CandidateProfile --verify_cv_claims()--> List[CVClaim]
        for each question: print it, input() a real live answer,
            evaluate_answer() [real Gemini call] --> AnswerEvaluation,
            decide_next_step() --> DecisionOutcome
        (CandidateProfile, cv_claims) --build_cv_claim_evidence()--> CVClaimEvidence
        (answer_evaluations, required_skills) --build_skill_matrix()--> List[SkillMatrixEntry]
        (matched_claims, skill_matrix) --analyze_cv_interview_gap()--> List[GapAnalysisEntry]
        (...) --generate_final_assessment()--> FinalAssessmentReport

Every question, answer, evaluation, and the final report are written to
my_interview_transcript.txt in this directory as a permanent record, in
addition to being printed live.

On any exception the script prints which stage failed and the full
traceback, then stops -- nothing here is fixed if it breaks; that's the
point of a real run.
"""

import json
import sys
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Optional

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.jd_intelligence.jd_parser import parse_job_description
from app.services.cv_intelligence.cv_parser import parse_cv
from app.services.cv_intelligence.extraction import CVExtractionError
from app.services.cv_intelligence.extraction.pdf_extractor import extract_text_from_pdf
from app.services.cv_intelligence.extraction.docx_extractor import extract_text_from_docx
from app.services.jd_intelligence.requirement_classifier import classify_requirements
from app.services.eligibility.eligibility_engine import (
    ApplicationDetails,
    RecruiterConstraints,
    check_eligibility,
    format_eligibility_report,
)
from app.services.interview_intelligence.day1_interview_plan import generate_interview_plan
from app.services.interview_intelligence.day2_question_generation import generate_questions
from app.services.interview_intelligence.day3_cv_verification import verify_cv_claims
from app.services.interview_intelligence.day4_adaptive_interview import decide_next_step
from app.services.assessment.day5_answer_evaluation import evaluate_answer
from app.services.assessment.day6_skill_gap_analysis import (
    build_cv_claim_evidence,
    build_skill_matrix,
    analyze_cv_interview_gap,
)
from app.services.assessment.day7_final_assessment import generate_final_assessment


SCRIPTS_DIR = Path(__file__).resolve().parent
TRANSCRIPT_PATH = SCRIPTS_DIR / "my_interview_transcript.txt"

JD_TEXT = """Job Title: AI Engineer (Entry Level)

We are looking for an AI Engineer to join our team, building and deploying
machine learning and generative AI features into production systems.

Requirements:
- 0 to 1 year of professional or internship experience in AI/ML engineering,
  or equivalent hands-on project experience.
- Strong understanding of Python and supervised/unsupervised learning,
  neural networks, and model evaluation.
- Familiarity with TensorFlow is required; PyTorch is preferred.
- Experience working with Large Language Models, RAG, and prompt
  engineering is preferred.
- Familiarity with Git is required.
- Bachelor's degree in Computer Science, Data Science, AI, or a related
  field is required.
- Experience with cloud platforms (AWS, GCP, or Azure) is preferred.
- Prior exposure to building or contributing to any AI-powered application
  or personal project is preferred.

Responsibilities:
- Assist in building, training, and evaluating machine learning models.
- Integrate LLM-based features into existing backend services.
- Write clean, well-tested Python code.
- Collaborate with senior engineers to learn production ML practices.
"""

# Proposed recruiter-side defaults for this entry-level role. Confirmed with
# the candidate at runtime (see _get_recruiter_constraints) rather than
# silently hardcoded -- press Enter to accept, or override interactively.
DEFAULT_MAX_NOTICE_PERIOD_DAYS = 30
DEFAULT_SALARY_MIN = 50000.0
DEFAULT_SALARY_MAX = 90000.0


def _find_cv_file() -> Path:
    """
    Looks for my_cv.pdf / my_cv.docx first; otherwise falls back to the
    single .pdf/.docx file present in this directory (excluding this
    script's own siblings), so a differently-named real CV file still works
    without renaming it.
    """
    for name in ("my_cv.pdf", "my_cv.docx"):
        explicit_path = SCRIPTS_DIR / name
        if explicit_path.is_file():
            return explicit_path

    known_scripts = {"run_real_interview.py", "test_full_pipeline_e2e.py"}
    candidates = [
        path
        for path in SCRIPTS_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in (".pdf", ".docx") and path.name not in known_scripts
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            f"No CV file found in {SCRIPTS_DIR}. Place your CV there as "
            "my_cv.pdf or my_cv.docx."
        )
    raise FileNotFoundError(
        f"Multiple candidate CV files found in {SCRIPTS_DIR}: "
        f"{[path.name for path in candidates]}. Rename the one to use to "
        "my_cv.pdf or my_cv.docx."
    )


def _extract_cv_text(cv_path: Path) -> str:
    if cv_path.suffix.lower() == ".pdf":
        return extract_text_from_pdf(str(cv_path))
    if cv_path.suffix.lower() == ".docx":
        return extract_text_from_docx(str(cv_path))
    raise CVExtractionError(f"Unsupported CV file type: {cv_path.suffix}")


def _prompt_float(prompt: str) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            return float(raw)
        except ValueError:
            print("Please enter a number (e.g. 60000).")


def _get_application_details() -> ApplicationDetails:
    print("\nA couple of quick questions before we check eligibility.\n")
    joining_availability = input("Your joining availability (e.g. 'immediate', '2 weeks', '30 days'): ").strip()
    salary_expectation = _prompt_float("Your salary expectation (annual, numeric only, e.g. 70000): ")
    return ApplicationDetails(joining_availability=joining_availability, salary_expectation=salary_expectation)


def _get_recruiter_constraints() -> RecruiterConstraints:
    print(
        "\nProposed recruiter-side constraints for this entry-level AI Engineer role:\n"
        f"  Max notice period: {DEFAULT_MAX_NOTICE_PERIOD_DAYS} days\n"
        f"  Salary range: ${DEFAULT_SALARY_MIN:,.0f} - ${DEFAULT_SALARY_MAX:,.0f} (annual)\n"
    )
    response = input(
        "Press Enter to accept these, or type 'min,max' to override the salary range "
        "(e.g. 55000,85000): "
    ).strip()
    if response:
        parts = [part.strip() for part in response.split(",")]
        if len(parts) != 2:
            print("Could not parse that as 'min,max' -- using the proposed defaults instead.")
            salary_min, salary_max = DEFAULT_SALARY_MIN, DEFAULT_SALARY_MAX
        else:
            try:
                salary_min, salary_max = float(parts[0]), float(parts[1])
            except ValueError:
                print("Could not parse that as 'min,max' -- using the proposed defaults instead.")
                salary_min, salary_max = DEFAULT_SALARY_MIN, DEFAULT_SALARY_MAX
    else:
        salary_min, salary_max = DEFAULT_SALARY_MIN, DEFAULT_SALARY_MAX

    return RecruiterConstraints(
        max_notice_period_days=DEFAULT_MAX_NOTICE_PERIOD_DAYS,
        salary_min=salary_min,
        salary_max=salary_max,
    )


def to_native(obj):
    if isinstance(obj, list):
        return [to_native(item) for item in obj]
    if isinstance(obj, dict):
        return {key: to_native(value) for key, value in obj.items()}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return obj


class Transcript:
    """Tees every line to both stdout and the transcript file, flushed immediately."""

    def __init__(self, path: Path):
        self._file = open(path, "w", encoding="utf-8")

    def write(self, text: str = "") -> None:
        print(text)
        self._file.write(text + "\n")
        self._file.flush()

    def show(self, label: str, obj) -> None:
        self.write(f"\n--- {label} ---")
        self.write(json.dumps(to_native(obj), indent=2, default=str))

    def banner(self, title: str) -> None:
        self.write("\n" + "=" * 90)
        self.write(title)
        self.write("=" * 90)

    def close(self) -> None:
        self._file.close()


def main() -> None:
    stage = "startup"
    log = Transcript(TRANSCRIPT_PATH)
    try:
        log.banner("STAGE 1: parse_job_description() [real Gemini call]")
        log.write("INPUT JD TEXT:\n" + JD_TEXT)
        stage = "parse_job_description"
        jd_profile = parse_job_description(JD_TEXT)
        log.show("Parsed JobRequirementProfile", jd_profile)

        log.banner("STAGE 2: extract CV text + parse_cv() [real Gemini call]")
        stage = "find/extract CV"
        cv_path = _find_cv_file()
        log.write(f"CV FILE: {cv_path}")
        cv_text = _extract_cv_text(cv_path)
        log.write("EXTRACTED CV TEXT:\n" + cv_text)

        stage = "parse_cv"
        candidate = parse_cv(cv_text)
        log.show("Parsed CandidateProfile", candidate)

        log.banner("STAGE 3: classify_requirements()")
        stage = "classify_requirements"
        classified = classify_requirements(jd_profile)
        log.show("ClassifiedRequirement list", classified)

        log.banner("STAGE 4: check_eligibility()")
        stage = "check_eligibility (collecting ApplicationDetails/RecruiterConstraints)"
        application = _get_application_details()
        constraints = _get_recruiter_constraints()
        log.show("ApplicationDetails (your live input)", application)
        log.show("RecruiterConstraints (confirmed with you)", constraints)

        stage = "check_eligibility"
        eligibility_result = check_eligibility(
            jd_profile=jd_profile,
            classified_reqs=classified,
            candidate=candidate,
            application=application,
            constraints=constraints,
        )
        log.show("EligibilityResult (structured)", eligibility_result)
        log.write("\n--- Human-readable eligibility report ---")
        log.write(format_eligibility_report(eligibility_result))

        if not eligibility_result.overall_eligible:
            log.banner("NOT ELIGIBLE -- stopping here")
            log.write(
                "check_eligibility() returned overall_eligible=False, so the interview "
                "does not proceed. See the report above for exactly which mandatory "
                "requirement(s) were not met."
            )
            return

        log.banner("ELIGIBLE -- proceeding to the live interview")

        log.banner("STAGE 5: generate_interview_plan() [Day 1]")
        stage = "generate_interview_plan"
        plan = generate_interview_plan(jd_profile, candidate)
        log.show("InterviewPlan", plan)

        log.banner("STAGE 6: generate_questions() [Day 2]")
        stage = "generate_questions"
        questions = generate_questions(jd_profile, candidate, plan)
        log.show("Generated Questions", questions)

        log.banner("STAGE 7: verify_cv_claims() [Day 3]")
        stage = "verify_cv_claims"
        cv_claims = verify_cv_claims(candidate)
        log.show("CV Claims", cv_claims)

        log.banner(
            "STAGE 8: LIVE INTERVIEW -- your real answers -> evaluate_answer() "
            "[Day 5, real Gemini calls] -> decide_next_step() [Day 4]"
        )
        answer_evaluations = []
        current_difficulty = questions[0].baseline_difficulty if questions else "Mid-Level"
        previous_question_type = questions[0].question_type if questions else "Role-specific"

        for i, question in enumerate(questions):
            log.write(
                f"\n>>> Question {i + 1}/{len(questions)} "
                f"({question.question_type} / {question.expected_knowledge_area}, "
                f"difficulty: {question.baseline_difficulty}):"
            )
            log.write(question.question_text)

            print()
            answer_text = input("Your answer: ").strip()
            log.write(f"\n>>> Your answer:\n{answer_text}")

            stage = f"evaluate_answer (question {i + 1})"
            evaluation = evaluate_answer(question, answer_text)
            log.show(f"AnswerEvaluation (question {i + 1})", evaluation)
            answer_evaluations.append(evaluation)

            stage = f"decide_next_step (after question {i + 1})"
            decision = decide_next_step(
                current_difficulty=current_difficulty,
                previous_question_type=previous_question_type,
                answer_evaluation=asdict(evaluation),
            )
            log.show(f"DecisionOutcome (after question {i + 1})", decision)

            current_difficulty = decision.next_difficulty
            previous_question_type = decision.next_question_type

        log.banner("STAGE 9: build_cv_claim_evidence() [Day 6]")
        stage = "build_cv_claim_evidence"
        cv_claim_evidence = build_cv_claim_evidence(candidate, cv_claims)
        log.show("CVClaimEvidence", cv_claim_evidence)

        log.banner("STAGE 10: build_skill_matrix() [Day 6]")
        stage = "build_skill_matrix"
        skill_matrix = build_skill_matrix(answer_evaluations, jd_profile.required_skills)
        log.show("Skill Matrix", skill_matrix)

        log.banner("STAGE 11: analyze_cv_interview_gap() [Day 6]")
        stage = "analyze_cv_interview_gap"
        gap_analysis = analyze_cv_interview_gap(cv_claim_evidence.matched_claims, skill_matrix)
        log.show("Gap Analysis", gap_analysis)

        log.banner("STAGE 12: generate_final_assessment() [Day 7]")
        stage = "generate_final_assessment"
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
        log.show("FinalAssessmentReport", final_report)

        log.banner("INTERVIEW COMPLETE")
        log.write(f"Full transcript saved to: {TRANSCRIPT_PATH}")

    except Exception as exc:
        log.banner(f"RUN FAILED AT STAGE: {stage}")
        log.write(f"Exception type: {type(exc).__name__}")
        log.write(f"Exception message: {exc}")
        log.write("\nFull traceback:\n")
        log.write(traceback.format_exc())
        log.close()
        sys.exit(1)
    else:
        log.close()


if __name__ == "__main__":
    main()
