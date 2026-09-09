"""
app/services/eligibility/eligibility_engine.py

Combines experience matching (Day 4), classified requirement matching
(Day 3), and recruiter-form inputs (joining availability, salary) into a
single eligibility decision for a candidate against a job.

Two structured, non-LLM-parsed inputs are introduced here — ApplicationDetails
(candidate-side) and RecruiterConstraints (recruiter-side) — because salary
and availability are recruiter-form data, not something that should ever be
parsed from JD text. JobRequirementProfile deliberately has no salary or
availability fields; reintroducing them there would undo that Day 1 scoping
decision.

check_eligibility() takes both jd_profile and classified_reqs, not just the
latter, for two reasons: (1) match_all_experience_requirements requires a
JobRequirementProfile, and is reused here rather than hand-rolled; (2)
ExperienceMatchResult does not carry is_mandatory forward, so recovering it
requires pairing each result with its source ExperienceRequirement via
jd_profile.experience_requirements. classified_reqs remains the sole source
for every non-experience requirement type (skill/technology/education/
certification/domain/other), exactly as Day 3 designed it to be.

MatchStatus.MANUAL_REVIEW_REQUIRED never blocks overall_eligible, even for a
mandatory requirement. It is used when there is genuinely no reliable way to
verify a requirement — domain_experience and other_mandatory_requirements
have no corresponding CandidateProfile field at all, and a candidate's
free-text joining_availability may not be parseable into a number of days.
In all these cases, fabricating a pass or a fail would be worse than
surfacing the item for a human to check (see format_eligibility_report).
"""

import re
from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from app.schemas.candidate import CandidateProfile
from app.schemas.job import (
    ClassifiedRequirement,
    ExperienceRequirementType,
    JobRequirementProfile,
    RequirementCategory,
    RequirementType,
)
from app.services.eligibility.experience_matcher import (
    ExperienceMatchResult,
    match_all_experience_requirements,
)


class ApplicationDetails(BaseModel):
    """Candidate-side structured input, not LLM-parsed."""
    joining_availability: str
    salary_expectation: float


class RecruiterConstraints(BaseModel):
    """Recruiter-side structured input, not LLM-parsed. None means no constraint stated."""
    max_notice_period_days: Optional[int] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None


class MatchStatus(str, Enum):
    MET = "met"
    NOT_MET_MANDATORY = "not_met_mandatory"
    NOT_FOUND_PREFERRED = "not_found_preferred"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class ExperienceEligibilityResult(BaseModel):
    """Composes Day 4's ExperienceMatchResult with the mandatory/preferred verdict it doesn't carry."""
    match: ExperienceMatchResult
    is_mandatory: bool
    status: MatchStatus


class RequirementMatchResult(BaseModel):
    """Composes a Day 3 ClassifiedRequirement with its match verdict."""
    requirement: ClassifiedRequirement
    status: MatchStatus


class SalaryEligibilityResult(BaseModel):
    candidate_salary_expectation: float
    salary_min: Optional[float]
    salary_max: Optional[float]
    status: MatchStatus


class JoiningAvailabilityEligibilityResult(BaseModel):
    candidate_joining_availability: str
    max_notice_period_days: Optional[int]
    status: MatchStatus


class EligibilityResult(BaseModel):
    experience_results: List[ExperienceEligibilityResult]
    requirement_results: List[RequirementMatchResult]
    joining_availability_result: JoiningAvailabilityEligibilityResult
    salary_result: SalaryEligibilityResult
    overall_eligible: bool


_IMMEDIATE_KEYWORDS = ("immediate", "immediately", "asap", "right away")

_NOTICE_UNIT_TO_DAYS = {
    "day": 1,
    "days": 1,
    "week": 7,
    "weeks": 7,
    "month": 30,
    "months": 30,
}

_NOTICE_PERIOD_PATTERN = re.compile(r"(\d+)\s*(day|days|week|weeks|month|months)\b")


def _parse_notice_period_days(text: str) -> Optional[int]:
    """
    Parses free-text joining-availability into a number of notice days, or
    None if it can't be confidently determined.

    - "immediate"/"immediately"/"asap"/"right away" -> 0.
    - "<number> day(s)/week(s)/month(s)" -> converted to days.
    - A bare number with no unit (e.g. "30") is deliberately treated as
      unparseable rather than guessed — it could mean days, weeks, or
      something else, and guessing would fabricate data we don't have.
    - Anything else unrecognized -> None.
    """
    normalized = text.strip().lower()
    if not normalized:
        return None

    if any(keyword in normalized for keyword in _IMMEDIATE_KEYWORDS):
        return 0

    match = _NOTICE_PERIOD_PATTERN.search(normalized)
    if match:
        quantity = int(match.group(1))
        unit = match.group(2)
        return quantity * _NOTICE_UNIT_TO_DAYS[unit]

    return None


