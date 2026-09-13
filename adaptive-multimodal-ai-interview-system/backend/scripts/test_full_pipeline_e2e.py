"""
test_full_pipeline_e2e.py

First real, end-to-end run of the full pipeline with zero hand-crafted
schema objects. Every JobRequirementProfile / CandidateProfile used below is
produced by the real parsers from plain JD/CV text -- nothing is constructed
by hand in this file.

Chain exercised:

    JD text --parse_job_description()--> JobRequirementProfile
    CV text --parse_cv()--> CandidateProfile
    JobRequirementProfile --classify_requirements()--> List[ClassifiedRequirement]
    (JobRequirementProfile, classified_reqs, CandidateProfile, ApplicationDetails,
     RecruiterConstraints) --check_eligibility()--> EligibilityResult
    IF eligible:
        (JobRequirementProfile, CandidateProfile) --generate_interview_plan()--> InterviewPlan
        (..., InterviewPlan) --generate_questions()--> List[Question]
        CandidateProfile --verify_cv_claims()--> List[CVClaim]
        for each simulated answer: evaluate_answer() [real Gemini call] --> AnswerEvaluation
                                    decide_next_step() --> DecisionOutcome
        (CandidateProfile, cv_claims) --build_cv_claim_evidence()--> CVClaimEvidence
        (answer_evaluations, required_skills) --build_skill_matrix()--> List[SkillMatrixEntry]
        (matched_claims, skill_matrix) --analyze_cv_interview_gap()--> List[GapAnalysisEntry]
        (...) --generate_final_assessment()--> FinalAssessmentReport

This is a discovery run: nothing here is fixed if it breaks. On any
exception the script prints which stage failed and the full traceback,
then stops.
"""

import json
import sys
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.jd_intelligence.jd_parser import parse_job_description
from app.services.cv_intelligence.cv_parser import parse_cv
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


JD_TEXT = """Job Title: Backend Software Engineer

We are hiring a Backend Software Engineer to join our platform team building
the core services behind our payments product.

Requirements:
- Minimum 3 years of general professional software engineering experience.
- At least 2 years of hands-on experience with Python in a production environment.
- Strong skills in REST API design and SQL are required.
- Experience with GraphQL and Kubernetes is preferred but not required.
- Required technologies: Python, FastAPI, PostgreSQL, Docker.
- Preferred technologies: Redis, Kafka.
- Bachelor's degree in Computer Science, Software Engineering, or a related field is required.
- AWS Certified Developer - Associate certification is preferred.
- Prior experience in the fintech or payments domain is preferred.
- Candidates must be authorized to work in the United States without sponsorship.

Responsibilities:
- Build and maintain the RESTful APIs serving millions of requests per day.
- Take ownership of the PostgreSQL databases powering this service.
- Containerize and deploy services using Docker in a CI/CD pipeline.
- Collaborate with product and frontend teams to ship reliable backend features.
"""

CV_TEXT = """Jane Doe
Backend Software Engineer

Summary:
Backend engineer with 4 years of experience building REST APIs and
data-intensive services for high-growth startups.

Work Experience:

Backend Engineer, Meridian Payments Inc. (Jan 2022 - Present)
- Designed and implemented REST APIs using Python and FastAPI for a
  payments processing platform handling over 2 million transactions/month.
- Modeled and optimized PostgreSQL schemas, including an indexing strategy
  that cut p95 query latency by 40%.
- Containerized all services with Docker and maintained the CI pipeline
  for automated deployment.

Software Engineer, Bright Analytics (Jun 2020 - Dec 2021)
- Built internal data pipelines in Python, integrating with a PostgreSQL
  data warehouse.
- Implemented a caching layer using Redis to reduce load on the primary database.

Projects:
Payments Reconciliation Service - A FastAPI microservice that reconciles
daily transaction records between internal ledgers and external payment
processors, deployed via Docker to Kubernetes.

Skills: REST APIs, SQL, Git, Problem Solving
Technologies: Python, FastAPI, PostgreSQL, Docker, Redis, Kubernetes

Education:
B.S. in Computer Science, State University, 2020

Certifications: None

Achievements:
- Reduced payment processing error rate by 25% through improved validation logic.
- Mentored two junior engineers during onboarding.
"""

