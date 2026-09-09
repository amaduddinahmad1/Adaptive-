"""
tests/unit/test_eligibility_engine.py

Unit tests for app.services.eligibility.eligibility_engine: verifies that
check_eligibility() correctly combines experience matching (Day 4),
classified requirement matching (Day 3), and recruiter-form inputs (joining
availability, salary) into a single eligibility decision, with
overall_eligible False if and only if some check is genuinely mandatory and
unmet — never for a preferred miss, and never for a MANUAL_REVIEW_REQUIRED
item, even a mandatory one.
"""

from datetime import date
from unittest.mock import patch

import pytest

from app.schemas.candidate import CandidateProfile, TechnologyExperience, WorkExperience
from app.schemas.job import (
    EducationRequirement,
    ExperienceRequirement,
    ExperienceRequirementType,
    JobRequirementProfile,
)
from app.services.eligibility.eligibility_engine import (
    ApplicationDetails,
    MatchStatus,
    RecruiterConstraints,
    check_eligibility,
    format_eligibility_report,
)
from app.services.eligibility.experience_matcher import ExperienceMatchResult
from app.services.jd_intelligence.requirement_classifier import classify_requirements

TODAY = date(2026, 9, 9)


def _baseline_jd() -> JobRequirementProfile:
    return JobRequirementProfile(
        job_title="Senior Python Developer",
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
        ],
        required_technologies=["FastAPI", "PostgreSQL"],
        preferred_technologies=["Docker"],
        education_requirements=[
            EducationRequirement(degree_level="Bachelor's", field_of_study="Computer Science", is_mandatory=True),
        ],
    )


def _baseline_candidate() -> CandidateProfile:
    return CandidateProfile(
        technologies=["FastAPI", "PostgreSQL"],
        education=["Bachelor's in Computer Science, State University"],
        work_experience=[
            WorkExperience(position="Backend Engineer", start_date="2020-01", end_date="2024-01"),
        ],
        technology_specific_experience=[
            TechnologyExperience(technology="Python", years=2.5),
        ],
    )


def _baseline_application() -> ApplicationDetails:
    return ApplicationDetails(joining_availability="2 weeks", salary_expectation=100000.0)


def _baseline_constraints() -> RecruiterConstraints:
    return RecruiterConstraints(max_notice_period_days=30, salary_min=80000.0, salary_max=120000.0)


def _run(jd, candidate, application, constraints):
    classified = classify_requirements(jd)
    return check_eligibility(jd, classified, candidate, application, constraints, today=TODAY)


# ---------------------------------------------------------------------------
# Test 1: Eligible Candidate
# ---------------------------------------------------------------------------
def test_eligible_candidate():
    """A candidate meeting all mandatory requirements (missing only the preferred Docker) is ELIGIBLE."""
    result = _run(_baseline_jd(), _baseline_candidate(), _baseline_application(), _baseline_constraints())

    assert result.overall_eligible is True


# ---------------------------------------------------------------------------
# Test 2: Salary Blocks Eligibility
# ---------------------------------------------------------------------------
def test_salary_blocks_eligibility():
    """Candidate's salary_expectation exceeding RecruiterConstraints.salary_max blocks eligibility."""
    application = ApplicationDetails(joining_availability="2 weeks", salary_expectation=150000.0)

    result = _run(_baseline_jd(), _baseline_candidate(), application, _baseline_constraints())

    assert result.salary_result.status == MatchStatus.NOT_MET_MANDATORY
    assert result.overall_eligible is False


# ---------------------------------------------------------------------------
# Test 3: Missing Preferred Item Does Not Block Eligibility
# ---------------------------------------------------------------------------
def test_missing_preferred_item_does_not_block_eligibility():
    """A missing preferred technology (Docker) is flagged NOT_FOUND_PREFERRED but never blocks overall_eligible."""
    result = _run(_baseline_jd(), _baseline_candidate(), _baseline_application(), _baseline_constraints())

    docker_result = next(r for r in result.requirement_results if r.requirement.requirement == "Docker")
    assert docker_result.status == MatchStatus.NOT_FOUND_PREFERRED
    assert result.overall_eligible is True


# ---------------------------------------------------------------------------
# Test 4: Missing Mandatory Requirement Blocks Eligibility
# ---------------------------------------------------------------------------
def test_missing_mandatory_requirement_blocks_eligibility():
    """A missing mandatory technology (PostgreSQL) sets overall_eligible False."""
    candidate = _baseline_candidate().model_copy(update={"technologies": ["FastAPI"]})

    result = _run(_baseline_jd(), candidate, _baseline_application(), _baseline_constraints())

    postgres_result = next(r for r in result.requirement_results if r.requirement.requirement == "PostgreSQL")
    assert postgres_result.status == MatchStatus.NOT_MET_MANDATORY
    assert result.overall_eligible is False


# ---------------------------------------------------------------------------
# Test 5: Specific Experience Failure Blocks Eligibility
# ---------------------------------------------------------------------------
def test_specific_experience_failure_blocks_eligibility():
    """
    A mandatory specific-experience shortfall (Day 4's matcher) blocks
    eligibility, while an unrelated, independently-met general requirement
    is unaffected.
    """
    candidate = _baseline_candidate().model_copy(
        update={"technology_specific_experience": [TechnologyExperience(technology="Python", years=1.0)]}
    )

    result = _run(_baseline_jd(), candidate, _baseline_application(), _baseline_constraints())

    python_result = next(r for r in result.experience_results if r.match.target == "Python")
    general_result = next(r for r in result.experience_results if r.match.target is None)

    assert python_result.status == MatchStatus.NOT_MET_MANDATORY
    assert general_result.status == MatchStatus.MET
    assert result.overall_eligible is False


