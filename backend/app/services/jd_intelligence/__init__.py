"""JD Intelligence service module powered by Google Gemini."""

from app.services.jd_intelligence.jd_parser import (
    DEFAULT_MODEL,
    JDParser,
    JDParserError,
    parse_job_description,
)

__all__ = [
    "DEFAULT_MODEL",
    "JDParser",
    "JDParserError",
    "parse_job_description",
]
