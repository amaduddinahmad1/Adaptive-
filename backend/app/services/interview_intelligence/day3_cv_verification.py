import logging
from typing import List

from .models import CVClaim, iter_claim_sources
from app.schemas.candidate import CandidateProfile

logger = logging.getLogger(__name__)


def verify_cv_claims(candidate_profile: CandidateProfile) -> List[CVClaim]:
    """Extract significant claims from the CV and produce targeted verification questions."""
    logger.info("Verifying CV claims for candidate")
    raw_claims = iter_claim_sources(candidate_profile)
    if not raw_claims:
        raw_claims = ["Candidate profile contains no explicit CV claims."]
    verified_claims: List[CVClaim] = []

    for claim in raw_claims:
        claim_text = claim.strip()
        if not claim_text:
            continue

        questions = [
            f"Can you walk me through the technical design of this work and the key architecture decisions you made?",
            f"What were the main technical challenges you encountered, and how did you validate the solution under real workload constraints?",
            f"What measurable outcomes or business impact did this effort deliver, and how did you verify them?",
        ]

        if "FastAPI" in claim_text or "API" in claim_text:
            questions[0] = "What endpoints, schemas, and request flow did you implement, and how did you handle validation, error handling, and performance?"
        if "PostgreSQL" in claim_text or "database" in claim_text:
            questions[1] = "Which tables, indexes, and transaction boundaries did you design, and how did you handle consistency and performance issues?"
        if "Docker" in claim_text or "deploy" in claim_text or "CI" in claim_text:
            questions[2] = "How did you validate deployment safety, monitor the service, and measure the impact after rollout?"

        verified_claims.append(
            CVClaim(
                claim_text=claim_text,
                claim_questions=questions[:3],
                verification_focus="implementation details, constraints, validation, and measurable outcomes",
            )
        )

    logger.info("Generated %d CV verification items", len(verified_claims))
    return verified_claims
