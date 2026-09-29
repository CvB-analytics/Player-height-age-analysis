from __future__ import annotations

from io import BytesIO
from pathlib import Path
import logging
from statistics import median
from typing import Any

LOGGER = logging.getLogger(__name__)
OCR_DPI = 240


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
            "Deze PDF bevat geen bruikbare tekst en kon niet betrouwbaar worden gelezen."
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
            pixmap = page.get_pixmap(dpi=OCR_DPI, colorspace=fitz.csRGB, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            image = _orient_image_for_ocr(image, page.rotation)
            image = ImageOps.autocontrast(ImageOps.grayscale(image))
            data = pytesseract.image_to_data(
                image,
                lang="eng",
                config="--psm 6 -c preserve_interword_spaces=1",
                output_type=pytesseract.Output.DICT,
            )
            logical_text = _logical_text_from_ocr_data(data)
            geometric_text = _geometric_rows_from_ocr_data(data, image.height)
            ocr_text = "\n".join(part for part in (logical_text, geometric_text) if part)
            if len(ocr_text.strip()) > len(current.strip()):
                pages[index] = ocr_text
        except Exception as exc:
            LOGGER.info("OCR van PDF-pagina %s overgeslagen: %s", index + 1, type(exc).__name__)
    return pages


def _orient_image_for_ocr(image, rotation: int):
    """Undo scan rotation metadata when the rendered content is still sideways."""
    normalized = int(rotation or 0) % 360
    if normalized == 90:
        return image.rotate(90, expand=True)
    if normalized == 180:
        return image.rotate(180, expand=True)
    if normalized == 270:
        return image.rotate(-90, expand=True)
    return image


def _needs_ocr(text: str) -> bool:
    clean = " ".join(str(text or "").split())
    upper = clean.upper()
    if "FINAL TEAM LIST" in upper and ("BIRTH" in upper or "POSITION" in upper):
        return False
    return len(clean) < 350


def _ocr_words(data: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Normalize Tesseract word boxes while retaining their table geometry."""
    words: list[dict[str, Any]] = []
    texts = data.get("text", [])
    for index, raw_text in enumerate(texts):
        text = str(raw_text or "").strip()
        if not text:
            continue
        try:
            confidence = float(data.get("conf", [])[index])
            x = int(data.get("left", [])[index])
            y = int(data.get("top", [])[index])
            width = int(data.get("width", [])[index])
            height = int(data.get("height", [])[index])
            block = int(data.get("block_num", [])[index])
            paragraph = int(data.get("par_num", [])[index])
            line = int(data.get("line_num", [])[index])
        except (IndexError, TypeError, ValueError):
            continue
        if confidence < 0 or width <= 0 or height <= 0:
            continue
        words.append(
            {
                "text": text,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "center_y": y + height / 2,
                "line_key": (block, paragraph, line),
            }
        )
    return words


def _logical_text_from_ocr_data(data: dict[str, list[Any]]) -> str:
    """Rebuild Tesseract's ordinary reading order from word-level output."""
    lines: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    order: list[tuple[int, int, int]] = []
    for word in _ocr_words(data):
        key = word["line_key"]
        if key not in lines:
            lines[key] = []
            order.append(key)
        lines[key].append(word)
    return "\n".join(
        " ".join(word["text"] for word in sorted(lines[key], key=lambda item: item["x"]))
        for key in order
    )


def _geometric_rows_from_ocr_data(data: dict[str, list[Any]], image_height: int) -> str:
    """Reassemble dense scanned tables by visual row instead of OCR reading order."""
    words = _ocr_words(data)
    if not words:
        return ""
    typical_height = median(word["height"] for word in words)
    tolerance = max(5.0, min(typical_height * 0.65, image_height * 0.008))
    rows: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (item["center_y"], item["x"])):
        best = min(rows, key=lambda row: abs(row["center_y"] - word["center_y"]), default=None)
        if best is None or abs(best["center_y"] - word["center_y"]) > tolerance:
            rows.append({"center_y": word["center_y"], "words": [word]})
            continue
        best["words"].append(word)
        best["center_y"] = sum(item["center_y"] for item in best["words"]) / len(best["words"])

    reconstructed: list[str] = []
    for row in sorted(rows, key=lambda item: item["center_y"]):
        row_words = sorted(row["words"], key=lambda item: item["x"])
        if len(row_words) < 2:
            continue
        reconstructed.append(" ".join(word["text"] for word in row_words))
    return "\n".join(reconstructed)
