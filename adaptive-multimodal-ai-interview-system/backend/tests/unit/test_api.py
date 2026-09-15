"""
tests/unit/test_api.py

Automated sanity tests for the Day 6 FastAPI service, using
fastapi.testclient.TestClient. LLM calls are mocked throughout (patched at
the point app.api.routes.pipeline imports them) — these are fast, CI-safe
tests, separate from Step 3's manual checks against the real Gemini API.

/match-experience and /check-eligibility need no mocking: both are pure
computation over already-structured input, with no LLM involved.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile
from app.services.cv_intelligence.cv_parser import CVParserError
from app.services.jd_intelligence.jd_parser import JDParserError

client = TestClient(app)

_GENERIC_ERROR_BODY = {"detail": "An internal error occurred while processing the request."}


def _sample_jd_profile_dict() -> dict:
    return {
        "job_title": "Senior Backend Engineer",
        "experience_requirements": [
            {
                "description": "3 years overall software development experience",
                "years": 3.0,
                "requirement_type": "general",
                "target": None,
                "is_mandatory": True,
            },
            {
                "description": "2 years Python experience",
                "years": 2.0,
                "requirement_type": "specific",
                "target": "Python",
                "is_mandatory": True,
            },
        ],
        "required_technologies": ["FastAPI", "PostgreSQL"],
        "preferred_technologies": ["Docker"],
        "education_requirements": [
            {"degree_level": "Bachelor's", "field_of_study": "Computer Science", "is_mandatory": True}
        ],
    }


def _sample_candidate_dict() -> dict:
    return {
        "technologies": ["FastAPI", "PostgreSQL"],
        "education": ["Bachelor's in Computer Science, State University"],
        "work_experience": [
            {"position": "Backend Engineer", "start_date": "2020-01", "end_date": "2024-01"},
        ],
        "technology_specific_experience": [
            {"technology": "Python", "years": 2.5},
        ],
    }


def _sample_check_eligibility_body() -> dict:
    return {
        "job_profile": _sample_jd_profile_dict(),
        "candidate": _sample_candidate_dict(),
        "application": {"joining_availability": "2 weeks", "salary_expectation": 100000},
        "constraints": {"max_notice_period_days": 30, "salary_min": 80000, "salary_max": 120000},
    }


# ---------------------------------------------------------------------------
# Test 1: /analyze-jd returns a valid profile (mocked LLM)
# ---------------------------------------------------------------------------
@patch("app.api.routes.pipeline.parse_job_description")
def test_analyze_jd_returns_valid_profile(mock_parse):
    mock_parse.return_value = JobRequirementProfile(**_sample_jd_profile_dict())

    response = client.post("/analyze-jd", json={"jd_text": "Some real-world JD text"})

    assert response.status_code == 200
    data = response.json()
    assert data["job_title"] == "Senior Backend Engineer"
    assert len(data["experience_requirements"]) == 2
    mock_parse.assert_called_once_with("Some real-world JD text")


# ---------------------------------------------------------------------------
# Test 2: /analyze-cv returns a valid profile (mocked LLM)
# ---------------------------------------------------------------------------
@patch("app.api.routes.pipeline.parse_cv")
def test_analyze_cv_returns_valid_profile(mock_parse):
    mock_parse.return_value = CandidateProfile(**_sample_candidate_dict())

    response = client.post("/analyze-cv", json={"cv_text": "Some real-world CV text"})

    assert response.status_code == 200
    data = response.json()
    assert "FastAPI" in data["technologies"]
    mock_parse.assert_called_once_with("Some real-world CV text")


# ---------------------------------------------------------------------------
# Test 3: /match-experience returns valid results (no mocking needed)
# ---------------------------------------------------------------------------
def test_match_experience_returns_valid_results():
    response = client.post(
        "/match-experience",
        json={"job_profile": _sample_jd_profile_dict(), "candidate": _sample_candidate_dict()},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    python_result = next(r for r in data if r["target"] == "Python")
    assert python_result["met"] is True
    assert python_result["candidate_years"] == 2.5


# ---------------------------------------------------------------------------
# Test 4: /check-eligibility returns a valid result (no mocking needed)
# ---------------------------------------------------------------------------
def test_check_eligibility_returns_valid_result():
    response = client.post("/check-eligibility", json=_sample_check_eligibility_body())

    assert response.status_code == 200
    data = response.json()
    assert data["overall_eligible"] is True  # only Docker (preferred) is missing

    fastapi_result = next(
        r for r in data["requirement_results"] if r["requirement"]["requirement"] == "FastAPI"
    )
    assert fastapi_result["status"] == "met"


# ---------------------------------------------------------------------------
# Test 5: /analyze-jd blank input returns 400
# ---------------------------------------------------------------------------
def test_analyze_jd_blank_input_returns_400():
    response = client.post("/analyze-jd", json={"jd_text": "   "})

    assert response.status_code == 400
    assert response.json() == {"detail": "Job description text cannot be empty."}


# ---------------------------------------------------------------------------
# Test 6: /analyze-cv blank input returns 400
# ---------------------------------------------------------------------------
def test_analyze_cv_blank_input_returns_400():
    response = client.post("/analyze-cv", json={"cv_text": ""})

    assert response.status_code == 400
    assert response.json() == {"detail": "CV text cannot be empty."}


# ---------------------------------------------------------------------------
# Test 7: /check-eligibility malformed body returns 422
# ---------------------------------------------------------------------------
def test_check_eligibility_malformed_body_returns_422():
    response = client.post("/check-eligibility", json={"job_profile": {"job_title": "Test"}})

    assert response.status_code == 422
    missing_fields = {error["loc"][-1] for error in response.json()["detail"]}
    assert missing_fields == {"candidate", "application", "constraints"}


# ---------------------------------------------------------------------------
# Test 8: /analyze-jd JDParserError returns 500 with a generic, non-leaky message
# ---------------------------------------------------------------------------
@patch("app.api.routes.pipeline.parse_job_description")
def test_analyze_jd_parser_error_returns_500_generic_message(mock_parse):
    mock_parse.side_effect = JDParserError("Sensitive internal detail: API key xyz123 rejected")

    response = client.post("/analyze-jd", json={"jd_text": "Some JD text"})

    assert response.status_code == 500
    assert response.json() == _GENERIC_ERROR_BODY
    assert "xyz123" not in response.text
    assert "Sensitive internal detail" not in response.text


# ---------------------------------------------------------------------------
# Test 9: /analyze-cv CVParserError returns 500 with a generic, non-leaky message
# ---------------------------------------------------------------------------
@patch("app.api.routes.pipeline.parse_cv")
def test_analyze_cv_parser_error_returns_500_generic_message(mock_parse):
    mock_parse.side_effect = CVParserError("Sensitive internal detail: token abc789 invalid")

    response = client.post("/analyze-cv", json={"cv_text": "Some CV text"})

    assert response.status_code == 500
    assert response.json() == _GENERIC_ERROR_BODY
    assert "abc789" not in response.text


# ---------------------------------------------------------------------------
# Test 10: /check-eligibility AssertionError returns 500 with a generic message
# ---------------------------------------------------------------------------
@patch("app.api.routes.pipeline.check_eligibility")
def test_check_eligibility_assertion_error_returns_500_generic_message(mock_check):
    mock_check.side_effect = AssertionError("internal invariant violated: length mismatch")

    response = client.post("/check-eligibility", json=_sample_check_eligibility_body())

    assert response.status_code == 500
    assert response.json() == _GENERIC_ERROR_BODY
    assert "invariant" not in response.text
