import os
from typing import Optional

from pydantic import ValidationError

from app.integrations.llm.base import LLMProvider, LLMProviderError
from app.integrations.llm.gemini_provider import (
    DEFAULT_GEMINI_MODEL,
    GeminiProvider,
)
from app.schemas.candidate import CandidateProfile

DEFAULT_MODEL = DEFAULT_GEMINI_MODEL

CV_PARSER_SYSTEM_PROMPT = """You are an expert CV and resume data extraction engine.
Extract a candidate profile from raw CV text and return JSON that conforms exactly to the requested schema.

Follow these rules:

1. Extract only information stated or reasonably supported by the CV. Never invent employers, dates,
   projects, certifications, achievements, skills, or education.
2. Handle chronological, skills-first, project-heavy, and sparse CV formats without requiring a fixed layout.
3. For missing sections, return empty lists or an empty technology_specific_experience object.
4. Use the literal string "present" only as end_date for an ongoing work experience entry. Use null for
    start_date or end_date when that date is not stated. Never use "unknown" or invent a date.
5. Put named languages, frameworks, libraries, databases, tools, platforms, and APIs in technologies.
    Put non-tool competencies and capabilities, such as system design, communication, problem solving,
    authentication, or reporting, in skills. Do not duplicate named technologies in skills.
6. Populate technology_specific_experience as technology-to-years estimates only when the CV provides
    usable date ranges or explicit duration information for that technology. If no date or duration
    information exists anywhere in the CV to support an estimate, omit that technology entirely. Never
    assign a default or guessed duration.
7. Avoid double-counting overlapping periods for the same technology where the CV shows concurrent roles or projects.
8. Use nonnegative numeric year values and preserve the technology names used by the CV.
9. Keep projects, work experience, education, certifications, and achievements grounded in the source text.
"""


class CVParserError(Exception):
    """Raised when CV extraction or profile validation fails."""


class CVParser:
    """Parse raw CV text into a validated CandidateProfile."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[LLMProvider] = None,
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.provider = provider or GeminiProvider(
            api_key=self.api_key,
            model=self.model,
        )

    def parse(self, cv_text: str) -> CandidateProfile:
        """Parse CV text, retrying once only after schema validation failure."""
        if not cv_text or not cv_text.strip():
            raise ValueError("CV text cannot be empty.")

        prompt = (
            "Extract the candidate profile from the following CV text:\n\n"
            f"{cv_text.strip()}"
        )

        try:
            raw_text = self.provider.generate_structured(
                prompt=prompt,
                system_instruction=CV_PARSER_SYSTEM_PROMPT,
                response_schema=CandidateProfile,
                temperature=0.1,
            )
        except LLMProviderError as error:
            raise CVParserError(f"LLM error during initial extraction: {error}") from error

        try:
            return CandidateProfile.model_validate_json(raw_text)
        except ValidationError as validation_error:
            return self._retry_with_validation_feedback(
                prompt=prompt,
                initial_output=raw_text,
                validation_error=validation_error,
            )

    def _retry_with_validation_feedback(
        self,
        prompt: str,
        initial_output: str,
        validation_error: ValidationError,
    ) -> CandidateProfile:
        retry_prompt = (
            f"{prompt}\n\n"
            f"Your previous JSON output was:\n{initial_output}\n\n"
            f"It failed schema validation with error:\n{validation_error}\n\n"
            "Correct the validation issues and return valid JSON matching the schema exactly."
        )

        try:
            retry_text = self.provider.generate_structured(
                prompt=retry_prompt,
                system_instruction=CV_PARSER_SYSTEM_PROMPT,
                response_schema=CandidateProfile,
                temperature=0.1,
            )
        except LLMProviderError as error:
            raise CVParserError(f"LLM error during extraction retry: {error}") from error

        try:
            return CandidateProfile.model_validate_json(retry_text)
        except ValidationError as validation_error:
            raise CVParserError(
                f"Schema validation failed after retry: {validation_error}"
            ) from validation_error


def parse_cv(
    cv_text: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[LLMProvider] = None,
) -> CandidateProfile:
    """Convenience function for parsing raw CV text into CandidateProfile."""
    parser = CVParser(
        api_key=api_key,
        model=model,
        provider=provider,
    )
    return parser.parse(cv_text)