def _case_insensitive_exact_match(target: str, candidates: List[str]) -> bool:
    """Exact match after casing/whitespace normalization — for short canonical names (skills, technologies)."""
    normalized_target = target.strip().lower()
    return any(item.strip().lower() == normalized_target for item in candidates)


def _case_insensitive_substring_match(needle: str, haystacks: List[str]) -> bool:
    """Substring containment after normalization — for longer descriptive phrases (certifications, education)."""
    normalized_needle = needle.strip().lower()
    return any(normalized_needle in item.strip().lower() for item in haystacks)


def _match_classified_requirement(requirement: ClassifiedRequirement, candidate: CandidateProfile) -> MatchStatus:
    """
    Matches a single non-experience ClassifiedRequirement against a candidate.

    DOMAIN and OTHER always return MANUAL_REVIEW_REQUIRED: CandidateProfile
    has no field representing industry/domain background or things like work
    authorization, so there is nothing to check them against.

    No fallback branch exists for an unhandled requirement_type — if one is
    ever added without updating this function, `found` stays unbound and a
    NameError (or, if refactored, a Pydantic validation error on a None
    status) surfaces immediately rather than silently misclassifying.
    """
    if requirement.requirement_type == RequirementType.SKILL:
        found = _case_insensitive_exact_match(requirement.requirement, candidate.skills)
    elif requirement.requirement_type == RequirementType.TECHNOLOGY:
        found = _case_insensitive_exact_match(requirement.requirement, candidate.technologies)
    elif requirement.requirement_type == RequirementType.CERTIFICATION:
        found = _case_insensitive_substring_match(requirement.requirement, candidate.certifications)
    elif requirement.requirement_type == RequirementType.EDUCATION:
        degree_level = requirement.source_detail.degree_level if requirement.source_detail else requirement.requirement
        found = _case_insensitive_substring_match(degree_level, candidate.education)
    elif requirement.requirement_type in (RequirementType.DOMAIN, RequirementType.OTHER):
        return MatchStatus.MANUAL_REVIEW_REQUIRED

    if found:
        return MatchStatus.MET
    return MatchStatus.NOT_MET_MANDATORY if requirement.category == RequirementCategory.MANDATORY else MatchStatus.NOT_FOUND_PREFERRED


def _check_joining_availability(
    application: ApplicationDetails,
    constraints: RecruiterConstraints,
) -> JoiningAvailabilityEligibilityResult:
    if constraints.max_notice_period_days is None:
        status = MatchStatus.MET
    else:
        parsed_days = _parse_notice_period_days(application.joining_availability)
        if parsed_days is None:
            status = MatchStatus.MANUAL_REVIEW_REQUIRED
        elif parsed_days <= constraints.max_notice_period_days:
            status = MatchStatus.MET
        else:
            status = MatchStatus.NOT_MET_MANDATORY

    return JoiningAvailabilityEligibilityResult(
        candidate_joining_availability=application.joining_availability,
        max_notice_period_days=constraints.max_notice_period_days,
        status=status,
    )


def _check_salary(
    application: ApplicationDetails,
    constraints: RecruiterConstraints,
) -> SalaryEligibilityResult:
    violates_min = constraints.salary_min is not None and application.salary_expectation < constraints.salary_min
    violates_max = constraints.salary_max is not None and application.salary_expectation > constraints.salary_max
    status = MatchStatus.NOT_MET_MANDATORY if (violates_min or violates_max) else MatchStatus.MET

    return SalaryEligibilityResult(
        candidate_salary_expectation=application.salary_expectation,
        salary_min=constraints.salary_min,
        salary_max=constraints.salary_max,
        status=status,
    )


def check_eligibility(
    jd_profile: JobRequirementProfile,
    classified_reqs: List[ClassifiedRequirement],
    candidate: CandidateProfile,
    application: ApplicationDetails,
    constraints: RecruiterConstraints,
    *,
    today: Optional[date] = None,
) -> EligibilityResult:
    """
    Evaluates a candidate's eligibility for a job, combining experience,
    classified requirements, joining availability, and salary.

    overall_eligible is False if and only if some check's status is
    NOT_MET_MANDATORY. MANUAL_REVIEW_REQUIRED never blocks eligibility on its
    own, even for a mandatory requirement — see module docstring.
    """
    experience_matches = match_all_experience_requirements(jd_profile, candidate, today=today)
    assert len(experience_matches) == len(jd_profile.experience_requirements), (
        f"match_all_experience_requirements returned {len(experience_matches)} results for "
        f"{len(jd_profile.experience_requirements)} requirements — cannot safely pair "
        "mandatory flags with match results."
    )

    experience_results = [
        ExperienceEligibilityResult(
            match=match,
            is_mandatory=requirement.is_mandatory,
            status=(
                MatchStatus.MET if match.met
                else MatchStatus.NOT_MET_MANDATORY if requirement.is_mandatory
                else MatchStatus.NOT_FOUND_PREFERRED
            ),
        )
        for requirement, match in zip(jd_profile.experience_requirements, experience_matches)
    ]

    requirement_results = [
        RequirementMatchResult(requirement=req, status=_match_classified_requirement(req, candidate))
        for req in classified_reqs
        if req.requirement_type != RequirementType.EXPERIENCE
    ]

    joining_availability_result = _check_joining_availability(application, constraints)
    salary_result = _check_salary(application, constraints)

    overall_eligible = not any(
        result.status == MatchStatus.NOT_MET_MANDATORY
        for result in (*experience_results, *requirement_results, joining_availability_result, salary_result)
    )

    return EligibilityResult(
        experience_results=experience_results,
        requirement_results=requirement_results,
        joining_availability_result=joining_availability_result,
        salary_result=salary_result,
        overall_eligible=overall_eligible,
    )


