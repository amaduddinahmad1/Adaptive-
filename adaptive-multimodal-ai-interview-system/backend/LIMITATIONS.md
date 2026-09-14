# Known Limitations — JD + CV Intelligence & Eligibility Engine

Honest handoff notes on this module's current limitations, for whoever
integrates or extends it next. Nothing here is a bug — each item is a
documented, deliberate tradeoff made during Days 1-7, re-confirmed during
Day 7's testing pass (some against real Gemini output, not just theory).

## Matching accuracy

- **Skill/technology matching is exact (after case/whitespace
  normalization), not semantic.** "Python" matches " python " but "Node.js"
  will NOT match "NodeJS", "ML" will not match "Machine Learning", and "REST
  API design" will not match "REST APIs". This applies uniformly to:
  technology-years lookups in specific-experience matching
  (`experience_matcher.py`), and presence checks for both `SKILL` and
  `TECHNOLOGY` requirement types in the eligibility engine
  (`eligibility_engine.py`) — Day 7 added test coverage for `SKILL`
  specifically and confirmed it shares the exact same underlying
  limitation as `TECHNOLOGY`, not a separate one. As of the fix below,
  `SKILL`/`TECHNOLOGY` presence checks in `eligibility_engine.py` are
  additionally checked against the *combined* set of
  `candidate.skills + candidate.technologies`, which resolves cross-field
  bucket mismatches between the two independent LLM parsers — but same-
  field phrasing mismatches (different wording, both filed under the same
  bucket, e.g. "REST API design" vs "REST APIs") are still unresolved and
  remain exact-match-only. Fixing that would need a semantic/fuzzy matching
  approach (e.g. sentence-transformers-based similarity scoring), which
  remains deliberately scoped out — the abbreviation-table approach used
  for education below doesn't generalize to open-ended skill/technology
  phrasing the way it does to a small, enumerable set of degree
  abbreviations.

- **Education requirement matching is substring-based and phrasing can
  mismatch, except for a curated set of common degree abbreviations.** A
  JD requirement like "Bachelor's in Computer Science" will not match a CV
  entry like "BSc Computer Science" — confirmed occurring on real
  (non-test) data during Day 6's manual API testing, not just a
  theoretical edge case. JD parsing and CV parsing are independent LLM
  extractions with no shared vocabulary, so this kind of mismatch should
  be expected on real candidates and will bias toward false NOT MET
  verdicts on otherwise-qualified candidates. A curated
  `_DEGREE_EQUIVALENCE_GROUPS` table in `eligibility_engine.py` now covers
  the common cases actually observed — Bachelor's/B.S./BS/Bachelor of
  Science, Bachelor's/B.A./BA/Bachelor of Arts, Master's/M.S./MS/Master of
  Science, and PhD/Ph.D./Doctorate — bidirectionally in either the JD's or
  the CV's phrasing. Degree levels outside this table (e.g. "MBA", "BSc")
  still fall back to plain substring matching and can still mismatch on
  phrasing; the table is meant to grow as new real-world cases are
  observed, not to be exhaustive.

- **Observed concretely during the first full JD→CV→eligibility→interview
  E2E run (2026-09-13, `backend/scripts/test_full_pipeline_e2e.py`),
  running two real, independent Gemini calls end to end (not hand-crafted
  fixtures) surfaced three simultaneous instances of the above limitations
  on one realistic JD/CV pair:**
  - JD required skill `"Python"` was NOT MET even though the candidate
    clearly had 4 years of Python experience — the CV parser categorized
    `"Python"` under `technologies`, not `skills`, and skill-matching only
    checks `candidate.skills`. This is a *cross-field* miss (same term,
    different top-level bucket between the two independent parsers),
    distinct from same-field exact-string mismatches.
  - JD required skill `"REST API design"` was NOT MET against a CV that
    said `"REST APIs"` — same underlying skill, different real LLM
    phrasing on each side, exact-match fails.
  - JD requirement `"Bachelor's in Computer Science..."` was NOT MET
    against a CV that said `"B.S. in Computer Science, State University,
    2020"` — the abbreviation `"B.S."` never contains the substring
    `"bachelor's"`.
  - All three were originally resolved for that test run only by rewording
    the CV text to use JD-matching terminology (Python listed explicitly as
    a skill, "REST API design" verbatim, "Bachelor's" spelled out) — not by
    changing any matching code. Kept here as concrete, reproducible
    evidence for whenever semantic/fuzzy matching gets prioritized.
  - **Update:** the first and third of these are now fixed in matching code
    itself (no CV rewording needed) — the cross-field skill/technology
    lookup and the degree-abbreviation table described above. Re-running
    the E2E script with the original, unmodified CV wording confirmed both:
    a live Gemini parse for the same JD/CV pair categorized "Kubernetes" as
    a JD `skill` against a CV that only listed it under `technologies`, and
    it now correctly matched. The second (`"REST API design"` vs
    `"REST APIs"`) is same-field phrasing, not cross-field or an
    enumerable abbreviation, so it remains unresolved — see the semantic-
    matching limitation above.

