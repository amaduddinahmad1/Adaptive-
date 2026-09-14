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
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.llm.base import LLMProvider, LLMProviderError
from app.schemas.candidate import CandidateProfile, TechnologyExperience, WorkExperience
from app.schemas.job import (
    ClassifiedRequirement,
    EducationRequirement,
    ExperienceRequirement,
    ExperienceRequirementType,
    JobRequirementProfile,
    RequirementCategory,
    RequirementType,
)
from app.services.eligibility.eligibility_engine import (
    ApplicationDetails,
    MatchStatus,
    RecruiterConstraints,
    RequirementMatchResult,
    check_eligibility,
    format_eligibility_report,
)
from app.services.eligibility.experience_matcher import ExperienceMatchResult
from app.services.eligibility.semantic_skill_matcher import SkillJudgment, SkillJudgmentBatch
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


def _run(jd, candidate, application, constraints, provider=None):
    classified = classify_requirements(jd)
    return check_eligibility(jd, classified, candidate, application, constraints, today=TODAY, provider=provider)


def _mock_provider(response_text: str) -> MagicMock:
    """A fake LLMProvider (never a real API call) returning a fixed structured response."""
    provider = MagicMock(spec=LLMProvider)
    provider.generate_structured.return_value = response_text
    return provider


def _judgment_batch_json(*judgments: SkillJudgment) -> str:
    return SkillJudgmentBatch(judgments=list(judgments)).model_dump_json()


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


# ---------------------------------------------------------------------------
# Semantic skill matching (MatchStatus.MET_BY_INFERENCE) -- opt-in via `provider`
#
# check_eligibility()'s semantic-inference layer only activates when a
# provider is explicitly passed (see eligibility_engine.py's design note) --
# every test above this point omits `provider` and must therefore remain
# byte-for-byte unaffected by this layer's existence, which the full suite
# passing confirms. Every test below explicitly injects a fake LLMProvider
# (never a real API call) to test the layer itself.
# ---------------------------------------------------------------------------
def _semantic_jd() -> JobRequirementProfile:
    """Minimal JD isolating only the mandatory SKILL/TECHNOLOGY requirements under test."""
    return JobRequirementProfile(
        job_title="AI Engineer",
        required_skills=["Machine Learning"],
        required_technologies=["Kubernetes"],
    )


def _semantic_application() -> ApplicationDetails:
    return ApplicationDetails(joining_availability="immediate", salary_expectation=50000.0)


def _semantic_constraints() -> RecruiterConstraints:
    return RecruiterConstraints()  # no constraints stated -- always MET, keeps focus on skill/tech results


def test_reason_required_when_status_is_met_by_inference():
    """
    Direct test of the validator: RequirementMatchResult must refuse to be
    constructed with status=MET_BY_INFERENCE and no reason. This is the
    structural guarantee that an LLM-inferred match can never be silently
    indistinguishable from a deterministic exact-string MET anywhere
    downstream -- not just something we remember to set correctly.
    """
    requirement = ClassifiedRequirement(
        requirement="Machine Learning",
        category=RequirementCategory.MANDATORY,
        requirement_type=RequirementType.SKILL,
    )

    with pytest.raises(Exception):
        RequirementMatchResult(requirement=requirement, status=MatchStatus.MET_BY_INFERENCE, reason=None)

    # A reason present succeeds -- confirms the failure above is specifically about the missing reason.
    RequirementMatchResult(requirement=requirement, status=MatchStatus.MET_BY_INFERENCE, reason="because X")


def test_semantic_layer_true_positive_resolves_to_met_by_inference_with_reason():
    """
    The concrete bug this layer fixes: candidate has real ML signal
    (TensorFlow) but never literally writes "Machine Learning" or "ML" --
    a mocked provider judgment (never a real API call) resolves it to
    MET_BY_INFERENCE with the reason carried through to the result.
    """
    candidate = CandidateProfile(technologies=["TensorFlow", "Python"])
    provider = _mock_provider(
        _judgment_batch_json(
            SkillJudgment(
                requirement="Machine Learning",
                matched=True,
                reason="Candidate lists TensorFlow, a deep learning framework.",
            ),
            SkillJudgment(requirement="Kubernetes", matched=False, reason="No container orchestration experience listed."),
        )
    )

    result = _run(_semantic_jd(), candidate, _semantic_application(), _semantic_constraints(), provider=provider)

    ml_result = next(r for r in result.requirement_results if r.requirement.requirement == "Machine Learning")
    assert ml_result.status == MatchStatus.MET_BY_INFERENCE
    assert ml_result.reason == "Candidate lists TensorFlow, a deep learning framework."
    provider.generate_structured.assert_called_once()


def test_semantic_layer_false_positive_guard_stays_not_met_with_reason():
    """
    The false-positive guard: a mandatory requirement with no genuine
    supporting evidence must stay NOT_MET_MANDATORY even after going
    through the semantic layer -- proving the wiring doesn't rubber-stamp
    everything that reaches this fallback path. The candidate here has zero
    AI/ML or infra signal at all.
    """
    candidate = CandidateProfile(technologies=["React", "CSS"])
    provider = _mock_provider(
        _judgment_batch_json(
            SkillJudgment(
                requirement="Machine Learning",
                matched=False,
                reason="No ML/AI-related technologies, titles, or projects present.",
            ),
            SkillJudgment(requirement="Kubernetes", matched=False, reason="No container orchestration experience listed."),
        )
    )

    result = _run(_semantic_jd(), candidate, _semantic_application(), _semantic_constraints(), provider=provider)

    ml_result = next(r for r in result.requirement_results if r.requirement.requirement == "Machine Learning")
    k8s_result = next(r for r in result.requirement_results if r.requirement.requirement == "Kubernetes")
    assert ml_result.status == MatchStatus.NOT_MET_MANDATORY
    assert ml_result.reason == "No ML/AI-related technologies, titles, or projects present."
    assert k8s_result.status == MatchStatus.NOT_MET_MANDATORY
    assert result.overall_eligible is False