_STATUS_LABELS = {
    MatchStatus.MET: "MET",
    MatchStatus.NOT_MET_MANDATORY: "NOT MET",
    MatchStatus.NOT_FOUND_PREFERRED: "NOT FOUND - Preferred",
    MatchStatus.MANUAL_REVIEW_REQUIRED: "MANUAL REVIEW REQUIRED",
}


def _experience_label(exp_result: ExperienceEligibilityResult) -> str:
    if exp_result.match.requirement_type == ExperienceRequirementType.GENERAL:
        return "Overall Experience"
    return f"{exp_result.match.target} Experience"


def _format_joining_availability_line(result: JoiningAvailabilityEligibilityResult) -> Optional[str]:
    """None (no line) when the recruiter stated no notice-period constraint — nothing worth reporting."""
    if result.max_notice_period_days is None:
        return None
    return (
        f"Joining Availability: {_STATUS_LABELS[result.status]} "
        f"({result.candidate_joining_availability}, limit {result.max_notice_period_days} days)"
    )


def _format_salary_line(result: SalaryEligibilityResult) -> Optional[str]:
    """None (no line) when the recruiter stated no salary constraint — nothing worth reporting."""
    if result.salary_min is None and result.salary_max is None:
        return None

    expectation = f"${result.candidate_salary_expectation:,.0f}"
    if result.salary_min is not None and result.salary_max is not None:
        range_text = f"range ${result.salary_min:,.0f}-${result.salary_max:,.0f}"
    elif result.salary_max is not None:
        range_text = f"max ${result.salary_max:,.0f}"
    else:
        range_text = f"min ${result.salary_min:,.0f}"

    return f"Salary Expectation: {_STATUS_LABELS[result.status]} ({expectation}, {range_text})"


def format_eligibility_report(result: EligibilityResult) -> str:
    """
    Renders an EligibilityResult as a human-readable report for recruiter
    display. This is the display layer only — downstream code/APIs should
    consume the structured EligibilityResult directly, never parse this string.

    DOMAIN and OTHER requirement_type entries are always MANUAL_REVIEW_REQUIRED
    (see _match_classified_requirement) and are never rendered as ordinary
    MET/NOT FOUND lines. Mandatory ones get their own prominent block right
    before the eligibility verdict — this is the only place a mandatory item
    the system couldn't verify becomes visible, since it never blocks
    overall_eligible on its own. Preferred ones (currently only
    domain_experience) get a second, visually subordinate block underneath.

    When there is nothing to flag, the report has no blank lines at all
    (matching the proposal's exact target format); blank lines only appear
    to set the review block(s) apart from the ordinary lines and the verdict.
    """
    lines: List[str] = [_experience_label(exp) + f": {_STATUS_LABELS[exp.status]}" for exp in result.experience_results]

    mandatory_manual_review: List[str] = []
    preferred_manual_review: List[str] = []

    for req_result in result.requirement_results:
        if req_result.status == MatchStatus.MANUAL_REVIEW_REQUIRED:
            target_list = (
                mandatory_manual_review
                if req_result.requirement.category == RequirementCategory.MANDATORY
                else preferred_manual_review
            )
            target_list.append(req_result.requirement.requirement)
            continue
        lines.append(f"{req_result.requirement.requirement}: {_STATUS_LABELS[req_result.status]}")

    joining_line = _format_joining_availability_line(result.joining_availability_result)
    if joining_line:
        lines.append(joining_line)

    salary_line = _format_salary_line(result.salary_result)
    if salary_line:
        lines.append(salary_line)

    if mandatory_manual_review or preferred_manual_review:
        lines.append("")
        if mandatory_manual_review:
            lines.append("REQUIRES MANUAL REVIEW (mandatory - not automatically verifiable):")
            lines.extend(f"  - {item}" for item in mandatory_manual_review)
        if preferred_manual_review:
            if mandatory_manual_review:
                lines.append("")
            lines.append("Not automatically verifiable (preferred):")
            lines.extend(f"  - {item}" for item in preferred_manual_review)
        lines.append("")

    lines.append(f"Eligibility: {'ELIGIBLE' if result.overall_eligible else 'NOT ELIGIBLE'}")

    return "\n".join(lines)
