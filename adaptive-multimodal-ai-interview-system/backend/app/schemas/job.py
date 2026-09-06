"""
app/schemas/job.py

Pydantic v2 models defining the structured Job Requirement Profile extracted from JDs.
Directly maps to the 10 core qualification criteria for eligibility evaluation.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

# Known limitations deferred for the eligibility-engine design review:
# domain_experience does not distinguish mandatory from preferred exposure, and
# education_requirements cannot represent "or equivalent practical experience".


class ExperienceRequirementType(str, Enum):
    """Classifies an experience requirement as general or specific."""
    GENERAL = "general"    # General software engineering / overall professional tenure
    SPECIFIC = "specific"  # Bound to a specific technology, framework, language, or domain


class ExperienceRequirement(BaseModel):
    """
    Individual experience requirement extracted from the JD.
    Serves as the single source of truth for both general tenure and specific tech requirements.
    """
    description: str = Field(
        ...,
        description="Original text from JD (e.g. 'Minimum 3 years professional software development experience' or '2 years Python experience')"
    )
    years: float = Field(
        ...,
        ge=0.0,
        description="Number of years required (e.g., 3.0)"
    )
    requirement_type: ExperienceRequirementType = Field(
        ...,
        description="'general' for overall tenure, 'specific' for experience bound to a named technology or domain"
    )
    target: Optional[str] = Field(
        None,
        description="Target technology or domain if specific (e.g., 'Python', 'FastAPI'); null if general"
    )
    is_mandatory: bool = Field(
        default=True,
        description="Whether this experience requirement is mandatory (True) or preferred/nice-to-have (False)"
    )


class EducationRequirement(BaseModel):
    """Educational qualifications specified in the JD."""
    degree_level: str = Field(
        ...,
        description="Degree level required (e.g., 'Bachelor\\'s', 'Master\\'s', 'PhD', 'Any')"
    )
    field_of_study: Optional[str] = Field(
        None,
        description="Discipline or major (e.g., 'Computer Science', 'Software Engineering', or null if open)"
    )
    is_mandatory: bool = Field(
        default=True,
        description="True if mandatory, False if preferred"
    )


class CertificationRequirement(BaseModel):
    """Professional certifications specified in the JD."""
    name: str = Field(
        ...,
        description="Certification title (e.g., 'AWS Certified Solutions Architect')"
    )
    is_mandatory: bool = Field(
        default=False,
        description="True if mandatory, False if preferred"
    )


class JobRequirementProfile(BaseModel):
    """
    Structured representation of a parsed Job Description.
    Maps directly to the 10 required qualification outputs.
    """
    # 1. Job Title
    job_title: str = Field(
        ...,
        description="Official job title (e.g. 'Senior Python Backend Engineer')"
    )

    # 2 & 3. Minimum General Experience + Specific Experience Requirements
    # (Single source of truth: general entries have requirement_type='general', specific have requirement_type='specific')
    experience_requirements: List[ExperienceRequirement] = Field(
        default_factory=list,
        description="All experience requirements, covering general overall tenure and specific technology/domain requirements"
    )

    # 4. Required Skills
    required_skills: List[str] = Field(
        default_factory=list,
        description="Mandatory skills and proficiencies required for the role"
    )

    # 5. Preferred Skills
    preferred_skills: List[str] = Field(
        default_factory=list,
        description="Preferred or nice-to-have skills"
    )

    # 6. Required Technologies
    required_technologies: List[str] = Field(
        default_factory=list,
        description="Mandatory languages, frameworks, databases, and tools (e.g., 'Python', 'FastAPI', 'PostgreSQL')"
    )

    # Preferred Technologies (classified under preferred requirements)
    preferred_technologies: List[str] = Field(
        default_factory=list,
        description="Preferred or nice-to-have technologies, libraries, or tools (e.g., 'Docker', 'Redis')"
    )

    # 7. Education Requirements
    education_requirements: List[EducationRequirement] = Field(
        default_factory=list,
        description="Educational criteria (mandatory or preferred)"
    )

    # 8. Certifications
    certifications: List[CertificationRequirement] = Field(
        default_factory=list,
        description="Certifications listed in the JD (mandatory or preferred)"
    )

    # 9. Domain Experience
    domain_experience: List[str] = Field(
        default_factory=list,
        description="Industry or domain exposure requirements (e.g., 'Fintech', 'Healthcare', 'E-commerce')"
    )

    # 10. Other Mandatory Requirements
    other_mandatory_requirements: List[str] = Field(
        default_factory=list,
        description="Any additional non-negotiable requirements (e.g., 'Must be eligible to work in the US')"
    )
