"""
tests/unit/test_experience_matcher.py

Unit tests for app.services.eligibility.experience_matcher: verifies that
general and specific experience requirements are matched strictly
independently against a CandidateProfile, that multiple requirements are
evaluated without cross-contamination, and that the date-handling edge
cases from date_utils (present/overlap/missing dates) are correctly wired
through match_experience.

Tests 1-3 are the Day 4 "must pass before today is done" sanity checks
called out in the brief, since Day 5's eligibility engine depends directly
on this logic.
"""

from datetime import date

from app.schemas.candidate import CandidateProfile, TechnologyExperience, WorkExperience
from app.schemas.job import ExperienceRequirement, ExperienceRequirementType, JobRequirementProfile
from app.services.eligibility.experience_matcher import (
    match_all_experience_requirements,
    match_experience,
)

TODAY = date(2026, 9, 8)


# ---------------------------------------------------------------------------
# Test 1 (Day 4 sanity check): Specific Experience Not Inflated by Overall
# ---------------------------------------------------------------------------
def test_specific_experience_not_inflated_by_overall_experience():
    """
    Candidate has 4 years overall software experience but only 1 year of
    Python; JD requires 2 years Python (SPECIFIC). Must be NOT MET — the
    4-year overall tenure must never satisfy a technology-specific requirement.
    """
    candidate = CandidateProfile(
        work_experience=[
            WorkExperience(position="Engineer", start_date="2020-01", end_date="2024-01"),
        ],
        technology_specific_experience=[
            TechnologyExperience(technology="Python", years=1.0),
        ],
    )
    requirement = ExperienceRequirement(
        description="2 years Python experience",
        years=2.0,
        requirement_type=ExperienceRequirementType.SPECIFIC,
        target="Python",
        is_mandatory=True,
    )

    result = match_experience(requirement, candidate, today=TODAY)

    assert result.candidate_years == 1.0
    assert result.met is False
    assert result.requirement_type == ExperienceRequirementType.SPECIFIC


# ---------------------------------------------------------------------------
# Test 2 (Day 4 sanity check): General Experience Met
# ---------------------------------------------------------------------------
def test_general_experience_met():
    """Candidate has 3 years relevant experience; JD requires 2 years general -> MET."""
    candidate = CandidateProfile(
        work_experience=[
            WorkExperience(position="Engineer", start_date="2021-01", end_date="2024-01"),
        ],
    )
    requirement = ExperienceRequirement(
        description="2 years professional software development experience",
        years=2.0,
        requirement_type=ExperienceRequirementType.GENERAL,
        target=None,
        is_mandatory=True,
    )

    result = match_experience(requirement, candidate, today=TODAY)

    expected_days = (date(2024, 1, 1) - date(2021, 1, 1)).days
    assert result.candidate_years == expected_days / 365.25
    assert result.met is True
    assert result.requirement_type == ExperienceRequirementType.GENERAL


# ---------------------------------------------------------------------------
# Test 3 (Day 4 sanity check): Multiple Independent Requirements
# ---------------------------------------------------------------------------
def test_multiple_independent_requirements_each_evaluated_separately():
    """
    JD requires 3yr overall (candidate has 4, met) + 2yr Python (candidate has
    2.5, met) + 1yr FastAPI (candidate has 0.5, not met). Each must be
    evaluated independently via match_all_experience_requirements, with none
    affecting the others' outcome.
    """
    candidate = CandidateProfile(
        work_experience=[
            WorkExperience(position="Engineer", start_date="2020-01", end_date="2024-01"),
        ],
        technology_specific_experience=[
            TechnologyExperience(technology="Python", years=2.5),
            TechnologyExperience(technology="FastAPI", years=0.5),
        ],
    )
    job_profile = JobRequirementProfile(
        job_title="Backend API Architect",
        experience_requirements=[
            ExperienceRequirement(
                description="3 years overall software development experience",
                years=3.0,
                requirement_type=ExperienceRequirementType.GENERAL,
                target=None,
                is_mandatory=True,
            ),
            ExperienceRequirement(
                description="2 years Python experience",
                years=2.0,
                requirement_type=ExperienceRequirementType.SPECIFIC,
                target="Python",
                is_mandatory=True,
            ),
            ExperienceRequirement(
                description="1 year FastAPI experience",
                years=1.0,
                requirement_type=ExperienceRequirementType.SPECIFIC,
                target="FastAPI",
                is_mandatory=True,
            ),
        ],
    )

    results = match_all_experience_requirements(job_profile, candidate, today=TODAY)

    assert len(results) == 3

    general_result, python_result, fastapi_result = results

    expected_general_days = (date(2024, 1, 1) - date(2020, 1, 1)).days
    assert general_result.candidate_years == expected_general_days / 365.25
    assert general_result.met is True

    assert python_result.candidate_years == 2.5
    assert python_result.met is True

    assert fastapi_result.candidate_years == 0.5
    assert fastapi_result.met is False


