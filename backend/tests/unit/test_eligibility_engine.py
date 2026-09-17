"""Regression tests for eligibility matching, aliases, project evidence, and hard gates."""
from __future__ import annotations

import json

from app.schemas.candidate import CandidateProfile, Project, WorkExperience
from app.schemas.job import (
    JobRequirementProfile,
    RequirementCategory,
    RequirementType,
)
from app.services.eligibility.eligibility_engine import (
    ApplicationDetails,
    MatchStatus,
    RecruiterConstraints,
    check_eligibility,
)
from app.services.eligibility.term_equivalence import alias_in_text, skill_aliases
from app.services.jd_intelligence.requirement_classifier import (
    classify_requirements,
    is_willingness_to_learn_requirement,
)


def _details() -> ApplicationDetails:
    return ApplicationDetails(joining_availability="immediate", salary_expectation=50000)


def _constraints() -> RecruiterConstraints:
    return RecruiterConstraints()


def _run(job: JobRequirementProfile, candidate: CandidateProfile, *, provider=None):
    return check_eligibility(
        job,
        classify_requirements(job),
        candidate,
        _details(),
        _constraints(),
        provider=provider,
    )


def _status_for(result, name: str) -> str | None:
    needle = name.strip().lower()
    for row in result.requirement_results:
        if row.requirement.requirement.strip().lower() == needle:
            return row.status.value
    return None


def _mandatory_skill_tech(result):
    return [
        row
        for row in result.requirement_results
        if row.requirement.category == RequirementCategory.MANDATORY
        and row.requirement.requirement_type in (RequirementType.SKILL, RequirementType.TECHNOLOGY)
    ]


class ScriptedSkillProvider:
    """Test double for judge_unmatched_mandatory_skills / generate_structured."""

    def __init__(self, matched=True):
        self.matched = matched
        self.calls = 0
        self.last_prompt = ""

    def generate_structured(self, *, prompt, system_instruction, response_schema, temperature=None):
        self.calls += 1
        self.last_prompt = prompt
        judgments = []
        for line in prompt.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                req = stripped[2:].strip()
                matched = self.matched[req] if isinstance(self.matched, dict) else bool(self.matched)
                judgments.append(
                    {
                        "requirement": req,
                        "matched": matched,
                        "reason": (
                            f"Profile evidence supports {req}."
                            if matched
                            else f"No concrete evidence for {req}."
                        ),
                    }
                )
        return json.dumps({"judgments": judgments})


def test_ai_ml_satisfies_mandatory_machine_learning():
    job = JobRequirementProfile(job_title="ML Intern", required_skills=["Machine Learning"])
    candidate = CandidateProfile(skills=["AI/ML", "Python"])
    result = _run(job, candidate)
    assert _status_for(result, "Machine Learning") == MatchStatus.MET.value
    assert result.overall_eligible is True


def test_html_does_not_satisfy_machine_learning():
    job = JobRequirementProfile(job_title="ML Intern", required_skills=["Machine Learning", "ML"])
    candidate = CandidateProfile(skills=["HTML", "XML"])
    result = _run(job, candidate)
    assert result.overall_eligible is False
    assert any(row.status == MatchStatus.NOT_MET_MANDATORY for row in _mandatory_skill_tech(result))
    assert alias_in_text("ml", "HTML") is False


def test_dl_satisfies_mandatory_deep_learning():
    job = JobRequirementProfile(job_title="DL Intern", required_skills=["Deep Learning"])
    candidate = CandidateProfile(skills=["DL", "Python"])
    result = _run(job, candidate)
    assert _status_for(result, "Deep Learning") == MatchStatus.MET.value
    assert result.overall_eligible is True


def test_project_description_dl_satisfies_deep_learning():
    job = JobRequirementProfile(job_title="DL Intern", required_skills=["Deep Learning"])
    candidate = CandidateProfile(
        skills=["Python"],
        projects=[
            Project(
                name="Vision pipeline",
                description="Trained DL models for object detection.",
                technologies=["YOLO"],
            )
        ],
    )
    result = _run(job, candidate)
    assert _status_for(result, "Deep Learning") == MatchStatus.MET.value
    assert result.overall_eligible is True


