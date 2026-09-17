"""Requirement classifier: willingness-to-learn and conceptual skill/tech dedupe."""
from app.schemas.job import JobRequirementProfile, RequirementCategory, RequirementType
from app.services.eligibility.term_equivalence import skill_aliases
from app.services.jd_intelligence.requirement_classifier import (
    classify_requirements,
    is_willingness_to_learn_requirement,
)


def test_willingness_phrases_are_other_not_mandatory_skills():
    phrases = [
        "Willingness to learn",
        "Willingness to learn new tools",
        "Eagerness to learn",
        "Ability/willingness to learn",
        "Ability to learn",
    ]
    for phrase in phrases:
        assert is_willingness_to_learn_requirement(phrase) is True

    assert is_willingness_to_learn_requirement("Machine Learning") is False
    assert is_willingness_to_learn_requirement("Deep Learning") is False
    assert is_willingness_to_learn_requirement("Willingness to work on-call rotations") is False

    profile = JobRequirementProfile(
        job_title="Intern",
        required_skills=["Python", "Willingness to learn new tools"],
        required_technologies=["Eagerness to learn"],
        preferred_skills=["Ability/willingness to learn"],
    )
    classified = classify_requirements(profile)
    learn_rows = [row for row in classified if is_willingness_to_learn_requirement(row.requirement)]
    assert learn_rows
    assert all(row.requirement_type == RequirementType.OTHER for row in learn_rows)
    assert not any(
        row.requirement_type in (RequirementType.SKILL, RequirementType.TECHNOLOGY)
        and is_willingness_to_learn_requirement(row.requirement)
        for row in classified
    )
    python = next(row for row in classified if row.requirement == "Python")
    assert python.requirement_type == RequirementType.SKILL
    assert python.category == RequirementCategory.MANDATORY


def test_machine_learning_not_duplicated_as_skill_and_technology_gates():
    profile = JobRequirementProfile(
        job_title="ML Intern",
        required_skills=["Machine Learning", "Python"],
        required_technologies=["ML", "Machine Learning", "Python", "PyTorch"],
        preferred_technologies=["Deep Learning"],
    )
    classified = classify_requirements(profile)
    ml_mandatory = [
        row
        for row in classified
        if row.category == RequirementCategory.MANDATORY
        and row.requirement_type in (RequirementType.SKILL, RequirementType.TECHNOLOGY)
        and "machine learning" in skill_aliases(row.requirement)
    ]
    assert len(ml_mandatory) == 1
    assert ml_mandatory[0].requirement_type == RequirementType.SKILL

    python_mandatory = [
        row
        for row in classified
        if row.category == RequirementCategory.MANDATORY and row.requirement.strip().lower() == "python"
    ]
    assert len(python_mandatory) == 2

    pytorch = next(row for row in classified if row.requirement == "PyTorch")
    assert pytorch.requirement_type == RequirementType.TECHNOLOGY
    assert pytorch.category == RequirementCategory.MANDATORY
