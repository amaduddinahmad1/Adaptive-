"""
app/services/eligibility/semantic_skill_matcher.py

Last-resort semantic layer for MANDATORY SKILL/TECHNOLOGY requirements that
survive both exact-string and curated-alias matching in
eligibility_engine.py. Handles the concrete failure mode observed live
twice in real pipeline runs: a candidate genuinely has a skill but expresses
it differently than the JD (job title "Machine Learning Engineer", tools
like TensorFlow/PyTorch, rather than the literal phrase "Machine Learning")
-- a tool/title-implies-skill inference that neither exact matching nor a
synonym table can express, since it requires domain knowledge ("TensorFlow
is a deep learning framework"), not textual similarity. See the design
discussion recorded around this date in the project history for why an
embedding-similarity approach was considered and rejected for this specific
failure mode (unreliable for tool-implies-category inference, though better
suited to literal rewording problems like "REST API design" vs "REST APIs").

Batched by design: ALL still-unresolved mandatory SKILL/TECHNOLOGY
requirements for one eligibility check go into a SINGLE LLM call, not one
call per requirement -- bounding the added cost/latency to at most +1 call
per check, regardless of how many requirements need judgment. Returns {}
immediately (zero calls) when there is nothing left to judge, so a
candidate who resolves everything via exact/alias matching never triggers
this layer at all.

On any failure (network error, malformed response, a requirement missing
from the response), the affected requirement(s) must fail safe to
MANUAL_REVIEW_REQUIRED rather than a fabricated NOT_MET_MANDATORY --
consistent with how domain_experience/other_mandatory_requirements already
handle "no reliable way to verify" elsewhere in this module (see
eligibility_engine.py). A transient LLM/infrastructure failure must never
irreversibly block an otherwise eligible candidate. This function itself
just returns {} on failure; the caller (eligibility_engine._match_all_
classified_requirements) is what maps a missing key to MANUAL_REVIEW_REQUIRED.

No retry-with-feedback on a malformed response (unlike JDParser/CVParser):
the failure mode here is already fully fail-safe (falls back to manual
review, never a wrong verdict), so the added complexity/cost of a retry
wasn't judged worthwhile for this layer.

Determinism caveat: temperature=0.0 minimizes but does not eliminate
run-to-run variation, and a model version change (GEMINI_MODEL, or a
provider-side update) can shift judgments with no code change. This is
inherent to using an LLM for this layer, not a defect in this
implementation -- it is exactly why every judgment must carry a reason
string and a distinct MatchStatus.MET_BY_INFERENCE, never be
indistinguishable from a deterministic exact-string MET.
"""
from typing import Dict, List, Optional

from pydantic import BaseModel, ValidationError

from app.integrations.llm.base import LLMProvider, LLMProviderError
from app.schemas.candidate import CandidateProfile
from app.schemas.job import ClassifiedRequirement

SEMANTIC_SKILL_MATCH_SYSTEM_PROMPT = """You are assisting a hiring eligibility system in judging whether a
candidate's profile provides genuine evidence for specific mandatory skill
or technology requirements that did not match by exact text.

For EACH requirement listed, decide whether the candidate profile provides
CONCRETE, SPECIFIC evidence of that skill or technology -- for example, a
job title that names it directly, a listed technology that is a
well-established tool/framework/library for it, or explicit work/project
descriptions demonstrating it.

Do NOT match on vague adjacency or general "technical" impression alone.
A candidate who has only "Python" and no other AI/ML signal does NOT
satisfy "Machine Learning" -- Python is used far too broadly to imply it.
A candidate with "TensorFlow" or "PyTorch" listed, or a job title like
"Machine Learning Engineer" or "Deep Learning Engineer" with relevant
project descriptions, DOES provide genuine evidence for "Machine Learning"
and/or "Deep Learning" as appropriate.

Explicit Generative AI / RAG evidence includes listed skills, technologies,
or project text such as RAG, Retrieval-Augmented Generation, LangChain, LLM,
Llama, or a RAG chatbot/agent project. That evidence CAN satisfy a mandatory
Generative AI and/or RAG requirement. Do NOT treat generic NLP, computer
vision, or unspecified "AI" work as Generative AI by itself.

Provide a one-sentence, specific, evidence-citing reason for every
judgment -- name the exact title/technology/project text that drove your
decision, whether matched=true or matched=false. Never fabricate evidence
that is not present in the candidate profile provided.
"""


class SkillJudgment(BaseModel):
    requirement: str
    matched: bool
    reason: str


class SkillJudgmentBatch(BaseModel):
    judgments: List[SkillJudgment]


def judge_unmatched_mandatory_skills(
    requirements: List[ClassifiedRequirement],
    candidate: CandidateProfile,
    *,
    provider: LLMProvider,
) -> Dict[str, SkillJudgment]:
    """
    Returns a requirement-text -> SkillJudgment mapping for every requirement
    in `requirements`, via a single batched LLM call. Returns {} immediately,
    with no API call, if `requirements` is empty.

    `provider` is required (not defaulted to get_default_provider()) so this
    function never silently decides on its own whether to make a real network
    call -- that decision belongs to the caller (see eligibility_engine.py's
    opt-in design: check_eligibility() only invokes this layer at all when a
    caller explicitly passes a provider).

    Assumes requirement text is unique within a single call's `requirements`
    list (true in practice -- a JD would not list the same mandatory skill
    twice); duplicates would simply share one judgment.

    Fails safe: any error (provider failure, malformed/incomplete response)
    returns {} rather than raising or fabricating a verdict -- callers must
    treat a missing key as "could not be judged" and route it to
    MANUAL_REVIEW_REQUIRED, never to a fabricated NOT_MET_MANDATORY.
    """
    if not requirements:
        return {}

    requirement_lines = "\n".join(f"- {req.requirement}" for req in requirements)
    prompt = (
        "Candidate profile (JSON):\n"
        f"{candidate.model_dump_json()}\n\n"
        "Requirements to judge:\n"
        f"{requirement_lines}"
    )

    try:
        raw_text = provider.generate_structured(
            prompt=prompt,
            system_instruction=SEMANTIC_SKILL_MATCH_SYSTEM_PROMPT,
            response_schema=SkillJudgmentBatch,
            temperature=0.0,
        )
    except LLMProviderError:
        return {}

    try:
        batch = SkillJudgmentBatch.model_validate_json(raw_text)
    except ValidationError:
        return {}

    return {judgment.requirement: judgment for judgment in batch.judgments}
