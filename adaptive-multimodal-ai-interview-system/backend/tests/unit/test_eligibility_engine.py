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
    RequirementType,
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


# ---------------------------------------------------------------------------
# Test 10: Missing Mandatory Skill Blocks Eligibility
# ---------------------------------------------------------------------------
def test_missing_mandatory_skill_blocks_eligibility():
    """
    A missing mandatory SKILL (not TECHNOLOGY) sets overall_eligible False.
    Day 7 audit found that required_skills/preferred_skills were never
    exercised anywhere in this suite — only required_technologies/
    preferred_technologies — despite going through the same matching code.
    """
    jd = _baseline_jd().model_copy(update={"required_skills": ["System Design"]})

    result = _run(jd, _baseline_candidate(), _baseline_application(), _baseline_constraints())

    skill_result = next(r for r in result.requirement_results if r.requirement.requirement == "System Design")
    assert skill_result.requirement.requirement_type == RequirementType.SKILL
    assert skill_result.status == MatchStatus.NOT_MET_MANDATORY
    assert result.overall_eligible is False


# ---------------------------------------------------------------------------
# Test 11: Missing Preferred Skill Does Not Block Eligibility
# ---------------------------------------------------------------------------
def test_missing_preferred_skill_does_not_block_eligibility():
    """A missing preferred SKILL (not TECHNOLOGY) is flagged but never blocks eligibility."""
    jd = _baseline_jd().model_copy(update={"preferred_skills": ["System Design"]})

    result = _run(jd, _baseline_candidate(), _baseline_application(), _baseline_constraints())

    skill_result = next(r for r in result.requirement_results if r.requirement.requirement == "System Design")
    assert skill_result.requirement.requirement_type == RequirementType.SKILL
    assert skill_result.status == MatchStatus.NOT_FOUND_PREFERRED
    assert result.overall_eligible is True


# ---------------------------------------------------------------------------
# Test 11b: Cross-Field Skill/Technology Match (JD Skill, CV Technology)
# ---------------------------------------------------------------------------
def test_required_skill_matches_candidate_technology_cross_field():
    """
    Regression test for the E2E-observed Python mismatch (see LIMITATIONS.md):
    the JD parser and CV parser are independent LLM extractions that don't
    reliably agree on which field a term belongs in. A JD requiring "Python"
    as a SKILL must MET against a candidate who has "Python" only under
    technologies, not skills.
    """
    jd = _baseline_jd().model_copy(update={"required_skills": ["Python"]})
    candidate = _baseline_candidate().model_copy(update={"skills": [], "technologies": ["FastAPI", "PostgreSQL", "Python"]})

    result = _run(jd, candidate, _baseline_application(), _baseline_constraints())

    python_skill_result = next(
        r for r in result.requirement_results
        if r.requirement.requirement == "Python" and r.requirement.requirement_type == RequirementType.SKILL
    )
    assert python_skill_result.status == MatchStatus.MET


# ---------------------------------------------------------------------------
# Test 11c: Cross-Field Match Is Also Case/Whitespace-Normalized
# ---------------------------------------------------------------------------
def test_required_technology_matches_candidate_skill_cross_field_normalized():
    """
    Mirror case of Test 11b (TECHNOLOGY requirement found under
    candidate.skills instead of candidate.technologies), combined with the
    existing case/whitespace normalization to confirm the combined-field
    lookup doesn't bypass it.
    """
    jd = _baseline_jd().model_copy(update={"required_technologies": ["FastAPI", "PostgreSQL", "Redis"]})
    candidate = _baseline_candidate().model_copy(update={"skills": ["  REDIS  "], "technologies": ["FastAPI", "PostgreSQL"]})

    result = _run(jd, candidate, _baseline_application(), _baseline_constraints())

    redis_result = next(r for r in result.requirement_results if r.requirement.requirement == "Redis")
    assert redis_result.requirement.requirement_type == RequirementType.TECHNOLOGY
    assert redis_result.status == MatchStatus.MET


# ---------------------------------------------------------------------------
# Test 11d: Degree Abbreviation Match — JD "Bachelor's" vs CV "B.S."
# ---------------------------------------------------------------------------
def test_education_bachelors_requirement_matches_bs_cv_entry():
    """
    Regression test for the E2E-observed Bachelor's/B.S. mismatch (see
    LIMITATIONS.md): a JD requiring "Bachelor's" must MET against a CV
    education entry phrased as "B.S." via the curated degree-abbreviation
    table, not just plain substring matching.
    """
    jd = _baseline_jd().model_copy(
        update={"education_requirements": [EducationRequirement(degree_level="Bachelor's", is_mandatory=True)]}
    )
    candidate = _baseline_candidate().model_copy(
        update={"education": ["B.S. in Computer Science, State University, 2020"]}
    )

    result = _run(jd, candidate, _baseline_application(), _baseline_constraints())

    education_result = next(r for r in result.requirement_results if r.requirement.requirement_type == RequirementType.EDUCATION)
    assert education_result.status == MatchStatus.MET


# ---------------------------------------------------------------------------
# Test 11e: Degree Abbreviation Match Is Bidirectional — JD "B.S." vs CV "Bachelor's"/"Bachelor of Science"
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("cv_education_entry", ["Bachelor's in Computer Science, State University", "Bachelor of Science in Computer Science, State University"])
def test_education_bs_requirement_matches_bachelors_cv_entry(cv_education_entry):
    """The reverse direction of Test 11d: JD phrased as the abbreviation, CV phrased in full."""
    jd = _baseline_jd().model_copy(
        update={"education_requirements": [EducationRequirement(degree_level="B.S.", is_mandatory=True)]}
    )
    candidate = _baseline_candidate().model_copy(update={"education": [cv_education_entry]})

    result = _run(jd, candidate, _baseline_application(), _baseline_constraints())

    education_result = next(r for r in result.requirement_results if r.requirement.requirement_type == RequirementType.EDUCATION)
    assert education_result.status == MatchStatus.MET