SIMULATED_ANSWERS = [
    (
        "STRONG",
        "In production, I'd design the API following REST principles with clear "
        "resource-oriented endpoints, versioning via a URL prefix like /v1/, and "
        "consistent error responses using RFC 7807 problem details. For request "
        "validation I'd use Pydantic models with strict typing, rejecting malformed "
        "payloads with a 422 before they reach business logic. For performance, I'd "
        "add database connection pooling, index the columns used in WHERE/JOIN "
        "clauses, and add Redis caching for frequently-read, rarely-changed resources "
        "with a short TTL and explicit invalidation on writes. I'd keep the API layer "
        "thin -- controllers only handle serialization/validation, business logic "
        "lives in an independently unit-tested service layer -- and add structured "
        "logging with correlation IDs so production failures can be diagnosed without "
        "redeploying. I'd also run contract tests against the OpenAPI schema so "
        "consumer-breaking changes are caught in CI before release.",
    ),
    (
        "MEDIUM",
        "I would build REST endpoints for the main resources and make sure to return "
        "proper HTTP status codes. I'd use a database to store the data and probably "
        "add some caching if things get slow. I'd also try to write some tests and "
        "maybe add logging so we can see what's going on if there's an issue. Docker "
        "would help with deployment consistency.",
    ),
    (
        "WEAK",
        "I would just make it scalable and use best practices, like microservices and "
        "cloud and maybe Kubernetes. Performance is important so I'd optimize the "
        "code. I would also make sure it's secure and follows industry standards.",
    ),
    (
        "NON_ANSWER",
        "I don't know, I haven't really worked with that before and I'm not sure how "
        "I'd approach it.",
    ),
]


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


def show(label: str, obj) -> None:
    print(f"\n--- {label} ---")
    print(json.dumps(to_native(obj), indent=2, default=str))