def test_semantic_layer_batches_multiple_requirements_into_a_single_call():
    """Two unmatched mandatory requirements must produce exactly one provider call, not two."""
    candidate = CandidateProfile(technologies=["TensorFlow"])
    provider = _mock_provider(
        _judgment_batch_json(
            SkillJudgment(requirement="Machine Learning", matched=True, reason="TensorFlow listed."),
            SkillJudgment(requirement="Kubernetes", matched=False, reason="No evidence."),
        )
    )

    _run(_semantic_jd(), candidate, _semantic_application(), _semantic_constraints(), provider=provider)

    assert provider.generate_structured.call_count == 1


def test_alias_table_resolves_before_ever_reaching_the_semantic_layer():
    """
    A requirement resolvable by the curated skill-alias table (e.g. "ML")
    must never reach the provider at all -- the provider here raises if
    called at all, which would fail this test if the ordering were wrong.
    """
    jd = JobRequirementProfile(job_title="AI Engineer", required_skills=["Machine Learning"])
    candidate = CandidateProfile(skills=["ML"])  # literal abbreviation, resolvable by the alias table alone
    provider = MagicMock(spec=LLMProvider)
    provider.generate_structured.side_effect = AssertionError("must not be called -- alias match should resolve this first")

    result = _run(jd, candidate, _semantic_application(), _semantic_constraints(), provider=provider)

    ml_result = next(r for r in result.requirement_results if r.requirement.requirement == "Machine Learning")
    assert ml_result.status == MatchStatus.MET
    assert ml_result.reason is None
    provider.generate_structured.assert_not_called()


def test_provider_omitted_never_calls_semantic_layer_and_stays_deterministic():
    """
    Omitting `provider` entirely must behave exactly as it did before this
    layer existed: no network call attempted (there's no provider to call),
    and the requirement stays NOT_MET_MANDATORY.
    """
    candidate = CandidateProfile(technologies=["TensorFlow"])

    result = _run(_semantic_jd(), candidate, _semantic_application(), _semantic_constraints())

    ml_result = next(r for r in result.requirement_results if r.requirement.requirement == "Machine Learning")
    assert ml_result.status == MatchStatus.NOT_MET_MANDATORY
    assert ml_result.reason is None


def test_semantic_layer_provider_failure_fails_safe_to_manual_review():
    """
    A provider failure (the same class of transient error seen in real
    pipeline runs today) must never fabricate a NOT_MET_MANDATORY verdict --
    it must fail safe to MANUAL_REVIEW_REQUIRED, consistent with how
    domain_experience/other_mandatory_requirements already handle "no
    reliable way to verify" elsewhere in this module. An infrastructure
    failure must never irreversibly block an otherwise eligible candidate.
    """
    candidate = CandidateProfile(technologies=["TensorFlow"])
    provider = MagicMock(spec=LLMProvider)
    provider.generate_structured.side_effect = LLMProviderError("simulated transient failure")

    result = _run(_semantic_jd(), candidate, _semantic_application(), _semantic_constraints(), provider=provider)

    ml_result = next(r for r in result.requirement_results if r.requirement.requirement == "Machine Learning")
    assert ml_result.status == MatchStatus.MANUAL_REVIEW_REQUIRED
    assert ml_result.reason is not None
    assert result.overall_eligible is True  # MANUAL_REVIEW_REQUIRED never blocks eligibility on its own


def test_semantic_layer_report_surfaces_reason_for_inferred_match():
    """format_eligibility_report() must render the reason inline for MET_BY_INFERENCE, not just the bare status."""
    candidate = CandidateProfile(technologies=["TensorFlow"])
    provider = _mock_provider(
        _judgment_batch_json(
            SkillJudgment(requirement="Machine Learning", matched=True, reason="Candidate lists TensorFlow."),
            SkillJudgment(requirement="Kubernetes", matched=True, reason="Assumed present for this report-rendering test."),
        )
    )

    result = _run(_semantic_jd(), candidate, _semantic_application(), _semantic_constraints(), provider=provider)
    report = format_eligibility_report(result)

    assert "Machine Learning: MET (inferred) — Candidate lists TensorFlow." in report


def test_report_surfaces_reason_for_not_met_mandatory_from_semantic_layer():
    """
    Real gap found and fixed: format_eligibility_report() used to only
    render req_result.reason for MET_BY_INFERENCE, so a semantic-layer
    NOT_MET_MANDATORY verdict (which also carries a real, specific reason)
    was invisible in the printed report even though it was correctly
    persisted in the DB. The report must now show it too.
    """
    candidate = CandidateProfile(technologies=["React", "CSS"])
    provider = _mock_provider(
        _judgment_batch_json(
            SkillJudgment(
                requirement="Machine Learning",
                matched=False,
                reason="No ML/AI-related technologies, titles, or projects present.",
            ),
            SkillJudgment(requirement="Kubernetes", matched=False, reason="No container orchestration experience listed."),
        )
    )

    result = _run(_semantic_jd(), candidate, _semantic_application(), _semantic_constraints(), provider=provider)
    report = format_eligibility_report(result)

    assert "Machine Learning: NOT MET — No ML/AI-related technologies, titles, or projects present." in report
