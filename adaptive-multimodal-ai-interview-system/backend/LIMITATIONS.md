# Known Limitations — JD + CV Intelligence & Eligibility Engine

Honest handoff notes on this module's current limitations, for whoever
integrates or extends it next. Nothing here is a bug — each item is a
documented, deliberate tradeoff made during Days 1-7, re-confirmed during
Day 7's testing pass (some against real Gemini output, not just theory).

## Matching accuracy

- **Skill/technology matching is exact (after case/whitespace
  normalization), not semantic.** "Python" matches " python " but "Node.js"
  will NOT match "NodeJS", and "ML" will not match "Machine Learning". This
  applies uniformly to: technology-years lookups in specific-experience
  matching (`experience_matcher.py`), and presence checks for both `SKILL`
  and `TECHNOLOGY` requirement types in the eligibility engine
  (`eligibility_engine.py`) — Day 7 added test coverage for `SKILL`
  specifically and confirmed it shares the exact same underlying
  limitation as `TECHNOLOGY`, not a separate one. Fixing this would need a
  semantic/fuzzy matching approach (e.g. sentence-transformers), which was
  scoped out from the start.

- **Education requirement matching is substring-based and phrasing can
  mismatch.** A JD requirement like "Bachelor's in Computer Science" will
  not match a CV entry like "BSc Computer Science" — confirmed occurring
  on real (non-test) data during Day 6's manual API testing, not just a
  theoretical edge case. JD parsing and CV parsing are independent LLM
  extractions with no shared vocabulary, so this kind of mismatch should
  be expected on real candidates and will bias toward false NOT MET
  verdicts on otherwise-qualified candidates.

- **Technology-specific experience years are LLM-estimated, not derived
  from date math.** Unlike general experience (computed via
  `date_utils.py` from actual work history date ranges),
  `technology_specific_experience` years come directly from the CV
  parser's own estimate and may have inconsistent precision across tools
  or roles within the same CV.

## Requirements with no way to automatically verify

- **`domain_experience` and `other_mandatory_requirements` have no
  corresponding field on `CandidateProfile` at all** (no industry/domain
  field, no work-authorization field, etc.). Both always resolve to
  `MatchStatus.MANUAL_REVIEW_REQUIRED` and, by design, never block
  `overall_eligible` — even when the underlying requirement is mandatory
  (e.g. "Must be eligible to work in the US"). **An `ELIGIBLE` verdict
  does not mean every mandatory requirement was verified** — some are
  flagged for a human to check instead. `format_eligibility_report()`
  surfaces these in a dedicated block for exactly this reason; don't
  discard or hide it downstream.

- **`domain_experience` has no mandatory/preferred distinction in the JD
  schema itself** — the field was scoped out during Day 1 parsing, so
  every entry defaults to `PREFERRED` regardless of how the JD actually
  phrased it.

- **`education_requirements` cannot represent "or equivalent practical
  experience"** — a JD saying "Bachelor's degree or equivalent experience"
  will only capture the degree requirement; the "or equivalent" escape
  hatch is lost.

## Recruiter-input parsing

- **A bare notice-period number with no unit (e.g. `"30"`) is deliberately
  left unparsed**, not guessed as days/weeks/months — it resolves to
  `MANUAL_REVIEW_REQUIRED` rather than a fabricated pass or fail.
