"""
app/services/jd_intelligence/jd_parser.py

Service responsible for parsing unstructured Job Description (JD) text
into a validated, structured JobRequirementProfile using Google Gemini API
(google-genai SDK) with structured JSON output and single-retry error recovery.
"""

import logging
import os
import re
from typing import Optional
from google import genai
from pydantic import ValidationError

from app.integrations.llm.factory import get_default_provider
from app.integrations.llm.gemini_provider import (
    DEFAULT_GEMINI_MODEL,
    GeminiProvider,
)
from app.integrations.llm.base import LLMProvider, LLMProviderError
from app.schemas.job import JobRequirementProfile

logger = logging.getLogger(__name__)

DEFAULT_MODEL = DEFAULT_GEMINI_MODEL

JD_PARSER_SYSTEM_PROMPT = """You are an expert technical recruiter and data extraction engine.
Your task is to analyze a raw Job Description (JD) and extract all qualification criteria into a strictly structured JSON format conforming to the requested schema.

Follow these critical disambiguation and classification rules:

0. REQUIREMENTS VS. RESPONSIBILITIES (CRITICAL -- classify by MEANING, not by section heading):
   - A REQUIREMENT describes something the candidate must already possess or be able to do BEFORE
     being hired -- a skill, technology, experience level, credential, or trait that qualifies them
     for the role (e.g., "Python", "3 years of backend experience", "Bachelor's degree").
   - A RESPONSIBILITY describes an action the person WILL PERFORM once hired -- a duty, task, or
     activity that is part of the job itself, not a qualification (e.g., "Build and maintain APIs",
     "Collaborate with the design team", "Participate in code reviews").
   - Classify based on the MEANING of each statement, not which section heading it physically
     appears under. JD authors are inconsistent: a duty-phrased line ("Collaborate with senior
     engineers on production ML practices") can appear under a "Requirements" heading, and a
     genuine qualification can appear under "Responsibilities." Extract only genuine
     requirement-shaped statements into required_skills/required_technologies/etc. regardless of
     heading, and do NOT extract responsibility-shaped statements even if they sit under a
     Requirements/Qualifications heading.
   - Test: could this statement be true of the candidate on day one, before doing any work in the
     role? If yes, it's a requirement. If it only makes sense as something they will DO once
     employed, it's a responsibility -- exclude it from required_skills/preferred_skills entirely.

1. EXPERIENCE REQUIREMENTS (CRITICAL):
   - You must differentiate between GENERAL experience and SPECIFIC experience.
   - GENERAL: Overall professional or software engineering tenure without restriction to a specific technology (e.g., "Minimum 3 years of professional software development experience"). Set requirement_type="general", target=null, years=<float>.
   - SPECIFIC: Experience tied to a named programming language, framework, database, tool, or domain (e.g., "2 years hands-on Python development experience", "1 year FastAPI experience"). Set requirement_type="specific", target=<named technology/tool/domain>, years=<float>.
   - Maintain a separate entry in `experience_requirements` for EVERY distinct experience requirement in the JD. If a JD requires "3 years overall + 2 years Python + 1 year FastAPI", create 3 separate ExperienceRequirement entries.
   - Always set `is_mandatory` (True if required/minimum, False if preferred/bonus).

2. MANDATORY VS. PREFERRED REQUIREMENTS:
   - This rule only decides WHICH BUCKET a genuine requirement goes in (mandatory vs. preferred) -- it
     does not override rule 0. A duty-phrased statement is excluded entirely regardless of which
     heading or wording marks it "required."
   - Mandatory: Requirements marked "required", "minimum", "must have", or listed under standard Requirements/Qualifications sections.
     * Place in `required_skills`, `required_technologies`, or mark `is_mandatory=True` for education/certifications.
   - Preferred: Requirements marked "preferred", "nice to have", "plus", "bonus", or "desired".
     * Place in `preferred_skills`, `preferred_technologies`, or mark `is_mandatory=False` for education/certifications.

3. EDUCATION & CERTIFICATIONS:
   - Extract degree level (e.g., "Bachelor's", "Master's", "PhD") and field of study if specified.
   - Extract any professional certifications (e.g., "AWS Certified Solutions Architect", "CKA").

4. DOMAIN EXPERIENCE:
   - Extract industry/business domains if specified (e.g., "Fintech", "Healthcare", "E-commerce", "AdTech").

5. OTHER MANDATORY REQUIREMENTS:
   - Capture non-technical constraints (e.g., "Must be eligible to work in the US", "Willingness to work on-call rotations").

Do not invent or assume requirements not mentioned in the text. Return only valid JSON conforming strictly to the requested schema.
"""

# Second-layer safety net, independent of prompt quality: removes any
# required_skills/preferred_skills entry whose phrasing starts with an
# action/duty verb (a responsibility statement, e.g. "Collaborate with
# senior engineers...") rather than a qualification statement (e.g.
# "Python"). Evidence-based, not exhaustive -- covers exactly what's been
# observed in a real false positive plus the verbs named when this fix was
# designed. Grow this list only when a real case shows up, same discipline
# as _SKILL_EQUIVALENCE_GROUPS/_DEGREE_EQUIVALENCE_GROUPS in
# eligibility_engine.py. Not applied to required_technologies/education/
# certifications -- those are named tools/credentials, not free-text
# sentences, and haven't shown this failure mode.
_DUTY_VERB_PATTERN = re.compile(
    r"^(collaborate|contribute|assist|participate|build|integrate|write|develop|design|maintain|support|manage|lead)\b",
    re.IGNORECASE,
)