def test_rag_alias_matches_retrieval_augmented_generation():
    job = JobRequirementProfile(
        job_title="AI Intern",
        required_skills=["RAG (Retrieval-Augmented Generation)"],
    )
    candidate = CandidateProfile(skills=["RAG"])
    result = _run(job, candidate)
    assert _status_for(result, "RAG (Retrieval-Augmented Generation)") == MatchStatus.MET.value
    assert result.overall_eligible is True


def test_rag_project_name_satisfies_rag_requirement():
    job = JobRequirementProfile(
        job_title="AI Intern",
        required_skills=["RAG (Retrieval-Augmented Generation)"],
    )
    candidate = CandidateProfile(
        skills=["Python"],
        projects=[
            Project(
                name="RAG-based PDF Chatbot",
                description="Answers questions over PDFs.",
                technologies=[],
            )
        ],
    )
    result = _run(job, candidate)
    assert result.overall_eligible is True


def test_willingness_to_learn_is_not_a_blocking_mandatory_skill():
    job = JobRequirementProfile(
        job_title="Intern",
        required_skills=["Python", "Willingness to learn new tools"],
    )
    candidate = CandidateProfile(skills=["Python"])
    classified = classify_requirements(job)
    willingness = [row for row in classified if is_willingness_to_learn_requirement(row.requirement)]
    assert willingness
    assert all(row.requirement_type == RequirementType.OTHER for row in willingness)
    result = _run(job, candidate)
    assert result.overall_eligible is True
    assert all(row.status != MatchStatus.NOT_MET_MANDATORY for row in result.requirement_results)


def test_preferred_missing_frameworks_do_not_block_eligibility():
    job = JobRequirementProfile(
        job_title="AI Intern",
        required_skills=["Python"],
        preferred_skills=["Git"],
        preferred_technologies=["PyTorch", "TensorFlow", "PostgreSQL"],
    )
    candidate = CandidateProfile(skills=["Python"])
    result = _run(job, candidate)
    assert result.overall_eligible is True
    assert _status_for(result, "PyTorch") == MatchStatus.NOT_FOUND_PREFERRED.value
    assert _status_for(result, "TensorFlow") == MatchStatus.NOT_FOUND_PREFERRED.value
    assert _status_for(result, "PostgreSQL") == MatchStatus.NOT_FOUND_PREFERRED.value
    assert _status_for(result, "Git") == MatchStatus.NOT_FOUND_PREFERRED.value


def test_duplicate_machine_learning_skill_and_technology_is_a_single_gate():
    job = JobRequirementProfile(
        job_title="ML Intern",
        required_skills=["Machine Learning"],
        required_technologies=["Machine Learning", "ML", "Python"],
    )
    classified = classify_requirements(job)
    ml_gates = [
        row
        for row in classified
        if row.category == RequirementCategory.MANDATORY
        and row.requirement_type in (RequirementType.SKILL, RequirementType.TECHNOLOGY)
        and ("machine learning" in skill_aliases(row.requirement))
    ]
    assert len(ml_gates) == 1
    python_gates = [
        row
        for row in classified
        if row.category == RequirementCategory.MANDATORY
        and row.requirement.strip().lower() == "python"
    ]
    assert len(python_gates) == 1

    candidate = CandidateProfile(skills=["AI/ML", "Python"])
    result = _run(job, candidate)
    assert result.overall_eligible is True
    ml_failures = [
        row
        for row in _mandatory_skill_tech(result)
        if row.status == MatchStatus.NOT_MET_MANDATORY and "machine learning" in skill_aliases(row.requirement.requirement)
    ]
    assert ml_failures == []


def test_project_evidence_can_satisfy_via_semantic_matcher():
    job = JobRequirementProfile(
        job_title="AI Engineer Intern",
        required_skills=["Deep Learning", "Generative AI"],
    )
    candidate = CandidateProfile(
        skills=["Python", "YOLO", "Computer Vision", "Transformers", "LangChain"],
        projects=[
            Project(
                name="RAG-based PDF Chatbot",
                description="Llama + LangChain retrieval-augmented generation chatbot.",
                technologies=["LangChain", "LLM", "Llama", "RAG"],
            )
        ],
    )
    provider = ScriptedSkillProvider(matched=True)
    result = _run(job, candidate, provider=provider)
    assert provider.calls == 1
    assert "RAG-based PDF Chatbot" in provider.last_prompt
    assert "LangChain" in provider.last_prompt
    assert result.overall_eligible is True
    assert any(row.status == MatchStatus.MET_BY_INFERENCE for row in result.requirement_results)


