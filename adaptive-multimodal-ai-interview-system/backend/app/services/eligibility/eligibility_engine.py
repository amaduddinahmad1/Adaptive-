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

MatchStatus.MET_BY_INFERENCE is a distinct, non-deterministic verdict for a
mandatory SKILL/TECHNOLOGY requirement resolved via an LLM judgment call
(see semantic_skill_matcher.py) rather than exact/alias matching — always
carries a reason string (enforced on RequirementMatchResult), and is never
rendered or persisted as an indistinguishable plain MET. Strictly opt-in via
check_eligibility(provider=...): omitting provider keeps this function
100% deterministic and network-free, exactly as before this layer existed.
"""

import re
from datetime import date
from enum import Enum
from typing import List, Optional, Set

from pydantic import BaseModel, model_validator

from app.integrations.llm.base import LLMProvider
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
from app.services.eligibility.semantic_skill_matcher import judge_unmatched_mandatory_skills


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
    MET_BY_INFERENCE = "met_by_inference"
    NOT_MET_MANDATORY = "not_met_mandatory"
    NOT_FOUND_PREFERRED = "not_found_preferred"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class ExperienceEligibilityResult(BaseModel):
    """Composes Day 4's ExperienceMatchResult with the mandatory/preferred verdict it doesn't carry."""
    match: ExperienceMatchResult
    is_mandatory: bool
    status: MatchStatus


class RequirementMatchResult(BaseModel):
    """
    Composes a Day 3 ClassifiedRequirement with its match verdict.

    reason is None for every deterministic verdict (exact/alias/substring
    match, or no match at all) -- there is nothing beyond the verdict itself
    to explain. It is enforced non-empty specifically when status is
    MET_BY_INFERENCE (see the validator below), so an LLM-inferred match can
    never be silently indistinguishable from a deterministic exact-string
    MET anywhere this result is displayed or persisted -- the report
    formatter and the JSONB dump written to Application.eligibility_result
    both carry this field automatically since it's a real model field, not
    something bolted on downstream.
    """
    requirement: ClassifiedRequirement
    status: MatchStatus
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _reason_required_for_inference(self) -> "RequirementMatchResult":
        if self.status == MatchStatus.MET_BY_INFERENCE and not self.reason:
            raise ValueError("reason is required when status is MET_BY_INFERENCE")
        return self


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


# Curated degree-abbreviation equivalents. "Bachelor's"/"Master's" deliberately
# appear in more than one group since a JD's generic degree_level should be
# satisfiable by any of that degree's specific forms (e.g. either B.S. or
# B.A. satisfies a plain "Bachelor's" requirement). Certification matching has
# no equivalent table yet — no concrete abbreviation mismatch has been
# observed there (see LIMITATIONS.md).
_DEGREE_EQUIVALENCE_GROUPS: List[Set[str]] = [
    {"bachelor's", "bachelors", "b.s.", "bs", "bachelor of science"},
    {"bachelor's", "bachelors", "b.a.", "ba", "bachelor of arts"},
    {"master's", "masters", "m.s.", "ms", "master of science"},
    {"phd", "ph.d.", "doctorate", "doctoral"},
]


def _degree_aliases(term: str) -> Set[str]:
    """
    Every phrasing interchangeable with `term`, per _DEGREE_EQUIVALENCE_GROUPS,
    plus the term itself. A term absent from the table maps to just itself, so
    unlisted degree levels fall back to plain substring matching unchanged.
    """
    normalized = term.strip().lower()
    aliases = {normalized}
    for group in _DEGREE_EQUIVALENCE_GROUPS:
        if normalized in group:
            aliases |= group
    return aliases


def _education_match(degree_level: str, education_entries: List[str]) -> bool:
    """
    Substring match after case/whitespace normalization, expanded across
    curated degree-abbreviation equivalents (e.g. "Bachelor's" <-> "B.S.") so
    real abbreviation mismatches between independent JD/CV LLM phrasing don't
    produce false NOT_MET verdicts. See LIMITATIONS.md.
    """
    return any(_case_insensitive_substring_match(alias, education_entries) for alias in _degree_aliases(degree_level))


# Curated skill/technology abbreviation equivalents, mirroring
# _DEGREE_EQUIVALENCE_GROUPS. Deliberately narrow -- only ML/DL, the two
# terms actually observed failing exact-match in real pipeline runs -- not
# padded out with plausible-looking additions (AI, NLP, etc.) that have no
# observed evidence yet. Add more only when real data shows a real gap, same
# discipline as the degree table and the date-format fix.
#
# This table can ONLY fix a literal synonym/abbreviation mismatch (JD says
# "ML", candidate says "Machine Learning"). It cannot and is not intended to
# fix the tool/title-implies-skill case (candidate lists "TensorFlow" but
# never writes "Machine Learning" or "ML" anywhere) -- that is a domain-
# knowledge inference, not a synonym relationship, and is handled by the
# separate, more expensive semantic_skill_matcher layer below, which only
# runs for whatever this table (and exact matching) still couldn't resolve.
_SKILL_EQUIVALENCE_GROUPS: List[Set[str]] = [
    {"machine learning", "ml"},
    {"deep learning", "dl"},
]


def _skill_aliases(term: str) -> Set[str]:
    """Every phrasing interchangeable with `term`, per _SKILL_EQUIVALENCE_GROUPS, plus the term itself."""
    normalized = term.strip().lower()
    aliases = {normalized}
    for group in _SKILL_EQUIVALENCE_GROUPS:
        if normalized in group:
            aliases |= group
    return aliases


def _skill_alias_match(requirement_text: str, candidate_terms: List[str]) -> bool:
    """Exact match after normalization, expanded across curated skill-abbreviation equivalents (e.g. "ML" <-> "Machine Learning")."""
    return any(_case_insensitive_exact_match(alias, candidate_terms) for alias in _skill_aliases(requirement_text))


def _match_classified_requirement(requirement: ClassifiedRequirement, candidate: CandidateProfile) -> MatchStatus:
    """
    Matches a single non-experience ClassifiedRequirement against a candidate
    using only free, deterministic checks -- no LLM call happens here. A
    MANDATORY SKILL/TECHNOLOGY requirement that comes back NOT_MET_MANDATORY
    from this function is not necessarily final: see
    _match_all_classified_requirements, which may still escalate it to the
    semantic_skill_matcher layer.

    SKILL and TECHNOLOGY requirements are both checked against the combined
    set of candidate.skills + candidate.technologies, not just the matching
    field. JD parsing and CV parsing are two independent LLM extractions
    with no shared vocabulary enforcement between them, so they don't
    reliably agree on which field a given term belongs in — e.g. "Python"
    filed as a skill by one and a technology by the other. Confirmed
    happening on real (non-test) data during the first full pipeline E2E
    run; see LIMITATIONS.md. This mirrors the same real-vocabulary-mismatch
    reasoning as experience_matcher._lookup_technology_years. On top of exact
    matching, _skill_alias_match additionally covers curated abbreviation
    equivalents (e.g. "ML" <-> "Machine Learning") — see
    _SKILL_EQUIVALENCE_GROUPS for what this can and can't fix.

    EDUCATION requirements match the degree_level through _education_match,
    which additionally covers curated degree-abbreviation equivalents (e.g.
    "Bachelor's" <-> "B.S.") on top of plain substring matching — see
    LIMITATIONS.md. CERTIFICATION has no such table yet: no concrete
    abbreviation mismatch has been observed there.

    DOMAIN and OTHER always return MANUAL_REVIEW_REQUIRED: CandidateProfile
    has no field representing industry/domain background or things like work
    authorization, so there is nothing to check them against.

    No fallback branch exists for an unhandled requirement_type — if one is
    ever added without updating this function, `found` stays unbound and a
    NameError (or, if refactored, a Pydantic validation error on a None
    status) surfaces immediately rather than silently misclassifying.
    """
    if requirement.requirement_type in (RequirementType.SKILL, RequirementType.TECHNOLOGY):
        candidate_terms = candidate.skills + candidate.technologies
        found = _case_insensitive_exact_match(requirement.requirement, candidate_terms) or _skill_alias_match(
            requirement.requirement, candidate_terms
        )
    elif requirement.requirement_type == RequirementType.CERTIFICATION:
        found = _case_insensitive_substring_match(requirement.requirement, candidate.certifications)
    elif requirement.requirement_type == RequirementType.EDUCATION:
        degree_level = requirement.source_detail.degree_level if requirement.source_detail else requirement.requirement
        found = _education_match(degree_level, candidate.education)
    elif requirement.requirement_type in (RequirementType.DOMAIN, RequirementType.OTHER):
        return MatchStatus.MANUAL_REVIEW_REQUIRED

    if found:
        return MatchStatus.MET
    return MatchStatus.NOT_MET_MANDATORY if requirement.category == RequirementCategory.MANDATORY else MatchStatus.NOT_FOUND_PREFERRED


def _match_all_classified_requirements(
    classified_reqs: List[ClassifiedRequirement],
    candidate: CandidateProfile,
    *,
    provider: Optional[LLMProvider] = None,
) -> List[RequirementMatchResult]:
    """
    Resolves every non-experience ClassifiedRequirement, then -- only if
    `provider` is explicitly given -- escalates whatever mandatory
    SKILL/TECHNOLOGY requirements are still unresolved after deterministic
    matching to the semantic_skill_matcher layer, in a single batched call.

    The semantic layer is strictly opt-in via `provider`, deliberately not
    defaulted to get_default_provider(): check_eligibility() (and therefore
    this function) is called by many existing tests that deliberately set up
    a mandatory skill/technology mismatch as their whole premise, none of
    which pass a provider. Defaulting this to an always-on real provider
    would turn every one of those into a real, uncontrolled network call the
    moment this feature shipped -- so `provider=None` means exactly today's
    pre-existing behavior, byte-for-byte unchanged, and a caller must
    explicitly opt in (e.g. scripts/run_pipeline_smoketest.py passes
    get_default_provider()) to exercise the new capability at all.

    A requirement that reaches the semantic layer but is missing from its
    result (provider/parse failure, or the model simply omitted it) becomes
    MANUAL_REVIEW_REQUIRED, never a fabricated NOT_MET_MANDATORY -- an
    infrastructure failure must never irreversibly block an otherwise
    eligible candidate.
    """
    provisional = [
        (req, _match_classified_requirement(req, candidate))
        for req in classified_reqs
        if req.requirement_type != RequirementType.EXPERIENCE
    ]

    if provider is None:
        return [RequirementMatchResult(requirement=req, status=status) for req, status in provisional]

    # NOT_MET_MANDATORY is only ever returned for a mandatory requirement
    # (see _match_classified_requirement's final line), so no separate
    # category check is needed here.
    escalation_candidates = [
        req
        for req, status in provisional
        if status == MatchStatus.NOT_MET_MANDATORY and req.requirement_type in (RequirementType.SKILL, RequirementType.TECHNOLOGY)
    ]
    escalation_ids = {id(req) for req in escalation_candidates}

    judgments = judge_unmatched_mandatory_skills(escalation_candidates, candidate, provider=provider)

    results: List[RequirementMatchResult] = []
    for req, status in provisional:
        if id(req) not in escalation_ids:
            results.append(RequirementMatchResult(requirement=req, status=status))
            continue

        judgment = judgments.get(req.requirement)
        if judgment is None:
            results.append(
                RequirementMatchResult(
                    requirement=req,
                    status=MatchStatus.MANUAL_REVIEW_REQUIRED,
                    reason="Semantic skill match could not be completed automatically; requires manual review.",
                )
            )
        elif judgment.matched:
            results.append(RequirementMatchResult(requirement=req, status=MatchStatus.MET_BY_INFERENCE, reason=judgment.reason))
        else:
            results.append(RequirementMatchResult(requirement=req, status=MatchStatus.NOT_MET_MANDATORY, reason=judgment.reason))

    return results


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
    provider: Optional[LLMProvider] = None,
) -> EligibilityResult:
    """
    Evaluates a candidate's eligibility for a job, combining experience,
    classified requirements, joining availability, and salary.

    overall_eligible is False if and only if some check's status is
    NOT_MET_MANDATORY. MANUAL_REVIEW_REQUIRED never blocks eligibility on its
    own, even for a mandatory requirement — see module docstring.

    provider is optional and strictly opt-in: when omitted, requirement
    matching is 100% deterministic and network-free, byte-for-byte identical
    to this function's behavior before the semantic-inference layer existed.
    Passing a provider (e.g. app.integrations.llm.factory.get_default_provider())
    additionally allows mandatory SKILL/TECHNOLOGY requirements that survive
    exact and alias matching to be escalated to an LLM judgment call — see
    _match_all_classified_requirements and semantic_skill_matcher.py.
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

    requirement_results = _match_all_classified_requirements(classified_reqs, candidate, provider=provider)

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
    MatchStatus.MET_BY_INFERENCE: "MET (inferred)",
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
        line = f"{req_result.requirement.requirement}: {_STATUS_LABELS[req_result.status]}"
        if req_result.reason:
            line += f" — {req_result.reason}"
        lines.append(line)

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
