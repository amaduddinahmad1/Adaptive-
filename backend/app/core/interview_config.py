"""Interview configuration constants shared by job postings and runtime."""

DEFAULT_INTERVIEW_QUESTION_COUNT = 7
MIN_INTERVIEW_QUESTION_COUNT = 1
MAX_INTERVIEW_QUESTION_COUNT = 20


def normalize_interview_question_count(value) -> int:
    """Return a positive interview question budget.

    Missing or invalid values (including 0/negative) fall back to the default
    so existing jobs without an explicit count keep working. API request
    validation still rejects 0/negative on create; this helper is for runtime
    and persistence defaults only.
    """
    try:
        count = int(value)
    except (TypeError, ValueError):
        return DEFAULT_INTERVIEW_QUESTION_COUNT
    if count < MIN_INTERVIEW_QUESTION_COUNT:
        return DEFAULT_INTERVIEW_QUESTION_COUNT
    return min(count, MAX_INTERVIEW_QUESTION_COUNT)