def banner(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def main() -> None:
    stage = "startup"
    try:
        banner("STAGE 1: parse_job_description() [real Gemini call]")
        print("INPUT JD TEXT:\n" + JD_TEXT)
        stage = "parse_job_description"
        jd_profile = parse_job_description(JD_TEXT)
        show("Parsed JobRequirementProfile", jd_profile)

        banner("STAGE 2: parse_cv() [real Gemini call]")
        print("INPUT CV TEXT:\n" + CV_TEXT)
        stage = "parse_cv"
        candidate = parse_cv(CV_TEXT)
        show("Parsed CandidateProfile", candidate)

        banner("STAGE 3: classify_requirements()")
        stage = "classify_requirements"
        classified = classify_requirements(jd_profile)
        show("ClassifiedRequirement list", classified)

        banner("STAGE 4: check_eligibility()")
        stage = "check_eligibility (constructing ApplicationDetails/RecruiterConstraints)"
        application = ApplicationDetails(
            joining_availability="2 weeks",
            salary_expectation=130000.0,
        )
        constraints = RecruiterConstraints(
            max_notice_period_days=30,
            salary_min=100000.0,
            salary_max=150000.0,
        )
        show("ApplicationDetails (recruiter-form input, not LLM-parsed)", application)
        show("RecruiterConstraints (recruiter-form input, not LLM-parsed)", constraints)

        stage = "check_eligibility"
        eligibility_result = check_eligibility(
            jd_profile=jd_profile,
            classified_reqs=classified,
            candidate=candidate,
            application=application,
            constraints=constraints,
        )
        show("EligibilityResult (structured)", eligibility_result)
        print("\n--- Human-readable eligibility report ---")
        print(format_eligibility_report(eligibility_result))

        if not eligibility_result.overall_eligible:
            banner("CANDIDATE NOT ELIGIBLE -- stopping here per the conditional chain")
            print(
                "check_eligibility() returned overall_eligible=False, so the interview "
                "pipeline (Faizan's side) is not invoked. This is the intended gate, "
                "not a failure."
            )
            return

        banner("CANDIDATE ELIGIBLE -- proceeding into Faizan's interview pipeline")

        banner("STAGE 5: generate_interview_plan() [Day 1]")
        stage = "generate_interview_plan"
        plan = generate_interview_plan(jd_profile, candidate)
        show("InterviewPlan", plan)

        banner("STAGE 6: generate_questions() [Day 2]")
        stage = "generate_questions"
        questions = generate_questions(jd_profile, candidate, plan)
        show("Generated Questions", questions)

        banner("STAGE 7: verify_cv_claims() [Day 3 - interview track]")
        stage = "verify_cv_claims"
        cv_claims = verify_cv_claims(candidate)
        show("CV Claims", cv_claims)

        banner("STAGE 8: simulate answers -> evaluate_answer() [Day 5, real Gemini calls] "
               "-> decide_next_step() [Day 4]")
        num_answers = min(len(questions), len(SIMULATED_ANSWERS))
        if num_answers < len(SIMULATED_ANSWERS):
            print(
                f"NOTE: only {len(questions)} question(s) were generated; "
                f"simulating {num_answers} answer(s) instead of "
                f"{len(SIMULATED_ANSWERS)}."
            )

        answer_evaluations = []
        current_difficulty = questions[0].baseline_difficulty if questions else "Mid-Level"
        previous_question_type = questions[0].question_type if questions else "Role-specific"

        for i in range(num_answers):
            question = questions[i]
            quality_label, answer_text = SIMULATED_ANSWERS[i]

            print(f"\n>>> Question {i + 1} ({question.question_type} / "
                  f"{question.expected_knowledge_area}):")
            print(question.question_text)
            print(f"\n>>> Simulated answer quality: {quality_label}")
            print(answer_text)

            stage = f"evaluate_answer (question {i + 1}, quality={quality_label})"
            evaluation = evaluate_answer(question, answer_text)
            show(f"AnswerEvaluation (question {i + 1}, quality={quality_label})", evaluation)
            answer_evaluations.append(evaluation)

            stage = f"decide_next_step (after question {i + 1})"
            decision = decide_next_step(
                current_difficulty=current_difficulty,
                previous_question_type=previous_question_type,
                answer_evaluation=asdict(evaluation),
            )
            show(f"DecisionOutcome (after question {i + 1})", decision)

            current_difficulty = decision.next_difficulty
            previous_question_type = decision.next_question_type

        banner("STAGE 9: build_cv_claim_evidence() [Day 6]")
        stage = "build_cv_claim_evidence"
        cv_claim_evidence = build_cv_claim_evidence(candidate, cv_claims)
        show("CVClaimEvidence", cv_claim_evidence)

        banner("STAGE 10: build_skill_matrix() [Day 6]")
        stage = "build_skill_matrix"
        skill_matrix = build_skill_matrix(answer_evaluations, jd_profile.required_skills)
        show("Skill Matrix", skill_matrix)

        banner("STAGE 11: analyze_cv_interview_gap() [Day 6]")
        stage = "analyze_cv_interview_gap"
        gap_analysis = analyze_cv_interview_gap(cv_claim_evidence.matched_claims, skill_matrix)
        show("Gap Analysis", gap_analysis)

        banner("STAGE 12: generate_final_assessment() [Day 7]")
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
        show("FinalAssessmentReport", final_report)

        banner("END-TO-END RUN COMPLETE")

    except Exception as exc:
        banner(f"PIPELINE FAILED AT STAGE: {stage}")
        print(f"Exception type: {type(exc).__name__}")
        print(f"Exception message: {exc}")
        print("\nFull traceback:\n")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
