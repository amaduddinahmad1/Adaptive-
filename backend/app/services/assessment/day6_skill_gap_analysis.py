import logging
from typing import Iterable, List

from app.services.interview_intelligence.models import AnswerEvaluation, CVClaim, CVClaimEvidence, GapAnalysisEntry, SkillMatrixEntry
from app.schemas.candidate import CandidateProfile

logger = logging.getLogger(__name__)


def build_cv_claim_evidence(
    candidate_profile: CandidateProfile,
    cv_claims: Iterable[CVClaim],
) -> CVClaimEvidence:
    """Map CV claims to scoreable candidate skills without fabricating categories."""
    skill_names = list(candidate_profile.skills)
    skill_names.extend(candidate_profile.technologies)
    skill_names.extend(item.technology for item in candidate_profile.technology_specific_experience)

    canonical_skills = {}
    for skill in skill_names:
        cleaned = skill.strip()
        if cleaned:
            canonical_skills.setdefault(cleaned.casefold(), cleaned)

    ordered_skills = sorted(canonical_skills, key=len, reverse=True)
    matched_claims: List[dict[str, str]] = []
    unmatched_claims: List[str] = []
    seen_matches = set()

    for claim in cv_claims:
        claim_text = claim.claim_text.strip()
        claim_lower = claim_text.casefold()
        matched = False
        for normalized_skill in ordered_skills:
            if normalized_skill not in claim_lower:
                continue
            skill = canonical_skills[normalized_skill]
            match_key = (skill, claim_text)
            if match_key not in seen_matches:
                matched_claims.append({"skill": skill, "claim": claim_text})
                seen_matches.add(match_key)
            matched = True
        if not matched and claim_text:
            unmatched_claims.append(claim_text)

    return CVClaimEvidence(
        matched_claims=matched_claims,
        unmatched_claims=unmatched_claims,
    )


def build_skill_matrix(answer_evaluations: Iterable[AnswerEvaluation], required_skills: List[str]) -> List[SkillMatrixEntry]:
    """Aggregate evaluation results into a skill matrix with confidence and proficiency."""
    answer_evaluations = list(answer_evaluations)
    logger.info("Building skill matrix from %d assessments", len(answer_evaluations))
    skill_scores = {}
    skill_count = {}

    for evaluation in answer_evaluations:
        for skill in evaluation.skills_covered or []:
            if not skill:
                continue
            if skill not in skill_scores:
                skill_scores[skill] = []
                skill_count[skill] = 0
            skill_scores[skill].append(evaluation.weighted_total)
            skill_count[skill] += 1

    for skill in required_skills:
        if skill not in skill_scores:
            skill_scores[skill] = [0.0]
            skill_count[skill] = 0

    entries: List[SkillMatrixEntry] = []
    for skill in sorted(set(required_skills) | set(skill_scores.keys())):
        values = skill_scores.get(skill, [0.0])
        score = round(sum(values) / len(values), 2)
        assessments = skill_count.get(skill, len(values))
        confidence = "High" if score >= 75 else "Moderate" if score >= 55 else "Low"
        entries.append(
            SkillMatrixEntry(
                skill_name=skill,
                proficiency_score=score,
                assessment_count=assessments,
                confidence_level=confidence,
                evidence_summary=f"{assessments} assessment(s) covering this area.",
            )
        )

    return entries


def analyze_cv_interview_gap(cv_claims: Iterable[dict], skill_matrix: Iterable[SkillMatrixEntry]) -> List[GapAnalysisEntry]:
    """Compare CV claim strength to observed interview evidence."""
    entries = []
    skill_map = {entry.skill_name: entry for entry in skill_matrix}

    for claim in cv_claims:
        skill = claim.get("skill", "General")
        cv_claim = claim.get("claim", "Claim not provided")
        evidence = skill_map.get(skill)
        interview_score = evidence.proficiency_score if evidence else 0.0
        if interview_score >= 75:
            alignment = "Strong"
        elif interview_score >= 55:
            alignment = "Moderate"
        else:
            alignment = "Weak"

        entries.append(
            GapAnalysisEntry(
                skill=skill,
                cv_claim=cv_claim,
                interview_evidence=f"Interview evidence score {interview_score}",
                alignment=alignment,
            )
        )

    logger.info("Gap analysis generated for %d skills", len(entries))
    return entries
