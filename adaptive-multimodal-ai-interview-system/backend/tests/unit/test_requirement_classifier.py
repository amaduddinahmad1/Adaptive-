"""
tests/unit/test_requirement_classifier.py

Unit tests for requirement_classifier.classify_requirements().
Validates that mandatory/preferred status is read from Day 1's existing
JobRequirementProfile classification (not re-derived), that the documented
required/preferred conflict rule and domain-experience default are applied
correctly, and that empty/minimal profiles and multi-item experience lists
are handled without crashing or cross-contamination.
"""

from app.schemas.job import (
    CertificationRequirement,
    ExperienceRequirement,
    ExperienceRequirementType,
    JobRequirementProfile,
    RequirementCategory,
    RequirementType,
)
from app.services.jd_intelligence.requirement_classifier import classify_requirements


# ---------------------------------------------------------------------------
# Test 1: Required Technology Classified as Mandatory
# ---------------------------------------------------------------------------
def test_required_technology_classified_as_mandatory():
    """Verifies a required_technologies entry becomes a mandatory technology requirement."""
    profile = JobRequirementProfile(job_title="Test", required_technologies=["Python"])

    result = classify_requirements(profile)

    assert len(result) == 1
    entry = result[0]
    assert entry.requirement == "Python"
    assert entry.category == RequirementCategory.MANDATORY
    assert entry.requirement_type == RequirementType.TECHNOLOGY
    assert entry.source_detail is None


# ---------------------------------------------------------------------------
# Test 2: Preferred Technology Classified as Preferred
# ---------------------------------------------------------------------------
def test_preferred_technology_classified_as_preferred():
    """Verifies a preferred_technologies entry becomes a preferred technology requirement."""
    profile = JobRequirementProfile(job_title="Test", preferred_technologies=["Docker"])

    result = classify_requirements(profile)

    assert len(result) == 1
    entry = result[0]
    assert entry.requirement == "Docker"
    assert entry.category == RequirementCategory.PREFERRED
    assert entry.requirement_type == RequirementType.TECHNOLOGY


# ---------------------------------------------------------------------------
# Test 3: General Mandatory Experience Requirement
# ---------------------------------------------------------------------------
def test_general_experience_requirement_classified_as_mandatory():
    """Verifies a mandatory general experience requirement is classified correctly
    and its structured detail (years/target) is preserved via source_detail."""
    exp = ExperienceRequirement(
        description="3 years professional software development experience",
        years=3.0,
        requirement_type=ExperienceRequirementType.GENERAL,
        target=None,
        is_mandatory=True,
    )
    profile = JobRequirementProfile(job_title="Test", experience_requirements=[exp])

    result = classify_requirements(profile)

    assert len(result) == 1
    entry = result[0]
    assert entry.category == RequirementCategory.MANDATORY
    assert entry.requirement_type == RequirementType.EXPERIENCE
    assert entry.source_detail is exp
    assert entry.source_detail.years == 3.0
    assert entry.source_detail.target is None


# ---------------------------------------------------------------------------
# Test 4: Preferred Certification
# ---------------------------------------------------------------------------
def test_preferred_certification_classified_as_preferred():
    """Verifies a certification with is_mandatory=False is classified as preferred."""
    cert = CertificationRequirement(name="AWS certification", is_mandatory=False)
    profile = JobRequirementProfile(job_title="Test", certifications=[cert])

    result = classify_requirements(profile)

    assert len(result) == 1
    entry = result[0]
    assert entry.requirement == "AWS certification"
    assert entry.category == RequirementCategory.PREFERRED
    assert entry.requirement_type == RequirementType.CERTIFICATION
    assert entry.source_detail is cert


# ---------------------------------------------------------------------------
# Test 5: Required/Preferred Conflict Resolves to Mandatory
# ---------------------------------------------------------------------------
def test_required_preferred_conflict_resolves_to_mandatory():
    """
    Verifies the documented conflict-resolution rule: when the same name
    appears in both a required_* and preferred_* list (a data-quality
    artifact, not a genuine either/or), exactly one entry is emitted and it
    is MANDATORY — the preferred duplicate is dropped, not merely shadowed.
    """
    profile = JobRequirementProfile(
        job_title="Test",
        required_skills=["SQL"],
        preferred_skills=["SQL", "Excel"],
        required_technologies=["Python"],
        preferred_technologies=["Python", "Redis"],
    )

    result = classify_requirements(profile)

    sql_entries = [r for r in result if r.requirement == "SQL"]
    python_entries = [r for r in result if r.requirement == "Python"]

    assert len(sql_entries) == 1
    assert sql_entries[0].category == RequirementCategory.MANDATORY

    assert len(python_entries) == 1
    assert python_entries[0].category == RequirementCategory.MANDATORY

    # Non-conflicting items are unaffected
    assert any(r.requirement == "Excel" and r.category == RequirementCategory.PREFERRED for r in result)
    assert any(r.requirement == "Redis" and r.category == RequirementCategory.PREFERRED for r in result)


