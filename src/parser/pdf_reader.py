from __future__ import annotations

from io import BytesIO
from pathlib import Path
import logging

LOGGER = logging.getLogger(__name__)


class NoUsableTextError(ValueError):
    pass


def extract_pages(source: bytes | str | Path) -> list[str]:
    """Extract text per page and apply local OCR to image-based pages."""
    raw = source if isinstance(source, bytes) else Path(source).read_bytes()
    pages: list[str] = []
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(raw)) as pdf:
            pages = [(page.extract_text(x_tolerance=2, y_tolerance=3) or "") for page in pdf.pages]
    except Exception:
        pages = []

    if not pages:
        try:
            import fitz

            document = fitz.open(stream=raw, filetype="pdf")
            pages = [page.get_text("text") or "" for page in document]
        except Exception:
            pages = []

    pages = _ocr_image_pages(raw, pages)

    if not any(len(page.strip()) > 80 for page in pages):
        raise NoUsableTextError(
            "Deze PDF bevat geen bruikbare tekst en kon ook niet met lokale OCR worden gelezen."
        )
    return pages


def _ocr_image_pages(raw: bytes, extracted_pages: list[str]) -> list[str]:
    """OCR only pages whose embedded text is too limited for roster detection."""
    try:
        import fitz
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError:
        LOGGER.info("OCR overgeslagen omdat een lokale OCR-afhankelijkheid ontbreekt.")
        return extracted_pages

    try:
        document = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        return extracted_pages

    pages = list(extracted_pages)
    if len(pages) < len(document):
        pages.extend([""] * (len(document) - len(pages)))

    for index, page in enumerate(document):
        current = pages[index] if index < len(pages) else ""
        if not _needs_ocr(current) or not page.get_images(full=True):
            continue
        try:
            pixmap = page.get_pixmap(dpi=200, colorspace=fitz.csRGB, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            image = ImageOps.autocontrast(ImageOps.grayscale(image))
            ocr_text = pytesseract.image_to_string(image, lang="eng", config="--psm 6")
            if len(ocr_text.strip()) > len(current.strip()):
                pages[index] = ocr_text
        except Exception as exc:
            LOGGER.info("OCR van PDF-pagina %s overgeslagen: %s", index + 1, type(exc).__name__)
    return pages


def _needs_ocr(text: str) -> bool:
    clean = " ".join(str(text or "").split())
    upper = clean.upper()
    if "FINAL TEAM LIST" in upper and ("BIRTH" in upper or "POSITION" in upper):
        return False
    return len(clean) < 350