- **A tool/title-implies-skill inference gap (distinct from the phrasing
  mismatches above) was confirmed live twice in real pipeline runs**
  (`backend/scripts/run_pipeline_smoketest.py`, using a real CV): a JD
  requiring bare-term mandatory skills like `"Machine Learning"`/
  `"Deep Learning"` was NOT MET against a candidate whose profile never
  literally contains those phrases or their abbreviations, but clearly
  demonstrates them — job title `"Machine Learning Internee"`, a `"Deep
  Learning Specialization"` certification, and projects citing
  Scikit-learn/XGBoost/TensorFlow/Keras. Unlike the rewording/abbreviation
  cases above, no synonym table can express this — it requires domain
  knowledge (`"TensorFlow is a deep learning framework"`), not textual
  similarity. Fixed with a new, strictly opt-in semantic-inference layer:
  `MatchStatus.MET_BY_INFERENCE`, resolved by
  `semantic_skill_matcher.judge_unmatched_mandatory_skills()`, which
  batches every remaining unmatched mandatory `SKILL`/`TECHNOLOGY`
  requirement into a single LLM call (never one call per requirement) and
  always attaches an evidence-citing reason string, enforced non-empty by
  a `RequirementMatchResult` validator so an inferred match can never be
  silently indistinguishable from a deterministic exact-string `MET`
  anywhere it's displayed or persisted. Opt-in via
  `check_eligibility(provider=...)`: omitting `provider` keeps this
  function 100% deterministic and network-free, unchanged from before this
  layer existed — every existing eligibility test relies on this.
  A small curated `_SKILL_EQUIVALENCE_GROUPS` table (currently just
  ML/DL, evidence-based only, same discipline as the degree table) runs
  first and resolves literal synonym mismatches for free before this more
  expensive layer is ever reached.

- **Follow-up, not yet fixed: the semantic-inference layer's fail-safe path
  swallows the real underlying error without logging it.** When the batched
  LLM call in `judge_unmatched_mandatory_skills()` fails (provider error or
  a malformed response), every affected requirement correctly becomes
  `MANUAL_REVIEW_REQUIRED` rather than a fabricated `NOT_MET_MANDATORY` —
  but the actual exception (e.g. a transient Gemini 503, or a schema
  validation failure) is discarded, not logged. This was observed directly:
  one real pipeline run silently hit this path and produced
  `overall_eligible=True` for the same underlying reason a completely
  different, fully-confirmed run also produced `True` — both looked
  identical from the top-level boolean alone, and were only distinguished
  by inspecting each `RequirementMatchResult.reason` individually. Worth
  adding structured logging (e.g. `logger.warning` with the caught
  exception) in `semantic_skill_matcher.py`'s two `except` blocks so an
  operator can tell "the LLM was consulted and found nothing" apart from
  "the LLM was never successfully consulted at all" without manually
  diffing reason strings.

- **Follow-up, not yet fixed: some mandatory JD requirements are
  dispositions, not checkable skills, and are currently misclassified as
  `SKILL` type anyway.** Observed live: a JD requiring `"Willingness to
  learn new tools"` as a mandatory skill can never be satisfied by exact,
  alias, or even semantic-inference matching, since no real CV states a
  disposition like this as a literal skill/technology — it isn't evidence
  of a checkable capability the way "TensorFlow" or "Machine Learning" is.
  This isn't a matching-logic bug (matching is working as designed); it's
  that `requirement_classifier.py`/JD parsing routes this kind of language
  into `SKILL` when it more properly belongs alongside `domain_experience`/
  `other_mandatory_requirements` — items that always resolve to
  `MANUAL_REVIEW_REQUIRED` because there's genuinely no `CandidateProfile`
  field to check them against. Deliberately not fixed today: reclassifying
  this is a requirement-classifier design change, a different kind of
  decision than the eligibility-matching work above, and blurring the two
  together risked conflating two separate problems. Worked around at the
  JD-authoring level in the meantime (moved out of the mandatory list
  entirely in `sample_jd_ai_engineer_intern_v3.txt`), which is itself weak
  evidence for the reclassification argument: a requirement that
  structurally can never be verified against a `CandidateProfile`
  arguably shouldn't be mandatory in a well-written JD to begin with.

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
