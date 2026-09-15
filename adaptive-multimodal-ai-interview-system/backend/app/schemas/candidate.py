from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# Known follow-ups:
# Normalize free-text start_date/end_date values before calculating durations.
# The "present" sentinel represents an ongoing role; None represents a missing date.
# Replace the deprecated `import fitz` usage in the PDF extractor with
# `import pymupdf` in a future cleanup.
# Technology-specific durations are LLM-estimated and may assign inconsistent
# precision across tools used within the same role or across multiple roles;
# a dedicated duration-aggregation engine should validate or recompute these
# values before they are used in eligibility scoring.


class WorkExperience(BaseModel):
    position: str
    company: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class Project(BaseModel):
    name: str
    description: str
    technologies: List[str] = Field(default_factory=list)


class TechnologyExperience(BaseModel):
    technology: str
    years: float = Field(ge=0.0)


class CandidateProfile(BaseModel):
    skills: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    projects: List[Project] = Field(default_factory=list)
    work_experience: List[WorkExperience] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    achievements: List[str] = Field(default_factory=list)
    technology_specific_experience: List[TechnologyExperience] = Field(
        default_factory=list
    )

    @property
    def technology_experience_map(self) -> Dict[str, float]:
        return {
            item.technology: item.years
            for item in self.technology_specific_experience
        }
