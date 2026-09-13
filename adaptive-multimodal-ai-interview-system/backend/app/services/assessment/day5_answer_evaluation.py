import logging
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from app.services.interview_intelligence.models import ANSWER_PASS_THRESHOLD, AnswerEvaluation, Question
from app.integrations.llm.base import LLMProvider, LLMProviderError
from app.integrations.llm.gemini_provider import GeminiProvider

logger = logging.getLogger(__name__)

RUBRIC_WEIGHTS = {
    "technical_correctness": 0.40,
    "problem_solving": 0.25,
    "completeness": 0.15,
    "reasoning": 0.15,
    "communication": 0.05,
}


class AnswerRubricScores(BaseModel):
    technical_correctness: float = Field(ge=0, le=100)
    problem_solving: float = Field(ge=0, le=100)
    completeness: float = Field(ge=0, le=100)
    reasoning: float = Field(ge=0, le=100)
    communication: float = Field(ge=0, le=100)


SYSTEM_INSTRUCTION = """
You are evaluating a candidate's answer to an interview question.

Score the answer independently from 0 to 100 on:

- technical_correctness: factual and technical accuracy
- problem_solving: diagnosis, solution quality, and trade-offs
- completeness: coverage of the important parts of the question
- reasoning: clarity and quality of the underlying reasoning
- communication: clarity and structure

Return only the structured score object. Do not calculate or return a weighted total.

Rules:

1. Judge the answer against the question and expected knowledge area, not keyword presence alone.
2. Relevant technologies and keywords do not prove understanding.
3. If the answer says "I don't know," "I do not know," declines to answer,
   says the candidate has no knowledge or experience, gives only a vague refusal,
   or is otherwise a non-answer, technical_correctness and completeness must
   score very low, generally between 0 and 10. This applies even if the
   response is fluent, long, or contains relevant technology keywords.
4. A concise technically correct answer may score well; length alone is not evidence.
5. Do not infer unprovided experience or correctness.
6. Use the full 0-100 range when justified.
"""


def _weighted_total(scores: AnswerRubricScores) -> float:
    return round(
        scores.technical_correctness * RUBRIC_WEIGHTS["technical_correctness"]
        + scores.problem_solving * RUBRIC_WEIGHTS["problem_solving"]
        + scores.completeness * RUBRIC_WEIGHTS["completeness"]
        + scores.reasoning * RUBRIC_WEIGHTS["reasoning"]
        + scores.communication * RUBRIC_WEIGHTS["communication"],
        2,
    )


def _build_prompt(question: Question, candidate_answer: str) -> str:
    return (
        f"Question type: {question.question_type}\n"
        f"Expected knowledge area: {question.expected_knowledge_area}\n"
        f"Question: {question.question_text}\n"
        f"Candidate answer: {candidate_answer}\n"
    )


def _request_scores(
    provider: LLMProvider,
    question: Question,
    candidate_answer: str,
) -> AnswerRubricScores:
    prompt = _build_prompt(question, candidate_answer)
    validation_error: Optional[str] = None

    for attempt in range(2):
        retry_context = ""
        if validation_error:
            retry_context = (
                "\nYour previous response failed validation with this error:\n"
                f"{validation_error}\nReturn corrected JSON only.\n"
            )

        response_text = provider.generate_structured(
            prompt=prompt + retry_context,
            system_instruction=SYSTEM_INSTRUCTION,
            response_schema=AnswerRubricScores,
            temperature=0.0,
        )

        try:
            return AnswerRubricScores.model_validate_json(response_text)
        except (ValidationError, ValueError) as exc:
            validation_error = str(exc)
            logger.warning("Invalid answer rubric response on attempt %d", attempt + 1)

    raise LLMProviderError(
        f"Answer rubric response failed validation after 2 attempts: {validation_error}"
    )


def evaluate_answer(
    question: Question,
    candidate_answer: str,
    provider: Optional[LLMProvider] = None,
) -> AnswerEvaluation:
    """Evaluate an answer using schema-constrained LLM rubric scores."""
    logger.info("Evaluating answer for %s", question.expected_knowledge_area)
    scores = _request_scores(
        provider=provider or GeminiProvider(),
        question=question,
        candidate_answer=candidate_answer.strip(),
    )
    weighted_total = _weighted_total(scores)
    pass_fail = weighted_total >= ANSWER_PASS_THRESHOLD

    criterion_scores = {
        "Technical Correctness": scores.technical_correctness,
        "Problem Solving": scores.problem_solving,
        "Completeness": scores.completeness,
        "Reasoning": scores.reasoning,
        "Communication": scores.communication,
    }

    evaluation = AnswerEvaluation(
        question_text=question.question_text,
        expected_knowledge_area=question.expected_knowledge_area,
        question_type=question.question_type,
        weighted_total=weighted_total,
        technical_correctness=scores.technical_correctness,
        problem_solving=scores.problem_solving,
        completeness=scores.completeness,
        reasoning=scores.reasoning,
        communication=scores.communication,
        pass_fail=pass_fail,
        criterion_scores=criterion_scores,
        skills_covered=question.skills_covered,
        recommendation_note=(
            "Candidate response demonstrates a solid understanding of the topic."
            if pass_fail
            else "Candidate answer has gaps requiring follow-up and additional evidence."
        ),
    )
    logger.info("Scored answer: total %.2f pass=%s", evaluation.weighted_total, evaluation.pass_fail)
    return evaluation
