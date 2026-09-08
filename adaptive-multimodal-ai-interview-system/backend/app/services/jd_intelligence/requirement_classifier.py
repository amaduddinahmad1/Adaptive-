"""
app/services/jd_intelligence/requirement_classifier.py

Normalizes an already-parsed JobRequirementProfile into a flat list of
ClassifiedRequirement objects.

IMPORTANT — this is an enrichment/normalization step, not a second classifier.
JD parsing (jd_parser.py) already used Gemini's full-context understanding of
the JD to decide mandatory-vs-preferred (is_mandatory flags, and which of the
required_*/preferred_* lists a skill or technology was placed in). Re-deriving
that classification here from keyword heuristics on raw text would only ever
have LESS context than the original extraction and risks silently
contradicting it. So this module reads Day 1's existing classification and
restates it in one uniform shape — it does not re-classify anything from text.

Two assumptions fill gaps where Day 1's schema has no classification to read,
and they intentionally point in opposite directions for a single underlying
reason: each picks whichever default is least likely to produce a WRONG
eligibility outcome, given what is actually known vs. unknown in that case.

1. Required/preferred conflict (same skill or technology name appears in both
   the required_* and preferred_* lists — a Day 1 data-quality artifact, not a
   genuine JD statement of "either/or"): mandatory wins. Known: the item is
   REQUIRED somewhere in the JD. Unknown: which list is the mistake. Treating
   it as mandatory is the conservative choice — it never lets a candidate
   falsely clear a bar that might be mandatory. Silently downgrading to
   preferred risks passing an unqualified candidate.

2. domain_experience (Day 1's schema has no is_mandatory split for these at
   all — a known Day 1 limitation, see the comment above JobRequirementProfile
   in job.py): defaults to PREFERRED. Known: the JD mentions this domain.
   Unknown: whether it's a hard gate or a plus (JDs typically phrase domain
   exposure as the latter, e.g. "ideally fintech"). Defaulting to the LESS
   strict category is the conservative choice here — it never lets missing
   domain exposure wrongly disqualify a candidate over something the JD never
   actually said was mandatory.

In both cases: pick the default that costs the least when we're wrong, given
which direction of error is unknown-but-bounded and which is unknown-and-risky.
"""

from typing import List

from app.schemas.job import (
    ClassifiedRequirement,
    JobRequirementProfile,
    RequirementCategory,
    RequirementType,
)


def _format_education_requirement(degree_level: str, field_of_study: str | None) -> str:
    """Builds human-readable text for an education requirement entry."""
    if field_of_study:
        return f"{degree_level} in {field_of_study}"
    return degree_level


def _classify_required_preferred_list(
    required: List[str],
    preferred: List[str],
    requirement_type: RequirementType,
) -> List[ClassifiedRequirement]:
    """
    Classifies a required_*/preferred_* pair of plain-string lists (skills or
    technologies) into ClassifiedRequirement entries.

    Conflict resolution: if the same name (case-insensitive) appears in both
    lists, it is emitted once as MANDATORY and the preferred duplicate is
    skipped. See module docstring, point 1, for why mandatory wins.
    """
    classified: List[ClassifiedRequirement] = []

    required_lower = {item.lower() for item in required}
    for item in required:
        classified.append(
            ClassifiedRequirement(
                requirement=item,
                category=RequirementCategory.MANDATORY,
                requirement_type=requirement_type,
            )
        )

    for item in preferred:
        if item.lower() in required_lower:
            # Conflict: item is listed as both required and preferred.
            # Mandatory wins — already emitted above, so skip the duplicate.
            continue
        classified.append(
            ClassifiedRequirement(
                requirement=item,
                category=RequirementCategory.PREFERRED,
                requirement_type=requirement_type,
            )
        )

    return classified


def classify_requirements(profile: JobRequirementProfile) -> List[ClassifiedRequirement]:
    """
    Flattens a JobRequirementProfile into a uniform list of ClassifiedRequirement
    entries, reading mandatory/preferred status from Day 1's existing
    classification rather than re-deriving it.

    Args:
        profile: A validated JobRequirementProfile from JD parsing.

    Returns:
        A flat list of ClassifiedRequirement objects covering every requirement
        in the profile. Order follows the profile's field order; within a field,
        source order is preserved.
    """
    classified: List[ClassifiedRequirement] = []

    for exp in profile.experience_requirements:
        classified.append(
            ClassifiedRequirement(
                requirement=exp.description,
                category=RequirementCategory.MANDATORY if exp.is_mandatory else RequirementCategory.PREFERRED,
                requirement_type=RequirementType.EXPERIENCE,
                source_detail=exp,
            )
        )

    classified.extend(
        _classify_required_preferred_list(
            profile.required_skills, profile.preferred_skills, RequirementType.SKILL
        )
    )
    classified.extend(
        _classify_required_preferred_list(
            profile.required_technologies, profile.preferred_technologies, RequirementType.TECHNOLOGY
        )
    )

    for edu in profile.education_requirements:
        classified.append(
            ClassifiedRequirement(
                requirement=_format_education_requirement(edu.degree_level, edu.field_of_study),
                category=RequirementCategory.MANDATORY if edu.is_mandatory else RequirementCategory.PREFERRED,
                requirement_type=RequirementType.EDUCATION,
                source_detail=edu,
            )
        )

    for cert in profile.certifications:
        classified.append(
            ClassifiedRequirement(
                requirement=cert.name,
                category=RequirementCategory.MANDATORY if cert.is_mandatory else RequirementCategory.PREFERRED,
                requirement_type=RequirementType.CERTIFICATION,
                source_detail=cert,
            )
        )

    # domain_experience has no is_mandatory split in Day 1's schema.
    # Defaults to PREFERRED — see module docstring, point 2, for why.
    for domain in profile.domain_experience:
        classified.append(
            ClassifiedRequirement(
                requirement=domain,
                category=RequirementCategory.PREFERRED,
                requirement_type=RequirementType.DOMAIN,
            )
        )

    # other_mandatory_requirements is mandatory by definition (its own field
    # name), with no finer sub-categorization today — kept literal as "other"
    # per scope: no keyword-based sub-classification is applied here.
    for other in profile.other_mandatory_requirements:
        classified.append(
            ClassifiedRequirement(
                requirement=other,
                category=RequirementCategory.MANDATORY,
                requirement_type=RequirementType.OTHER,
            )
        )

    return classified
