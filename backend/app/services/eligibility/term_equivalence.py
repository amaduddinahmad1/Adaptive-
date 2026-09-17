"""
Curated skill/technology phrasing equivalents used by eligibility matching
and requirement classification.

These are synonym/abbreviation relationships only. They do not encode
tool-implies-skill inferences (TensorFlow => Deep Learning); that remains
the semantic matcher layer. Short aliases are matched with alphanumeric
boundaries so "ML" does not match inside "HTML".
"""

from __future__ import annotations

import re
from typing import Iterable, Set

# Deliberately narrow groups of interchangeable phrasings. Grow only when a
# real pipeline mismatch is observed — same discipline as degree aliases.
SKILL_EQUIVALENCE_GROUPS: list[Set[str]] = [
    {"machine learning", "ml", "ai/ml", "ai-ml"},
    {"deep learning", "dl"},
    {
        "rag",
        "rag (retrieval-augmented generation)",
        "retrieval-augmented generation",
        "retrieval augmented generation",
        "generative ai/rag",
        "generative ai / rag",
    },
    {
        "generative ai",
        "gen ai",
        "genai",
        "generative ai/rag",
        "generative ai / rag",
    },
]


def normalize_term(term: str) -> str:
    """Case-insensitive, whitespace-collapsed form of a skill/technology string."""
    return " ".join(term.strip().lower().split())


def alias_in_text(alias: str, text: str) -> bool:
    """
    True when `alias` appears in `text` as a whole token, not as a substring
    of a longer alphanumeric token. `/`, `-`, and parentheses count as
    boundaries, so "ml" matches inside "AI/ML" and "rag" matches inside
    "RAG-based", but "ml" does not match inside "HTML".
    """
    if not alias or not text:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None


def skill_aliases(term: str) -> Set[str]:
    """
    Every curated phrasing interchangeable with `term`, plus the normalized
    term itself. Unlisted terms map to just themselves.
    """
    normalized = normalize_term(term)
    aliases = {normalized}
    if not normalized:
        return aliases

    for group in SKILL_EQUIVALENCE_GROUPS:
        if normalized in group:
            aliases |= group
            continue
        if any(alias_in_text(alias, normalized) for alias in group):
            aliases |= group
    return aliases


def is_conceptual_skill_term(term: str) -> bool:
    """True when `term` belongs to (or contains) a curated concept group such as ML/DL/RAG."""
    aliases = skill_aliases(term)
    return any(aliases & group for group in SKILL_EQUIVALENCE_GROUPS)


def conceptual_alias_keys(term: str) -> Set[str]:
    if is_conceptual_skill_term(term):
        return set(skill_aliases(term))
    return {normalize_term(term)}


def any_alias_matches(requirement_text: str, evidence_texts: Iterable[str]) -> bool:
    """Exact field match or bounded phrase match of any alias against evidence strings."""
    aliases = skill_aliases(requirement_text)
    for raw in evidence_texts:
        if not raw or not str(raw).strip():
            continue
        text = str(raw)
        normalized = normalize_term(text)
        for alias in aliases:
            if normalized == alias or alias_in_text(alias, text):
                return True
    return False