def test_missing_mandatory_skill_still_makes_ineligible():
    job = JobRequirementProfile(job_title="COBOL Engineer", required_skills=["COBOL"])
    candidate = CandidateProfile(skills=["Python", "AI/ML"])
    result = _run(job, candidate)
    assert result.overall_eligible is False
    assert _status_for(result, "COBOL") == MatchStatus.NOT_MET_MANDATORY.value

    provider = ScriptedSkillProvider(matched=False)
    result_with_provider = _run(job, candidate, provider=provider)
    assert result_with_provider.overall_eligible is False
    assert _status_for(result_with_provider, "COBOL") == MatchStatus.NOT_MET_MANDATORY.value


def test_job_title_alone_is_not_deterministic_proof_of_a_skill():
    job = JobRequirementProfile(job_title="ML Intern", required_skills=["Machine Learning"])
    candidate = CandidateProfile(
        work_experience=[WorkExperience(position="AI/ML Engineer", description=None)]
    )
    result = _run(job, candidate)
    assert result.overall_eligible is False
    assert _status_for(result, "Machine Learning") == MatchStatus.NOT_MET_MANDATORY.value


def test_danish_style_profile_is_not_rejected_for_literal_or_soft_mismatches():
    job = JobRequirementProfile(
        job_title="AI Engineer Intern",
        required_skills=[
            "Python",
            "Machine Learning",
            "Deep Learning",
            "Willingness to learn new tools",
        ],
        preferred_skills=["Git"],
        required_technologies=[
            "Python",
            "Machine Learning",
            "Deep Learning",
            "Generative AI/RAG",
        ],
        preferred_technologies=["PyTorch", "TensorFlow", "PostgreSQL"],
    )
    candidate = CandidateProfile(
        skills=[
            "Python",
            "AI/ML",
            "YOLO",
            "Computer Vision",
            "Transformers",
            "LangChain",
            "RAG",
        ],
        technologies=["Python", "YOLO", "LangChain"],
        projects=[
            Project(
                name="RAG-based PDF Chatbot",
                description="Retrieval-Augmented Generation chatbot using LangChain and Llama.",
                technologies=["LangChain", "RAG", "LLM", "Llama"],
            ),
            Project(
                name="AI Voice Calling Agent",
                description="Voice agent built with an LLM.",
                technologies=["LLM"],
            ),
            Project(
                name="AI Mock Interviewer",
                description="Mock interviewer agent.",
                technologies=["LLM"],
            ),
        ],
        work_experience=[
            WorkExperience(
                position="AI/ML Engineer",
                company="Example",
                description="Built computer vision systems with YOLO and Transformers.",
            )
        ],
        education=["BS Information Technology"],
    )

    classified = classify_requirements(job)
    willingness = [row for row in classified if is_willingness_to_learn_requirement(row.requirement)]
    assert willingness
    assert all(row.requirement_type == RequirementType.OTHER for row in willingness)

    ml_gates = [
        row
        for row in classified
        if row.category == RequirementCategory.MANDATORY
        and row.requirement_type in (RequirementType.SKILL, RequirementType.TECHNOLOGY)
        and "machine learning" in skill_aliases(row.requirement)
    ]
    dl_gates = [
        row
        for row in classified
        if row.category == RequirementCategory.MANDATORY
        and row.requirement_type in (RequirementType.SKILL, RequirementType.TECHNOLOGY)
        and "deep learning" in skill_aliases(row.requirement)
    ]
    assert len(ml_gates) == 1
    assert len(dl_gates) == 1

    provider = ScriptedSkillProvider(matched=True)
    result = _run(job, candidate, provider=provider)
    assert result.overall_eligible is True
    assert _status_for(result, "Python") == MatchStatus.MET.value
    assert _status_for(result, "Machine Learning") == MatchStatus.MET.value
    assert _status_for(result, "Git") == MatchStatus.NOT_FOUND_PREFERRED.value
    assert _status_for(result, "PyTorch") == MatchStatus.NOT_FOUND_PREFERRED.value
    assert _status_for(result, "TensorFlow") == MatchStatus.NOT_FOUND_PREFERRED.value
    assert _status_for(result, "PostgreSQL") == MatchStatus.NOT_FOUND_PREFERRED.value
    assert all(row.status != MatchStatus.NOT_MET_MANDATORY for row in result.requirement_results)
