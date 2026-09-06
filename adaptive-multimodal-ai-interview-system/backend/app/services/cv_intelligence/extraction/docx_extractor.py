from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.cv_intelligence.extraction import CVExtractionError


def _normalize_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _iter_document_blocks(document: Document):
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def extract_text_from_docx(path: str) -> str:
    """Extract paragraph and table text from a DOCX document in document order."""
    source_path = Path(path)
    if not source_path.is_file():
        raise CVExtractionError(f"DOCX file does not exist: {path}")

    try:
        document = Document(source_path)
        blocks = []
        for block in _iter_document_blocks(document):
            if isinstance(block, Paragraph):
                if block.text.strip():
                    blocks.append(block.text)
            else:
                for row in block.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    row_text = " | ".join(cell for cell in cells if cell)
                    if row_text:
                        blocks.append(row_text)
    except Exception as error:
        raise CVExtractionError(f"Unable to extract text from DOCX '{path}': {error}") from error

    text = _normalize_text("\n".join(blocks))
    if not text:
        raise CVExtractionError(f"DOCX contains no usable text: {path}")
    return text