def _filter_duty_shaped_requirements(profile: JobRequirementProfile) -> JobRequirementProfile:
    """
    Mutates and returns `profile`: strips any required_skills/preferred_skills
    entry that reads as a job duty (starts with an action verb) rather than a
    candidate qualification. See _DUTY_VERB_PATTERN's docstring above for why
    this exists alongside, not instead of, the prompt's own rule 0.
    """
    for field_name in ("required_skills", "preferred_skills"):
        original = getattr(profile, field_name)
        kept = [item for item in original if not _DUTY_VERB_PATTERN.match(item.strip())]
        for item in original:
            if item not in kept:
                logger.warning("Filtered duty-shaped requirement out of %s: %r", field_name, item)
        setattr(profile, field_name, kept)
    return profile


class JDParserError(Exception):
    """Raised when JD parsing or validation fails."""
    pass


class JDParser:
    """
    Parses unstructured Job Description text into a structured JobRequirementProfile
    using Gemini API structured outputs with a retry-on-validation-failure mechanism.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[genai.Client] = None,
        provider: Optional[LLMProvider] = None,
    ):
        """
        Initialize the JDParser.

        Args:
            api_key: Gemini API key. If omitted, read from GEMINI_API_KEY env var.
            model: Model identifier. Defaults to GEMINI_MODEL env var or 'gemini-3.6-flash'.
            client: Optional pre-configured genai.Client instance (useful for unit testing and dependency injection).
            provider: Optional pre-built LLMProvider, taking full precedence over api_key/model/client.
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

        # api_key/model/client customize a specific GeminiProvider (also how
        # tests inject a mock client), so any of them being explicitly set
        # takes precedence over the Gemini-plus-xAI-fallback default -- that
        # default only applies to a genuinely zero-config call, e.g. the
        # parse_job_description() convenience function called with no
        # optional args at all.
        if provider is not None:
            self.provider = provider
        elif api_key is not None or model is not None or client is not None:
            self.provider = GeminiProvider(api_key=self.api_key, model=self.model, client=client)
        else:
            self.provider = get_default_provider()

    def parse(self, jd_text: str) -> JobRequirementProfile:
        """
        Parses raw Job Description text into a validated JobRequirementProfile.
        If initial schema validation fails, retries once with the validation error
        fed back to the model before raising JDParserError.

        Args:
            jd_text: Raw job description text.

        Returns:
            Validated JobRequirementProfile instance.

        Raises:
            ValueError: If jd_text is empty or blank.
            JDParserError: If API communication fails or schema validation fails after retry.
        """
        if not jd_text or not jd_text.strip():
            raise ValueError("Job description text cannot be empty.")

        prompt = (
            "Extract all structured requirements from the following Job Description:\n\n"
            f"{jd_text.strip()}"
        )

        # First attempt
        try:
            raw_text = self.provider.generate_structured(
                prompt=prompt,
                system_instruction=JD_PARSER_SYSTEM_PROMPT,
                response_schema=JobRequirementProfile,
                temperature=0.1,
            )
        except LLMProviderError as err:
            raise JDParserError(f"LLM error during initial extraction: {err}") from err

        # Attempt validation on initial output
        try:
            return _filter_duty_shaped_requirements(JobRequirementProfile.model_validate_json(raw_text))
        except ValidationError as first_val_err:
            # Schema validation failed on first attempt: execute retry once
            return self._retry_with_validation_feedback(
                provider=self.provider,
                prompt=prompt,
                initial_output=raw_text,
                validation_error=first_val_err,
            )

    def _retry_with_validation_feedback(
        self,
        provider: GeminiProvider,
        prompt: str,
        initial_output: str,
        validation_error: ValidationError,
    ) -> JobRequirementProfile:
        """
        Retries extraction once by feeding back the schema validation error
        to the model.
        """
        retry_prompt = (
            f"{prompt}\n\n"
            f"Your previous JSON output was:\n{initial_output}\n\n"
            f"It failed schema validation with error:\n{validation_error}\n\n"
            "Please fix the issues identified above, ensure all field types and requirements match "
            "the schema exactly, and return valid JSON."
        )

        try:
            retry_text = provider.generate_structured(
                prompt=retry_prompt,
                system_instruction=JD_PARSER_SYSTEM_PROMPT,
                response_schema=JobRequirementProfile,
                temperature=0.1,
            )
        except LLMProviderError as err:
            raise JDParserError(f"LLM error during extraction retry: {err}") from err

        try:
            return _filter_duty_shaped_requirements(JobRequirementProfile.model_validate_json(retry_text))
        except ValidationError as retry_val_err:
            raise JDParserError(
                f"Schema validation failed after retry: {retry_val_err}"
            ) from retry_val_err


def parse_job_description(
    jd_text: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    client: Optional[genai.Client] = None,
    provider: Optional[LLMProvider] = None,
) -> JobRequirementProfile:
    """
    Convenience function to parse a raw Job Description into JobRequirementProfile.

    Args:
        jd_text: Raw job description text.
        api_key: Optional Gemini API key.
        model: Optional model override. Defaults to 'gemini-3.6-flash'.
        client: Optional Gemini Client instance.
        provider: Optional pre-built LLMProvider, taking full precedence over api_key/model/client.

    Returns:
        Validated JobRequirementProfile.
    """
    parser = JDParser(api_key=api_key, model=model, client=client, provider=provider)
    return parser.parse(jd_text)
