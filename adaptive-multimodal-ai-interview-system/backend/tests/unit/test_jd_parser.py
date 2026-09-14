"""
tests/unit/test_jd_parser.py

Unit tests for JDParser service using a mocked Google Gemini client.
Validates extraction accuracy, specific vs. general experience separation,
empty input validation, and single-retry error recovery on schema validation failure.
"""

import json
from unittest.mock import MagicMock
import pytest
from google.genai.errors import APIError

from app.schemas.job import (
    CertificationRequirement,
    EducationRequirement,
    ExperienceRequirement,
    ExperienceRequirementType,
    JobRequirementProfile,
)
from app.services.jd_intelligence.jd_parser import (
    JDParser,
    JDParserError,
    _filter_duty_shaped_requirements,
    parse_job_description,
)


def _make_mock_response(payload: dict | str):
    """Fabricates a Gemini GenerateContentResponse mock object."""
    response = MagicMock()
    if isinstance(payload, dict):
        response.text = json.dumps(payload)
    else:
        response.text = str(payload)
    return response


# ---------------------------------------------------------------------------
# Test 1: Literal Proposal Example JD (Section 4 of proposal)
# ---------------------------------------------------------------------------
def test_parse_exact_proposal_example_jd():
    """
    Verifies parsing against the exact proposal example JD:
    - 3 years overall software development experience (general)
    - 2 years Python development experience (specific)
    - FastAPI (required)
    - PostgreSQL (required)
    - Docker (preferred)
    No education, certifications, or extra technologies.
    """
    raw_jd = (
        "Job Title: Senior Python Developer\n"
        "Requirements:\n"
        "- 3 years of overall software development experience\n"
        "- 2 years of Python experience\n"
        "- FastAPI\n"
        "- PostgreSQL\n"
        "Preferred:\n"
        "- Docker\n"
    )

    expected_payload = {
        "job_title": "Senior Python Developer",
        "experience_requirements": [
            {
                "description": "3 years of overall software development experience",
                "years": 3.0,
                "requirement_type": "general",
                "target": None,
                "is_mandatory": True,
            },
            {
                "description": "2 years of Python experience",
                "years": 2.0,
                "requirement_type": "specific",
                "target": "Python",
                "is_mandatory": True,
            },
        ],
        "required_skills": [],
        "preferred_skills": [],
        "required_technologies": ["FastAPI", "PostgreSQL"],
        "preferred_technologies": ["Docker"],
        "education_requirements": [],
        "certifications": [],
        "domain_experience": [],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(expected_payload)

    parser = JDParser(client=mock_client)
    profile = parser.parse(raw_jd)

    # Field-by-field verification
    assert profile.job_title == "Senior Python Developer"
    assert len(profile.experience_requirements) == 2

    # General requirement
    gen_req = profile.experience_requirements[0]
    assert gen_req.years == 3.0
    assert gen_req.requirement_type == ExperienceRequirementType.GENERAL
    assert gen_req.target is None
    assert gen_req.is_mandatory is True

    # Specific requirement
    spec_req = profile.experience_requirements[1]
    assert spec_req.years == 2.0
    assert spec_req.requirement_type == ExperienceRequirementType.SPECIFIC
    assert spec_req.target == "Python"
    assert spec_req.is_mandatory is True

    # Technologies
    assert profile.required_technologies == ["FastAPI", "PostgreSQL"]
    assert profile.preferred_technologies == ["Docker"]

    # Empty optional lists
    assert profile.education_requirements == []
    assert profile.certifications == []
    assert profile.domain_experience == []
    assert profile.other_mandatory_requirements == []


# ---------------------------------------------------------------------------
# Test 2: Realistic Extended JD (includes education, certs, domain)
# ---------------------------------------------------------------------------
def test_parse_realistic_extended_jd():
    """
    Verifies parsing a richer JD containing education, certifications, and domain experience.
    """
    raw_jd = (
        "Job Title: Senior Backend Engineer\n"
        "Experience: 4 years overall, 2 years Python\n"
        "Required: Python, FastAPI, PostgreSQL\n"
        "Preferred: Docker, Redis\n"
        "Education: Bachelor's in Computer Science (Mandatory)\n"
        "Certification: AWS Certified Solutions Architect (Preferred)\n"
        "Domain: Fintech\n"
    )

    expected_payload = {
        "job_title": "Senior Backend Engineer",
        "experience_requirements": [
            {
                "description": "4 years overall",
                "years": 4.0,
                "requirement_type": "general",
                "target": None,
                "is_mandatory": True,
            },
            {
                "description": "2 years Python",
                "years": 2.0,
                "requirement_type": "specific",
                "target": "Python",
                "is_mandatory": True,
            },
        ],
        "required_skills": [],
        "preferred_skills": [],
        "required_technologies": ["Python", "FastAPI", "PostgreSQL"],
        "preferred_technologies": ["Docker", "Redis"],
        "education_requirements": [
            {
                "degree_level": "Bachelor's",
                "field_of_study": "Computer Science",
                "is_mandatory": True,
            }
        ],
        "certifications": [
            {
                "name": "AWS Certified Solutions Architect",
                "is_mandatory": False,
            }
        ],
        "domain_experience": ["Fintech"],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(expected_payload)

    parser = JDParser(client=mock_client)
    profile = parser.parse(raw_jd)

    assert profile.job_title == "Senior Backend Engineer"
    assert len(profile.education_requirements) == 1
    assert profile.education_requirements[0].degree_level == "Bachelor's"
    assert profile.education_requirements[0].field_of_study == "Computer Science"
    assert profile.education_requirements[0].is_mandatory is True

    assert len(profile.certifications) == 1
    assert profile.certifications[0].name == "AWS Certified Solutions Architect"
    assert profile.certifications[0].is_mandatory is False

    assert profile.domain_experience == ["Fintech"]


# ---------------------------------------------------------------------------
# Test 3: JD with Only General Experience (no specific technology tied)
# ---------------------------------------------------------------------------
def test_parse_jd_only_general_experience():
    """
    Verifies handling of a JD that only specifies general overall experience.
    """
    raw_jd = (
        "Job Title: Software Engineer\n"
        "Requirements: Minimum 4 years of professional software development experience.\n"
    )

    expected_payload = {
        "job_title": "Software Engineer",
        "experience_requirements": [
            {
                "description": "Minimum 4 years of professional software development experience",
                "years": 4.0,
                "requirement_type": "general",
                "target": None,
                "is_mandatory": True,
            }
        ],
        "required_skills": [],
        "preferred_skills": [],
        "required_technologies": [],
        "preferred_technologies": [],
        "education_requirements": [],
        "certifications": [],
        "domain_experience": [],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(expected_payload)

    parser = JDParser(client=mock_client)
    profile = parser.parse(raw_jd)

    assert len(profile.experience_requirements) == 1
    req = profile.experience_requirements[0]
    assert req.years == 4.0
    assert req.requirement_type == ExperienceRequirementType.GENERAL
    assert req.target is None

    # Verify no specific requirements exist
    assert not any(r.requirement_type == ExperienceRequirementType.SPECIFIC for r in profile.experience_requirements)


# ---------------------------------------------------------------------------
# Test 4: Multiple Specific Experience Requirements (Proposal Example 3)
# ---------------------------------------------------------------------------
def test_parse_jd_multiple_specific_experience_requirements():
    """
    Verifies multiple specific experience requirements (e.g. overall + Python + FastAPI)
    are captured as distinct, independent entries in experience_requirements.
    """
    raw_jd = (
        "Job Title: Backend API Architect\n"
        "Requirements:\n"
        "- 3 years of overall software development experience\n"
        "- 2 years of Python experience\n"
        "- 1 year of FastAPI experience\n"
    )

    expected_payload = {
        "job_title": "Backend API Architect",
        "experience_requirements": [
            {
                "description": "3 years of overall software development experience",
                "years": 3.0,
                "requirement_type": "general",
                "target": None,
                "is_mandatory": True,
            },
            {
                "description": "2 years of Python experience",
                "years": 2.0,
                "requirement_type": "specific",
                "target": "Python",
                "is_mandatory": True,
            },
            {
                "description": "1 year of FastAPI experience",
                "years": 1.0,
                "requirement_type": "specific",
                "target": "FastAPI",
                "is_mandatory": True,
            },
        ],
        "required_skills": [],
        "preferred_skills": [],
        "required_technologies": ["Python", "FastAPI"],
        "preferred_technologies": [],
        "education_requirements": [],
        "certifications": [],
        "domain_experience": [],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(expected_payload)

    parser = JDParser(client=mock_client)
    profile = parser.parse(raw_jd)

    assert len(profile.experience_requirements) == 3

    general_reqs = [r for r in profile.experience_requirements if r.requirement_type == ExperienceRequirementType.GENERAL]
    specific_reqs = [r for r in profile.experience_requirements if r.requirement_type == ExperienceRequirementType.SPECIFIC]

    assert len(general_reqs) == 1
    assert general_reqs[0].years == 3.0

    assert len(specific_reqs) == 2
    targets = {r.target: r.years for r in specific_reqs}
    assert targets == {"Python": 2.0, "FastAPI": 1.0}


# ---------------------------------------------------------------------------
# Test 5: Empty / Blank JD Raises ValueError
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("empty_input", ["", "   ", "\n\t  \n"])
def test_parse_empty_or_whitespace_jd_raises_value_error(empty_input):
    """
    Verifies that empty or whitespace-only JD inputs raise ValueError immediately
    without calling the LLM client.
    """
    mock_client = MagicMock()
    parser = JDParser(client=mock_client)

    with pytest.raises(ValueError, match="Job description text cannot be empty."):
        parser.parse(empty_input)

    mock_client.models.generate_content.assert_not_called()


# ---------------------------------------------------------------------------
# Test 6: Retry on Schema Validation Failure Succeeds on Second Attempt
# ---------------------------------------------------------------------------
def test_retry_on_schema_validation_failure_succeeds():
    """
    Simulates schema validation failure on first Gemini API response (e.g. invalid requirement_type).
    Confirms that:
    1. The error is caught.
    2. A retry call is sent with validation error feedback.
    3. The valid second response is parsed and returned.
    """
    raw_jd = "Job Title: Software Engineer\nRequirements: 3 years experience"

    # Invalid payload for attempt 1 (invalid enum value for requirement_type)
    invalid_payload = {
        "job_title": "Software Engineer",
        "experience_requirements": [
            {
                "description": "3 years experience",
                "years": 3.0,
                "requirement_type": "invalid_enum_choice",  # triggers ValidationError
                "target": None,
                "is_mandatory": True,
            }
        ],
    }

    # Corrected payload for attempt 2
    valid_payload = {
        "job_title": "Software Engineer",
        "experience_requirements": [
            {
                "description": "3 years experience",
                "years": 3.0,
                "requirement_type": "general",
                "target": None,
                "is_mandatory": True,
            }
        ],
        "required_skills": [],
        "preferred_skills": [],
        "required_technologies": [],
        "preferred_technologies": [],
        "education_requirements": [],
        "certifications": [],
        "domain_experience": [],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    first_response = _make_mock_response(invalid_payload)
    second_response = _make_mock_response(valid_payload)
    mock_client.models.generate_content.side_effect = [first_response, second_response]

    parser = JDParser(client=mock_client)
    profile = parser.parse(raw_jd)

    # Verify 2 calls were made (initial attempt + 1 retry)
    assert mock_client.models.generate_content.call_count == 2

    # Verify retry call contains the error feedback
    retry_call_args = mock_client.models.generate_content.call_args_list[1]
    retry_prompt = retry_call_args.kwargs.get("contents") or retry_call_args.args[1]
    assert "It failed schema validation with error:" in retry_prompt

    # Profile successfully validated
    assert profile.job_title == "Software Engineer"
    assert profile.experience_requirements[0].requirement_type == ExperienceRequirementType.GENERAL


# ---------------------------------------------------------------------------
# Test 7: Retry Fails After Second Attempt Raises JDParserError
# ---------------------------------------------------------------------------
def test_retry_failure_raises_jd_parser_error():
    """
    Confirms that if Gemini returns invalid schema data on BOTH attempts,
    JDParserError is raised with chained exception context.
    """
    raw_jd = "Job Title: Software Engineer\nRequirements: 3 years experience"

    invalid_payload = {
        "job_title": "Software Engineer",
        "experience_requirements": [
            {
                "description": "3 years experience",
                "years": 3.0,
                "requirement_type": "bad_type",
                "target": None,
                "is_mandatory": True,
            }
        ],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _make_mock_response(invalid_payload),
        _make_mock_response(invalid_payload),
    ]

    parser = JDParser(client=mock_client)

    with pytest.raises(JDParserError, match="Schema validation failed after retry"):
        parser.parse(raw_jd)

    assert mock_client.models.generate_content.call_count == 2


# ---------------------------------------------------------------------------
# Test 8: Empty Response from Gemini Raises JDParserError
# ---------------------------------------------------------------------------
def test_empty_response_raises_jd_parser_error():
    """
    Confirms that if the Gemini model returns an empty or whitespace response,
    JDParserError is raised.
    """
    raw_jd = "Some JD text"

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response("")

    parser = JDParser(client=mock_client)

    with pytest.raises(JDParserError, match="Gemini model returned an empty response"):
        parser.parse(raw_jd)


# ---------------------------------------------------------------------------
# Test 9: Convenience Function parse_job_description Works
# ---------------------------------------------------------------------------
def test_parse_job_description_convenience_function():
    """
    Verifies that the module-level parse_job_description convenience function works.
    """
    raw_jd = "Job Title: Backend Developer"
    valid_payload = {
        "job_title": "Backend Developer",
        "experience_requirements": [],
        "required_skills": [],
        "preferred_skills": [],
        "required_technologies": [],
        "preferred_technologies": [],
        "education_requirements": [],
        "certifications": [],
        "domain_experience": [],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(valid_payload)

    profile = parse_job_description(raw_jd, client=mock_client)
    assert profile.job_title == "Backend Developer"


# ---------------------------------------------------------------------------
# Test 10: Specific vs General Experience Independence
# ---------------------------------------------------------------------------
def test_specific_vs_general_experience_independence():
    """
    Verifies that specific experience requirements do NOT mutate or overwrite
    the general experience requirement, preserving distinct years and criteria.
    """
    raw_jd = "Job Title: ML Engineer\nExperience: 5 years software dev, 2 years PyTorch"

    payload = {
        "job_title": "ML Engineer",
        "experience_requirements": [
            {
                "description": "5 years software dev",
                "years": 5.0,
                "requirement_type": "general",
                "target": None,
                "is_mandatory": True,
            },
            {
                "description": "2 years PyTorch",
                "years": 2.0,
                "requirement_type": "specific",
                "target": "PyTorch",
                "is_mandatory": True,
            },
        ],
        "required_skills": [],
        "preferred_skills": [],
        "required_technologies": ["PyTorch"],
        "preferred_technologies": [],
        "education_requirements": [],
        "certifications": [],
        "domain_experience": [],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(payload)

    parser = JDParser(client=mock_client)
    profile = parser.parse(raw_jd)

    general = [r for r in profile.experience_requirements if r.requirement_type == ExperienceRequirementType.GENERAL][0]
    specific = [r for r in profile.experience_requirements if r.requirement_type == ExperienceRequirementType.SPECIFIC][0]

    assert general.years == 5.0
    assert specific.years == 2.0
    assert general.years != specific.years
    assert general.target is None
    assert specific.target == "PyTorch"


# ---------------------------------------------------------------------------
# Test 11: Mandatory vs Preferred Classification Integrity
# ---------------------------------------------------------------------------
def test_mandatory_vs_preferred_classification_integrity():
    """
    Verifies that required vs preferred technologies and requirements
    are strictly separated into their designated lists.
    """
    raw_jd = "Job Title: Full Stack Developer\nRequired: React, Node.js\nPreferred: TypeScript, GraphQL"

    payload = {
        "job_title": "Full Stack Developer",
        "experience_requirements": [],
        "required_skills": [],
        "preferred_skills": [],
        "required_technologies": ["React", "Node.js"],
        "preferred_technologies": ["TypeScript", "GraphQL"],
        "education_requirements": [],
        "certifications": [],
        "domain_experience": [],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(payload)

    parser = JDParser(client=mock_client)
    profile = parser.parse(raw_jd)

    # Intersection of required and preferred must be empty
    required_set = set(profile.required_technologies)
    preferred_set = set(profile.preferred_technologies)
    assert required_set.isdisjoint(preferred_set)
    assert required_set == {"React", "Node.js"}
    assert preferred_set == {"TypeScript", "GraphQL"}


# ---------------------------------------------------------------------------
# Test: _filter_duty_shaped_requirements Strips Duty-Phrased Entries Directly
# ---------------------------------------------------------------------------
def test_filter_duty_shaped_requirements_strips_action_verb_entries():
    """
    Direct unit test of the safety-net filter, independent of any LLM call:
    a duty-shaped entry (starts with an action verb -- a responsibility
    statement, not a qualification) must be removed from required_skills/
    preferred_skills, while genuine qualification-shaped entries survive.
    """
    profile = JobRequirementProfile(
        job_title="AI Engineer",
        required_skills=[
            "Python",
            "Machine Learning",
            "Build, train, and evaluate machine learning models",
            "Collaborate with senior engineers on production ML practices",
            "Integrate LLM-based features into existing backend services",
            "Write clean, well-tested Python code",
        ],
        preferred_skills=["Git", "Participate in code reviews"],
    )

    result = _filter_duty_shaped_requirements(profile)

    assert result.required_skills == ["Python", "Machine Learning"]
    assert result.preferred_skills == ["Git"]


# ---------------------------------------------------------------------------
# Test: The Filter Is Actually Wired Into parse() -- Not Just Correct in Isolation
# ---------------------------------------------------------------------------
def test_parse_filters_duty_shaped_requirements_from_llm_response():
    """
    Confirms the filter is actually applied inside JDParser.parse(), using a
    mocked LLM response shaped exactly like the real false positive found
    against Jazib's application: duty-phrased lines the model classified as
    required_skills anyway.
    """
    payload = {
        "job_title": "AI Engineer",
        "experience_requirements": [],
        "required_skills": [
            "Machine Learning",
            "Deep Learning",
            "Build, train, and evaluate machine learning models",
            "Collaborate with senior engineers on production ML practices",
        ],
        "preferred_skills": [],
        "required_technologies": ["Python"],
        "preferred_technologies": [],
        "education_requirements": [],
        "certifications": [],
        "domain_experience": [],
        "other_mandatory_requirements": [],
    }

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _make_mock_response(payload)

    parser = JDParser(client=mock_client)
    profile = parser.parse("Job Title: AI Engineer\nRequirements:\n- Machine Learning\n- Deep Learning\n")

    assert profile.required_skills == ["Machine Learning", "Deep Learning"]