# ---------------------------------------------------------------------------
# Test 6: Empty Profile Returns Empty List Without Crashing
# ---------------------------------------------------------------------------
def test_empty_profile_returns_empty_list_without_crashing():
    """Verifies a minimal profile with no requirements produces an empty list, not an error."""
    profile = JobRequirementProfile(job_title="Test")

    result = classify_requirements(profile)

    assert result == []


# ---------------------------------------------------------------------------
# Test 7: Minimal Profile Returns Appropriately Partial List
# ---------------------------------------------------------------------------
def test_minimal_profile_returns_partial_list():
    """Verifies that when only one field is populated, only that field produces
    entries — no spurious entries for absent categories."""
    profile = JobRequirementProfile(job_title="Test", required_skills=["SQL"])

    result = classify_requirements(profile)

    assert len(result) == 1
    assert result[0].requirement == "SQL"
    assert result[0].requirement_type == RequirementType.SKILL
    assert result[0].category == RequirementCategory.MANDATORY


# ---------------------------------------------------------------------------
# Test 8: Multiple Experience Requirements Each Classified Independently
# ---------------------------------------------------------------------------
def test_multiple_experience_requirements_each_classified_independently():
    """
    Verifies general + multiple specific experience requirements (Day 1's
    Example 3 pattern) each become their own correctly-classified entry,
    including a preferred one, proving per-item category/detail independence
    (no cross-contamination between entries).
    """
    general = ExperienceRequirement(
        description="3 years overall software development experience",
        years=3.0,
        requirement_type=ExperienceRequirementType.GENERAL,
        target=None,
        is_mandatory=True,
    )
    python_exp = ExperienceRequirement(
        description="2 years Python experience",
        years=2.0,
        requirement_type=ExperienceRequirementType.SPECIFIC,
        target="Python",
        is_mandatory=True,
    )
    fastapi_exp = ExperienceRequirement(
        description="1 year FastAPI experience (nice to have)",
        years=1.0,
        requirement_type=ExperienceRequirementType.SPECIFIC,
        target="FastAPI",
        is_mandatory=False,
    )
    profile = JobRequirementProfile(
        job_title="Test",
        experience_requirements=[general, python_exp, fastapi_exp],
    )

    result = classify_requirements(profile)

    assert len(result) == 3
    assert all(r.requirement_type == RequirementType.EXPERIENCE for r in result)

    by_target = {r.source_detail.target: r for r in result}

    assert by_target[None].category == RequirementCategory.MANDATORY
    assert by_target[None].source_detail.years == 3.0

    assert by_target["Python"].category == RequirementCategory.MANDATORY
    assert by_target["Python"].source_detail.years == 2.0

    assert by_target["FastAPI"].category == RequirementCategory.PREFERRED
    assert by_target["FastAPI"].source_detail.years == 1.0


# ---------------------------------------------------------------------------
# Test 9: Domain Experience Defaults to Preferred
# ---------------------------------------------------------------------------
def test_domain_experience_defaults_to_preferred():
    """
    Locks in the documented default for domain_experience (no is_mandatory
    split exists in Day 1's schema): every entry defaults to PREFERRED.
    """
    profile = JobRequirementProfile(job_title="Test", domain_experience=["Fintech"])

    result = classify_requirements(profile)

    assert len(result) == 1
    entry = result[0]
    assert entry.requirement == "Fintech"
    assert entry.category == RequirementCategory.PREFERRED
    assert entry.requirement_type == RequirementType.DOMAIN
    assert entry.source_detail is None


# ---------------------------------------------------------------------------
# Test 10: Other Mandatory Requirement Classified as Mandatory/Other
# ---------------------------------------------------------------------------
def test_other_mandatory_requirement_classified_as_mandatory_other():
    """Verifies other_mandatory_requirements entries are always mandatory/other,
    with no keyword-based sub-classification applied."""
    profile = JobRequirementProfile(
        job_title="Test",
        other_mandatory_requirements=["Must be eligible to work in the US"],
    )

    result = classify_requirements(profile)

    assert len(result) == 1
    entry = result[0]
    assert entry.requirement == "Must be eligible to work in the US"
    assert entry.category == RequirementCategory.MANDATORY
    assert entry.requirement_type == RequirementType.OTHER
    assert entry.source_detail is None