# ---------------------------------------------------------------------------
# Test 11f: Degree Term Absent From the Table Falls Back to Plain Substring Matching
# ---------------------------------------------------------------------------
def test_education_unlisted_degree_term_falls_back_to_substring_match():
    """
    A degree_level not present in _DEGREE_EQUIVALENCE_GROUPS (e.g. "MBA")
    must behave exactly as before: plain substring matching, unaffected by
    the new abbreviation table.
    """
    jd = _baseline_jd().model_copy(
        update={"education_requirements": [EducationRequirement(degree_level="MBA", is_mandatory=True)]}
    )
    candidate_match = _baseline_candidate().model_copy(update={"education": ["MBA, State University, 2020"]})
    candidate_no_match = _baseline_candidate().model_copy(update={"education": ["B.S. in Computer Science, State University, 2020"]})

    matched = _run(jd, candidate_match, _baseline_application(), _baseline_constraints())
    unmatched = _run(jd, candidate_no_match, _baseline_application(), _baseline_constraints())

    matched_result = next(r for r in matched.requirement_results if r.requirement.requirement_type == RequirementType.EDUCATION)
    unmatched_result = next(r for r in unmatched.requirement_results if r.requirement.requirement_type == RequirementType.EDUCATION)
    assert matched_result.status == MatchStatus.MET
    assert unmatched_result.status == MatchStatus.NOT_MET_MANDATORY


# ---------------------------------------------------------------------------
# Test 11g: A Genuinely Different Degree Level Still Correctly Fails
# ---------------------------------------------------------------------------
def test_education_genuinely_different_degree_still_fails():
    """
    The abbreviation table must not paper over an actual mismatch: a JD
    requiring a Master's degree against a candidate who only has a
    Bachelor's must still be NOT_MET_MANDATORY.
    """
    jd = _baseline_jd().model_copy(
        update={"education_requirements": [EducationRequirement(degree_level="Master's", is_mandatory=True)]}
    )
    candidate = _baseline_candidate().model_copy(
        update={"education": ["B.S. in Computer Science, State University, 2020"]}
    )

    result = _run(jd, candidate, _baseline_application(), _baseline_constraints())

    education_result = next(r for r in result.requirement_results if r.requirement.requirement_type == RequirementType.EDUCATION)
    assert education_result.status == MatchStatus.NOT_MET_MANDATORY
    assert result.overall_eligible is False


# ---------------------------------------------------------------------------
# Test 12: Joining Availability Exceeding the Limit Blocks Eligibility
# ---------------------------------------------------------------------------
def test_joining_availability_exceeds_limit_blocks_eligibility():
    """
    A joining_availability that parses successfully but exceeds
    max_notice_period_days blocks eligibility — the actual NOT_MET_MANDATORY
    path, distinct from the existing MET and unparseable-fails-safe tests,
    neither of which exercised this branch.
    """
    application = ApplicationDetails(joining_availability="60 days", salary_expectation=100000.0)

    result = _run(_baseline_jd(), _baseline_candidate(), application, _baseline_constraints())

    assert result.joining_availability_result.status == MatchStatus.NOT_MET_MANDATORY
    assert result.overall_eligible is False


# ---------------------------------------------------------------------------
# Test 13: Salary Below Minimum Blocks Eligibility
# ---------------------------------------------------------------------------
def test_salary_below_minimum_blocks_eligibility():
    """
    Candidate's salary_expectation below RecruiterConstraints.salary_min
    blocks eligibility — the violates_min branch of _check_salary, untested
    until now (only the violates_max direction was covered).
    """
    application = ApplicationDetails(joining_availability="2 weeks", salary_expectation=50000.0)

    result = _run(_baseline_jd(), _baseline_candidate(), application, _baseline_constraints())

    assert result.salary_result.status == MatchStatus.NOT_MET_MANDATORY
    assert result.overall_eligible is False


# ---------------------------------------------------------------------------
# Test 14: Multiple Simultaneous Mandatory Failures Are All Surfaced
# ---------------------------------------------------------------------------
def test_multiple_simultaneous_mandatory_failures_all_surfaced():
    """
    Three simultaneous, independent mandatory failures of different kinds
    (missing technology, salary over range, specific-experience shortfall)
    must ALL appear correctly in the result set — not just overall_eligible
    being False. Guards against an early-return bug that could silently
    drop a failure once another has already been found.
    """
    candidate = _baseline_candidate().model_copy(
        update={
            "technologies": ["FastAPI"],  # PostgreSQL (mandatory) now missing
            "technology_specific_experience": [
                TechnologyExperience(technology="Python", years=1.0)  # below the required 2.0
            ],
        }
    )
    application = ApplicationDetails(joining_availability="2 weeks", salary_expectation=150000.0)  # exceeds salary_max

    result = _run(_baseline_jd(), candidate, application, _baseline_constraints())

    postgres_result = next(r for r in result.requirement_results if r.requirement.requirement == "PostgreSQL")
    python_result = next(r for r in result.experience_results if r.match.target == "Python")
    general_result = next(r for r in result.experience_results if r.match.target is None)

    assert postgres_result.status == MatchStatus.NOT_MET_MANDATORY
    assert python_result.status == MatchStatus.NOT_MET_MANDATORY
    assert result.salary_result.status == MatchStatus.NOT_MET_MANDATORY
    assert general_result.status == MatchStatus.MET  # unrelated requirement, unaffected
    assert result.overall_eligible is False
