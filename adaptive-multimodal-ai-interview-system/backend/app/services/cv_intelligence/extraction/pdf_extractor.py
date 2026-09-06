from pathlib import Path

import fitz
import pdfplumber

from app.services.cv_intelligence.extraction import CVExtractionError


def _normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _is_usable_text(text: str) -> bool:
    normalized = _normalize_text(text)
    if len(normalized) < 20:
        return False

    non_whitespace = [character for character in normalized if not character.isspace()]
    if not non_whitespace:
        return False

    printable_ratio = sum(character.isprintable() for character in non_whitespace) / len(non_whitespace)
    replacement_ratio = normalized.count("\ufffd") / len(non_whitespace)
    return printable_ratio >= 0.95 and replacement_ratio <= 0.02


def _extract_with_pdfplumber(path: Path) -> str:
    with pdfplumber.open(path) as document:
        pages = [page.extract_text() or "" for page in document.pages]
    return _normalize_text("\n\n".join(pages))


def _extract_with_pymupdf(path: Path) -> str:
    document = fitz.open(path)
    try:
        pages = [page.get_text("text") for page in document]
    finally:
        document.close()
    return _normalize_text("\n\n".join(pages))


def extract_text_from_pdf(path: str) -> str:
    """Extract readable text from a PDF, falling back to PyMuPDF when needed."""
    source_path = Path(path)
    if not source_path.is_file():
        raise CVExtractionError(f"PDF file does not exist: {path}")

    try:
        primary_text = _extract_with_pdfplumber(source_path)
    except Exception as error:
        primary_text = ""
        primary_error = error
    else:
        primary_error = None

    if _is_usable_text(primary_text):
        return primary_text

    try:
        fallback_text = _extract_with_pymupdf(source_path)
    except Exception as error:
        detail = f"pdfplumber error: {primary_error}; PyMuPDF error: {error}"
        raise CVExtractionError(f"Unable to extract text from PDF '{path}': {detail}") from error

    if not _is_usable_text(fallback_text):
        raise CVExtractionError(f"PDF contains no usable text: {path}")
    return fallback_text
