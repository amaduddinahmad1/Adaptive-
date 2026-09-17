"""Dispatch CV text extraction to the existing PDF/DOCX extractors."""
from pathlib import Path

from app.services.cv_intelligence.extraction import CVExtractionError
from app.services.cv_intelligence.extraction.docx_extractor import extract_text_from_docx
from app.services.cv_intelligence.extraction.pdf_extractor import extract_text_from_pdf

SUPPORTED_CV_SUFFIXES = {".pdf", ".docx"}


def extract_cv_text(path: str) -> str:
    """Extract readable text from a CV file using the existing format extractors."""
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    if suffix == ".docx":
        return extract_text_from_docx(path)
    raise CVExtractionError(
        f"Unsupported CV format '{suffix or 'unknown'}'. Supported formats: PDF, DOCX."
    )
