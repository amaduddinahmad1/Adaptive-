from typing import List

from app.schemas.candidate import CandidateProfile
from app.schemas.job import JobRequirementProfile

MAX_TECHNOLOGY_QUESTIONS = 4


def select_technology_areas(
    job_requirements: JobRequirementProfile,
    candidate_profile: CandidateProfile,
    *,
    limit: int = MAX_TECHNOLOGY_QUESTIONS,
) -> List[str]:
    """Select required technology areas the candidate claims, within the interview cap."""
    candidate_capabilities = {
        value.strip().casefold()
        for value in [
            *candidate_profile.skills,
            *candidate_profile.technologies,
            *(item.technology for item in candidate_profile.technology_specific_experience),
            *(technology for project in candidate_profile.projects for technology in project.technologies),
        ]
        if value and value.strip()
    }

    technology_years = {
        technology.casefold(): years
        for technology, years in candidate_profile.technology_experience_map.items()
    }
    required_technology_matches = []
    for index, area in enumerate(job_requirements.required_technologies):
        cleaned = area.strip()
        if not cleaned or cleaned.casefold() not in candidate_capabilities:
            continue
        required_technology_matches.append(
            (-technology_years.get(cleaned.casefold(), 0.0), index, cleaned)
        )

    selected: List[str] = [
        area
        for _, _, area in sorted(required_technology_matches)
    ][:limit]

    if len(selected) < limit:
        selected_keys = {item.casefold() for item in selected}
        for area in job_requirements.required_skills:
            cleaned = area.strip()
            if (
                cleaned
                and cleaned.casefold() in candidate_capabilities
                and cleaned.casefold() not in selected_keys
            ):
                selected.append(cleaned)
                selected_keys.add(cleaned.casefold())
            if len(selected) == limit:
                break

    return selected
