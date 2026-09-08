"""
app/services/eligibility/date_utils.py

Date-parsing and duration-calculation utilities for turning
CandidateProfile.work_experience's free-text start_date/end_date strings into
a total general-experience duration, with overlapping roles merged so they
are not double-counted.

Design notes (approved before implementation):
- "present" means an ongoing role and resolves to an injected `today`
  reference date, never datetime.now() directly, so duration calculations
  involving "present" are deterministic and testable.
- None means the date was never stated (see candidate.py's Day 2 comment
  block). A role missing a start or end date is excluded from the general
  experience total entirely, rather than guessing a value.
- Any date string that doesn't match a recognized format is treated the same
  as None (excluded, never raises) — cv_parser.py's system prompt does not
  constrain the format of a stated date, only the "present"/null sentinels,
  so unfamiliar real-world formats are expected and must fail safe rather
  than crash matching for the whole candidate.
- Month/year-only dates are normalized to the 1st of the stated period
  (Jan 1 for a bare year, the 1st for "Month YYYY"), applied identically to
  start and end dates. This is a deliberate, consistent approximation: it
  has the property that a "2022"-"2023" range computes to exactly 1.0 year,
  matching the natural reading of the range.
- A role whose end date precedes its start date is malformed data (not a
  real range) and is excluded rather than allowed to contribute a negative
  duration to the total.
"""

from datetime import date, datetime
from typing import List, Optional, Tuple

from app.schemas.candidate import WorkExperience

DAYS_PER_YEAR = 365.25

_MONTH_YEAR_FORMATS = ("%B %Y", "%b %Y")


def parse_date_string(value: Optional[str], *, today: date) -> Optional[date]:
    """
    Parses a work-experience date string into a date, or None if it is
    missing, empty, or unparseable.

    Recognized forms: "present" (-> today), "YYYY-MM", "YYYY", "Month YYYY",
    "Mon YYYY". See module docstring for the normalization and fail-safe
    rules applied.
    """
    if value is None:
        return None

    text = value.strip()
    if not text:
        return None

    if text.lower() == "present":
        return today

    try:
        parsed = datetime.strptime(text, "%Y-%m")
        return date(parsed.year, parsed.month, 1)
    except ValueError:
        pass

    for fmt in _MONTH_YEAR_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            return date(parsed.year, parsed.month, 1)
        except ValueError:
            continue

    if text.isdigit() and len(text) == 4:
        return date(int(text), 1, 1)

    return None


def calculate_role_duration_years(start: Optional[date], end: Optional[date]) -> Optional[float]:
    """
    Returns the duration in years between two dates, or None if either date
    is missing or the range is malformed (end before start).
    """
    if start is None or end is None:
        return None
    if end < start:
        return None
    return (end - start).days / DAYS_PER_YEAR


def merge_overlapping_ranges(ranges: List[Tuple[date, date]]) -> List[Tuple[date, date]]:
    """
    Merges overlapping and touching (start, end) date ranges so that summing
    their lengths does not double-count shared time.
    """
    if not ranges:
        return []

    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged = [sorted_ranges[0]]

    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def calculate_total_general_experience(
    work_experience: List[WorkExperience],
    *,
    today: Optional[date] = None,
) -> float:
    """
    Calculates total general experience in years from a candidate's
    work_experience, merging overlapping roles so shared time is not
    double-counted.

    Args:
        work_experience: The candidate's work history.
        today: Reference date for resolving "present" end dates. Defaults to
            the real current date; tests should inject a fixed date instead.

    Returns:
        Total years of experience across merged, non-overlapping periods.
        Roles with a missing, unparseable, or malformed (end before start)
        date are excluded rather than guessed, and never cause a crash.
    """
    reference_today = today if today is not None else date.today()

    valid_ranges: List[Tuple[date, date]] = []
    for entry in work_experience:
        start = parse_date_string(entry.start_date, today=reference_today)
        end = parse_date_string(entry.end_date, today=reference_today)
        if calculate_role_duration_years(start, end) is None:
            # Missing, unparseable, or malformed date data — excluded rather
            # than guessed. See module docstring.
            continue
        valid_ranges.append((start, end))

    merged = merge_overlapping_ranges(valid_ranges)
    return sum((end - start).days for start, end in merged) / DAYS_PER_YEAR
