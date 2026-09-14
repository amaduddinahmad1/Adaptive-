"""
tests/unit/test_date_utils.py

Unit tests for app.services.eligibility.date_utils: date-string parsing,
single-role duration calculation, interval merging, and total
general-experience aggregation across a candidate's work_experience.
"""

from datetime import date

from app.schemas.candidate import WorkExperience
from app.services.eligibility.date_utils import (
    calculate_role_duration_years,
    calculate_total_general_experience,
    merge_overlapping_ranges,
    parse_date_string,
)

TODAY = date(2026, 9, 8)


# ---------------------------------------------------------------------------
# parse_date_string
# ---------------------------------------------------------------------------
def test_parse_date_string_none_returns_none():
    assert parse_date_string(None, today=TODAY) is None


def test_parse_date_string_present_returns_today():
    assert parse_date_string("present", today=TODAY) == TODAY
    assert parse_date_string("Present", today=TODAY) == TODAY


def test_parse_date_string_year_month_format():
    assert parse_date_string("2022-01", today=TODAY) == date(2022, 1, 1)


def test_parse_date_string_bare_year_format():
    assert parse_date_string("2023", today=TODAY) == date(2023, 1, 1)


def test_parse_date_string_full_month_year_format():
    assert parse_date_string("March 2021", today=TODAY) == date(2021, 3, 1)


def test_parse_date_string_abbreviated_month_year_format():
    assert parse_date_string("Mar 2021", today=TODAY) == date(2021, 3, 1)


def test_parse_date_string_unparseable_returns_none_without_crashing():
    assert parse_date_string("sometime last year", today=TODAY) is None
    assert parse_date_string("", today=TODAY) is None


def test_parse_date_string_ordinal_day_month_year_format():
    """Real gap found in run_real_interview.py's actual CV parse output (see LIMITATIONS.md discussion)."""
    assert parse_date_string("1st April 2026", today=TODAY) == date(2026, 4, 1)
    assert parse_date_string("30th April 2026", today=TODAY) == date(2026, 4, 30)


# ---------------------------------------------------------------------------
# calculate_role_duration_years
# ---------------------------------------------------------------------------
def test_calculate_role_duration_years_normal_range():
    duration = calculate_role_duration_years(date(2022, 1, 1), date(2023, 1, 1))
    assert duration == 365 / 365.25


def test_calculate_role_duration_years_none_start_returns_none():
    assert calculate_role_duration_years(None, date(2023, 1, 1)) is None


def test_calculate_role_duration_years_none_end_returns_none():
    assert calculate_role_duration_years(date(2022, 1, 1), None) is None


def test_calculate_role_duration_years_end_before_start_returns_none():
    assert calculate_role_duration_years(date(2023, 1, 1), date(2022, 1, 1)) is None


# ---------------------------------------------------------------------------
# merge_overlapping_ranges
# ---------------------------------------------------------------------------
def test_merge_no_overlap_keeps_ranges_separate():
    ranges = [(date(2018, 1, 1), date(2019, 1, 1)), (date(2020, 1, 1), date(2021, 1, 1))]
    assert merge_overlapping_ranges(ranges) == ranges


def test_merge_full_containment():
    ranges = [(date(2020, 1, 1), date(2023, 1, 1)), (date(2021, 1, 1), date(2022, 1, 1))]
    assert merge_overlapping_ranges(ranges) == [(date(2020, 1, 1), date(2023, 1, 1))]


def test_merge_partial_overlap():
    ranges = [(date(2020, 1, 1), date(2021, 6, 1)), (date(2021, 1, 1), date(2022, 1, 1))]
    assert merge_overlapping_ranges(ranges) == [(date(2020, 1, 1), date(2022, 1, 1))]


def test_merge_touching_boundaries():
    ranges = [(date(2020, 1, 1), date(2021, 1, 1)), (date(2021, 1, 1), date(2022, 1, 1))]
    assert merge_overlapping_ranges(ranges) == [(date(2020, 1, 1), date(2022, 1, 1))]


def test_merge_unsorted_input_still_merges_correctly():
    ranges = [(date(2021, 1, 1), date(2022, 1, 1)), (date(2020, 1, 1), date(2021, 6, 1))]
    assert merge_overlapping_ranges(ranges) == [(date(2020, 1, 1), date(2022, 1, 1))]


def test_merge_empty_list_returns_empty_list():
    assert merge_overlapping_ranges([]) == []


# ---------------------------------------------------------------------------
# calculate_total_general_experience
# ---------------------------------------------------------------------------
def test_single_closed_role():
    work_experience = [
        WorkExperience(position="Engineer", start_date="2020-01", end_date="2023-01"),
    ]
    total = calculate_total_general_experience(work_experience, today=TODAY)
    expected_days = (date(2023, 1, 1) - date(2020, 1, 1)).days
    assert total == expected_days / 365.25


def test_two_overlapping_roles_not_double_counted():
    work_experience = [
        WorkExperience(position="Engineer", company="A", start_date="2020-01", end_date="2022-01"),
        WorkExperience(position="Consultant", company="B", start_date="2021-01", end_date="2023-01"),
    ]
    total = calculate_total_general_experience(work_experience, today=TODAY)
    # Merged range: 2020-01 to 2023-01 = 3 years, not the naive 4-year sum.
    expected_days = (date(2023, 1, 1) - date(2020, 1, 1)).days
    assert total == expected_days / 365.25


def test_present_role_computes_duration_to_injected_today():
    work_experience = [
        WorkExperience(position="Engineer", start_date="2024-01", end_date="present"),
    ]
    total = calculate_total_general_experience(work_experience, today=TODAY)
    expected_days = (TODAY - date(2024, 1, 1)).days
    assert total == expected_days / 365.25


def test_role_with_none_dates_excluded_without_crashing():
    work_experience = [
        WorkExperience(position="Engineer", start_date="2020-01", end_date="2022-01"),
        WorkExperience(position="Startup Gig", start_date=None, end_date=None),
    ]
    total = calculate_total_general_experience(work_experience, today=TODAY)
    expected_days = (date(2022, 1, 1) - date(2020, 1, 1)).days
    assert total == expected_days / 365.25


def test_empty_work_experience_returns_zero():
    assert calculate_total_general_experience([], today=TODAY) == 0.0


def test_short_internship_with_ordinal_dates_not_silently_dropped():
    """
    End-to-end regression for the real gap: a 1-month internship expressed
    with ordinal-day dates must now contribute ~1 month to the general
    experience total, not be silently excluded.
    """
    work_experience = [
        WorkExperience(position="ML Internee", start_date="1st April 2026", end_date="30th April 2026"),
    ]
    total = calculate_total_general_experience(work_experience, today=TODAY)
    expected_days = (date(2026, 4, 30) - date(2026, 4, 1)).days
    assert total == expected_days / 365.25
    assert total > 0.0


def test_malformed_end_before_start_entry_excluded_from_aggregation():
    """
    Verifies the end-before-start exclusion propagates through the full
    aggregation (not just the lower-level calculate_role_duration_years
    helper): a malformed entry is dropped and does not crash or corrupt
    the total contributed by the other, valid entries.
    """
    work_experience = [
        WorkExperience(position="Engineer", start_date="2020-01", end_date="2022-01"),
        WorkExperience(position="Bad Data Entry", start_date="2023-01", end_date="2021-01"),
    ]
    total = calculate_total_general_experience(work_experience, today=TODAY)
    expected_days = (date(2022, 1, 1) - date(2020, 1, 1)).days
    assert total == expected_days / 365.25
