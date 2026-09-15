import json
from unittest.mock import MagicMock

import pytest

from app.integrations.llm.base import LLMProvider, LLMProviderError
from app.schemas.candidate import CandidateProfile
from app.services.cv_intelligence.cv_parser import (
    CVParser,
    CVParserError,
    parse_cv,
)


SAMPLE_CV_TEXT = """Jane Doe
Backend Engineer

Skills: Python, FastAPI, PostgreSQL
Experience:
Backend Engineer at Acme, 2022 - present
Built APIs with Python and FastAPI.
"""


def _mock_provider(*responses) -> MagicMock:
    provider = MagicMock(spec=LLMProvider)
    provider.generate_structured.side_effect = [
        json.dumps(response) if isinstance(response, dict) else response
        for response in responses
    ]
    return provider


def _chronological_profile() -> dict:
    return {
        "skills": ["Python", "API design"],
        "technologies": ["Python", "FastAPI", "PostgreSQL"],
        "projects": [],
        "work_experience": [
            {
                "position": "Backend Engineer",
                "company": "Acme",
                "start_date": "2022-01",
                "end_date": "present",
                "description": "Built Python APIs.",
            }
        ],
        "education": ["BSc Computer Science"],
        "certifications": [],
        "achievements": [],
        "technology_specific_experience": [
            {"technology": "Python", "years": 2.0},
            {"technology": "FastAPI", "years": 1.5},
        ],
    }


def test_cv_parser_basic():
    provider = _mock_provider(_chronological_profile())

    profile = parse_cv(SAMPLE_CV_TEXT, provider=provider)

    assert "Python" in profile.skills
    assert len(profile.work_experience) > 0
    assert profile.technology_experience_map.get("Python", 0) > 0


def test_parse_standard_chronological_cv():
    provider = _mock_provider(_chronological_profile())

    profile = CVParser(provider=provider).parse(SAMPLE_CV_TEXT)

    assert profile.work_experience[0].position == "Backend Engineer"
    assert profile.work_experience[0].end_date == "present"
    assert profile.education == ["BSc Computer Science"]


def test_parse_skills_first_cv():
    payload = {
        "skills": ["Python", "Docker", "SQL"],
        "technologies": ["Python", "Docker"],
        "projects": [],
        "work_experience": [
            {
                "position": "Software Developer",
                "company": None,
                "start_date": "2023",
                "end_date": "2024",
                "description": "Maintained backend services.",
            }
        ],
        "education": [],
        "certifications": [],
        "achievements": [],
        "technology_specific_experience": [],
    }
    provider = _mock_provider(payload)

    profile = parse_cv("Skills: Python, Docker, SQL\nWork: Software Developer", provider=provider)

    assert profile.skills == ["Python", "Docker", "SQL"]
    assert len(profile.work_experience) == 1


def test_parse_project_heavy_cv():
    payload = {
        "skills": ["JavaScript"],
        "technologies": ["React", "Node.js"],
        "projects": [
            {
                "name": "Student Marketplace",
                "description": "Built a marketplace web application.",
                "technologies": ["React", "Node.js"],
            },
            {
                "name": "Portfolio Site",
                "description": "Created a personal portfolio.",
                "technologies": ["JavaScript"],
            },
        ],
        "work_experience": [],
        "education": ["BSc Software Engineering"],
        "certifications": [],
        "achievements": ["Won a university hackathon"],
        "technology_specific_experience": [
            {"technology": "React", "years": 1.0},
        ],
    }
    provider = _mock_provider(payload)

    profile = parse_cv("Projects: Student Marketplace; Portfolio Site", provider=provider)

    assert len(profile.projects) == 2
    assert profile.projects[0].technologies == ["React", "Node.js"]
    assert profile.work_experience == []


def test_parse_sparse_cv_does_not_hallucinate():
    payload = {
        "skills": ["Python"],
        "technologies": [],
        "projects": [],
        "work_experience": [],
        "education": [],
        "certifications": [],
        "achievements": [],
        "technology_specific_experience": [],
    }
    provider = _mock_provider(payload)

    profile = parse_cv("Alex Smith\nPython", provider=provider)

    assert profile.skills == ["Python"]
    assert profile.technologies == []
    assert profile.work_experience == []
    assert profile.education == []
    assert profile.certifications == []
    assert profile.technology_specific_experience == []


def test_missing_work_experience_dates_use_none():
    payload = {
        "skills": ["Python"],
        "technologies": ["Python"],
        "projects": [],
        "work_experience": [
            {
                "position": "Software Developer",
                "company": "Small Startup",
                "start_date": None,
                "end_date": None,
                "description": "Worked on backend scripts.",
            }
        ],
        "education": [],
        "certifications": [],
        "achievements": [],
        "technology_specific_experience": [],
    }
    provider = _mock_provider(payload)

    profile = parse_cv("Software developer at a small startup.", provider=provider)

    assert profile.work_experience[0].start_date is None
    assert profile.work_experience[0].end_date is None


def test_technology_experience_can_be_inferred_from_cv_dates():
    payload = _chronological_profile()
    payload["technology_specific_experience"] = [
        {"technology": "Python", "years": 2.0},
    ]
    provider = _mock_provider(payload)

    profile = parse_cv(
        "Backend Engineer, 2022-present. Used Python throughout the role.",
        provider=provider,
    )

    assert profile.technology_experience_map["Python"] == 2.0


def test_retry_on_validation_failure_succeeds():
    invalid_payload = {"skills": "Python"}
    valid_payload = _chronological_profile()
    provider = _mock_provider(invalid_payload, valid_payload)

    profile = parse_cv(SAMPLE_CV_TEXT, provider=provider)

    assert profile.skills == ["Python", "API design"]
    assert provider.generate_structured.call_count == 2
    retry_prompt = provider.generate_structured.call_args_list[1].kwargs["prompt"]
    assert "failed schema validation with error:" in retry_prompt
    assert "Your previous JSON output was:" in retry_prompt


def test_retry_failure_raises_cv_parser_error():
    provider = _mock_provider({"skills": "Python"}, {"skills": "Python"})

    with pytest.raises(CVParserError, match="Schema validation failed after retry"):
        parse_cv(SAMPLE_CV_TEXT, provider=provider)

    assert provider.generate_structured.call_count == 2


def test_provider_failure_raises_immediately_without_retry():
    provider = MagicMock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMProviderError("provider unavailable")

    with pytest.raises(CVParserError, match="LLM error during initial extraction"):
        parse_cv(SAMPLE_CV_TEXT, provider=provider)

    provider.generate_structured.assert_called_once()


def test_blank_cv_raises_without_calling_provider():
    provider = MagicMock(spec=LLMProvider)

    with pytest.raises(ValueError, match="CV text cannot be empty"):
        parse_cv("  \n", provider=provider)

    provider.generate_structured.assert_not_called()


def test_provider_contract_uses_candidate_schema_and_low_temperature():
    provider = _mock_provider(_chronological_profile())

    parse_cv(SAMPLE_CV_TEXT, provider=provider)

    call = provider.generate_structured.call_args
    assert call.kwargs["response_schema"] is CandidateProfile
    assert call.kwargs["temperature"] == 0.1
    system_instruction = call.kwargs["system_instruction"].lower()
    assert "never invent" in system_instruction
    assert "omit that technology entirely" in system_instruction
    assert "use null" in system_instruction
    assert "named languages" in system_instruction
