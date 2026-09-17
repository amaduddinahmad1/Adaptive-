"""JD parser post-processing: duty-shaped lines and willingness-to-learn."""
from app.schemas.job import JobRequirementProfile
from app.services.jd_intelligence.jd_parser import _postprocess_parsed_profile
from app.services.jd_intelligence.requirement_classifier import is_willingness_to_learn_requirement


def test_postprocess_moves_willingness_to_learn_to_other_and_keeps_real_skills():
    profile = JobRequirementProfile(
        job_title="AI Engineer Intern",
        required_skills=[
            "Python",
            "Machine Learning",
            "Willingness to learn new tools",
            "Collaborate with senior engineers on production ML practices",
        ],
        preferred_skills=["Eagerness to learn"],
        required_technologies=["Deep Learning", "Ability/willingness to learn"],
        preferred_technologies=["PyTorch"],
        other_mandatory_requirements=["Must be eligible to work in the US"],
    )
    processed = _postprocess_parsed_profile(profile)

    assert "Python" in processed.required_skills
    assert "Machine Learning" in processed.required_skills
    assert not any(is_willingness_to_learn_requirement(item) for item in processed.required_skills)
    assert not any(is_willingness_to_learn_requirement(item) for item in processed.preferred_skills)
    assert not any(is_willingness_to_learn_requirement(item) for item in processed.required_technologies)
    assert all(not item.lower().startswith("collaborate") for item in processed.required_skills)
    assert "Deep Learning" in processed.required_technologies
    assert "PyTorch" in processed.preferred_technologies
    assert "Must be eligible to work in the US" in processed.other_mandatory_requirements
    assert any(is_willingness_to_learn_requirement(item) for item in processed.other_mandatory_requirements)
    assert "Willingness to learn new tools" in processed.other_mandatory_requirements
