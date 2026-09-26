from __future__ import annotations

from io import BytesIO
from pathlib import Path


class NoUsableTextError(ValueError):
    pass


def extract_pages(source: bytes | str | Path) -> list[str]:
    """Extract text per page without OCR, using pdfplumber then PyMuPDF."""
    raw = source if isinstance(source, bytes) else Path(source).read_bytes()
    pages: list[str] = []
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(raw)) as pdf:
            pages = [(page.extract_text(x_tolerance=2, y_tolerance=3) or "") for page in pdf.pages]
    except Exception:
        pages = []

    if not any(len(page.strip()) > 80 for page in pages):
        try:
            import fitz

            document = fitz.open(stream=raw, filetype="pdf")
            pages = [page.get_text("text") or "" for page in document]
        except Exception:
            pages = []

    if not any(len(page.strip()) > 80 for page in pages):
        raise NoUsableTextError(
            "Deze PDF lijkt uit scans/afbeeldingen te bestaan en kan in deze versie nog niet automatisch worden verwerkt."
        )
    return pages