# ---------------------------------------------------------------------------
# Test 4: Zero Specific Experience for a Technology With No Entry
# ---------------------------------------------------------------------------
def test_zero_specific_experience_when_technology_absent():
    """JD requires 2 years in a technology the candidate's profile has no entry for -> NOT MET, no crash."""
    candidate = CandidateProfile(technology_specific_experience=[])
    requirement = ExperienceRequirement(
        description="2 years Go experience",
        years=2.0,
        requirement_type=ExperienceRequirementType.SPECIFIC,
        target="Go",
        is_mandatory=True,
    )

    result = match_experience(requirement, candidate, today=TODAY)

    assert result.candidate_years == 0.0
    assert result.met is False


# ---------------------------------------------------------------------------
# Test 5: Currently Employed / "present" End Date
# ---------------------------------------------------------------------------
def test_present_end_date_contributes_duration_to_today():
    """A work_experience entry with end_date='present' contributes duration up to the injected today."""
    candidate = CandidateProfile(
        work_experience=[
            WorkExperience(position="Engineer", start_date="2024-01", end_date="present"),
        ],
    )
    requirement = ExperienceRequirement(
        description="2 years general experience",
        years=2.0,
        requirement_type=ExperienceRequirementType.GENERAL,
        target=None,
        is_mandatory=True,
    )

    result = match_experience(requirement, candidate, today=TODAY)

    expected_days = (TODAY - date(2024, 1, 1)).days
    assert result.candidate_years == expected_days / 365.25
    assert result.candidate_years > 0.0
    assert result.met is True


# ---------------------------------------------------------------------------
# Test 6: Overlapping Job Dates Not Double-Counted
# ---------------------------------------------------------------------------
def test_overlapping_work_experience_not_double_counted():
    """Two overlapping work_experience entries must not double-count the overlap in the general total."""
    candidate = CandidateProfile(
        work_experience=[
            WorkExperience(position="Engineer", company="A", start_date="2020-01", end_date="2022-01"),
            WorkExperience(position="Consultant", company="B", start_date="2021-01", end_date="2023-01"),
        ],
    )
    requirement = ExperienceRequirement(
        description="2 years general experience",
        years=2.0,
        requirement_type=ExperienceRequirementType.GENERAL,
        target=None,
        is_mandatory=True,
    )

    result = match_experience(requirement, candidate, today=TODAY)

    expected_days = (date(2023, 1, 1) - date(2020, 1, 1)).days
    assert result.candidate_years == expected_days / 365.25


# ---------------------------------------------------------------------------
# Test 7: Missing/None Dates Excluded Without Crashing
# ---------------------------------------------------------------------------
def test_missing_dates_excluded_without_crashing():
    """A work_experience entry with None dates is excluded from the general total, without crashing."""
    candidate = CandidateProfile(
        work_experience=[
            WorkExperience(position="Engineer", start_date="2020-01", end_date="2022-01"),
            WorkExperience(position="Startup Gig", start_date=None, end_date=None),
        ],
    )
    requirement = ExperienceRequirement(
        description="1 year general experience",
        years=1.0,
        requirement_type=ExperienceRequirementType.GENERAL,
        target=None,
        is_mandatory=True,
    )

    result = match_experience(requirement, candidate, today=TODAY)

    expected_days = (date(2022, 1, 1) - date(2020, 1, 1)).days
    assert result.candidate_years == expected_days / 365.25
    assert result.met is True


# ---------------------------------------------------------------------------
# Test 8: Technology Lookup Is Case- and Whitespace-Insensitive
# ---------------------------------------------------------------------------
def test_technology_lookup_is_case_and_whitespace_insensitive():
    """
    JD target 'python' (lowercase) must match a candidate technology entry of
    ' Python ' (different case, incidental whitespace) — JD parsing and CV
    parsing are independent LLM extractions with no shared vocabulary
    enforcement, so exact-string matching would silently under-report a
    candidate's real experience.
    """
    candidate = CandidateProfile(
        technology_specific_experience=[
            TechnologyExperience(technology=" Python ", years=2.5),
        ],
    )
    requirement = ExperienceRequirement(
        description="2 years Python experience",
        years=2.0,
        requirement_type=ExperienceRequirementType.SPECIFIC,
        target="python",
        is_mandatory=True,
    )

    result = match_experience(requirement, candidate, today=TODAY)

    assert result.candidate_years == 2.5
    assert result.met is True


# ---------------------------------------------------------------------------
# Test 9: Zero General Experience When Candidate Has No Work History
# ---------------------------------------------------------------------------
def test_general_experience_zero_when_no_work_history():
    """
    JD requires 2 years general experience; candidate has no work_experience
    at all -> NOT MET, no crash. calculate_total_general_experience([]) == 0.0
    is already tested in isolation (test_date_utils.py), but this confirms
    the wiring through match_experience produces a correct NOT MET result,
    not just the right number in isolation.
    """
    candidate = CandidateProfile(work_experience=[])
    requirement = ExperienceRequirement(
        description="2 years general experience",
        years=2.0,
        requirement_type=ExperienceRequirementType.GENERAL,
        target=None,
        is_mandatory=True,
    )

    result = match_experience(requirement, candidate, today=TODAY)

    assert result.candidate_years == 0.0
    assert result.met is False