# ---------------------------------------------------------------------------
# Test 6a: Joining Availability Parses and Meets Constraint
# ---------------------------------------------------------------------------
def test_joining_availability_parses_and_meets_constraint():
    """'2 weeks' (14 days) against a 30-day max notice period constraint is MET."""
    result = _run(_baseline_jd(), _baseline_candidate(), _baseline_application(), _baseline_constraints())

    assert result.joining_availability_result.status == MatchStatus.MET


# ---------------------------------------------------------------------------
# Test 6b: Joining Availability Unparseable Fails Safe
# ---------------------------------------------------------------------------
def test_joining_availability_unparseable_fails_safe():
    """
    An ambiguous joining_availability string ('soon') against a stated
    constraint cannot be confidently parsed. It must not silently pass or
    silently fail — it becomes MANUAL_REVIEW_REQUIRED and does not block an
    otherwise-qualified candidate.
    """
    application = ApplicationDetails(joining_availability="soon", salary_expectation=100000.0)

    result = _run(_baseline_jd(), _baseline_candidate(), application, _baseline_constraints())

    assert result.joining_availability_result.status == MatchStatus.MANUAL_REVIEW_REQUIRED
    assert result.overall_eligible is True


# ---------------------------------------------------------------------------
# Test 7: Length-Mismatch Assertion Fires
# ---------------------------------------------------------------------------
def test_length_mismatch_assertion_fires():
    """
    If match_all_experience_requirements ever returned a different number of
    results than input requirements, check_eligibility must refuse to
    silently pair them up — verified by forcing a mismatch via mocking, since
    this can't happen through normal operation of the real matcher.
    """
    jd = _baseline_jd()
    candidate = _baseline_candidate()
    classified = classify_requirements(jd)

    mismatched_results = [
        ExperienceMatchResult(
            description="stub",
            required_years=1.0,
            candidate_years=1.0,
            met=True,
            requirement_type=ExperienceRequirementType.GENERAL,
            target=None,
        )
    ]  # jd has 2 experience_requirements, this list has only 1

    with patch(
        "app.services.eligibility.eligibility_engine.match_all_experience_requirements",
        return_value=mismatched_results,
    ):
        with pytest.raises(AssertionError, match="cannot safely pair"):
            check_eligibility(jd, classified, candidate, _baseline_application(), _baseline_constraints(), today=TODAY)


# ---------------------------------------------------------------------------
# Test 8: Mandatory "Other" Requirement Manual Review Never Blocks
# ---------------------------------------------------------------------------
def test_mandatory_other_requirement_manual_review_never_blocks():
    """
    other_mandatory_requirements (e.g. work authorization) has no
    corresponding CandidateProfile field to verify against. It must become
    MANUAL_REVIEW_REQUIRED, not a fabricated pass or fail, and must never
    block overall_eligible on its own — this is the highest-stakes
    regression to guard against in this module.
    """
    jd = _baseline_jd().model_copy(
        update={"other_mandatory_requirements": ["Must be eligible to work in the US"]}
    )

    result = _run(jd, _baseline_candidate(), _baseline_application(), _baseline_constraints())

    other_result = next(
        r for r in result.requirement_results if r.requirement.requirement == "Must be eligible to work in the US"
    )
    assert other_result.status == MatchStatus.MANUAL_REVIEW_REQUIRED
    assert result.overall_eligible is True


# ---------------------------------------------------------------------------
# Test 9: format_eligibility_report Matches the Exact Target Format
# ---------------------------------------------------------------------------
def test_format_eligibility_report_matches_exact_target_format():
    """
    Locks in the proposal's exact target output format character-for-
    character, for a candidate with no stated recruiter constraints and no
    manual-review items. "Education" here is simply the JD's literal
    degree_level text (not a hardcoded label in the formatter) — every
    education entry renders using its own requirement text, which happens to
    read as "Education" for this specific JD.
    """
    jd = JobRequirementProfile(
        job_title="Senior Python Developer",
        experience_requirements=[
            ExperienceRequirement(
                description="3 years overall",
                years=3.0,
                requirement_type=ExperienceRequirementType.GENERAL,
                target=None,
                is_mandatory=True,
            ),
            ExperienceRequirement(
                description="2 years Python",
                years=2.0,
                requirement_type=ExperienceRequirementType.SPECIFIC,
                target="Python",
                is_mandatory=True,
            ),
        ],
        required_technologies=["FastAPI", "PostgreSQL"],
        preferred_technologies=["Docker"],
        education_requirements=[EducationRequirement(degree_level="Education", is_mandatory=True)],
    )
    candidate = CandidateProfile(
        technologies=["FastAPI", "PostgreSQL"],
        education=["Education"],
        work_experience=[WorkExperience(position="Engineer", start_date="2020-01", end_date="2024-01")],
        technology_specific_experience=[TechnologyExperience(technology="Python", years=2.5)],
    )
    application = ApplicationDetails(joining_availability="immediate", salary_expectation=100000.0)
    constraints = RecruiterConstraints()  # no stated constraints -> no join/salary lines in the report

    result = _run(jd, candidate, application, constraints)
    report = format_eligibility_report(result)

    expected = (
        "Overall Experience: MET\n"
        "Python Experience: MET\n"
        "FastAPI: MET\n"
        "PostgreSQL: MET\n"
        "Docker: NOT FOUND - Preferred\n"
        "Education: MET\n"
        "Eligibility: ELIGIBLE"
    )
    assert report == expected
