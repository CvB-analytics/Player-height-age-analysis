from __future__ import annotations

from io import BytesIO
from pathlib import Path
import logging
import re
from statistics import median
from typing import Any
import unicodedata

from .ocr_table import (
    deskew_table_image,
    detect_grid_table,
    remove_grid_lines,
    serialize_grid_rows,
    words_to_grid_rows,
)

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
            image, _ = deskew_table_image(image)
            grid = detect_grid_table(image)
            ocr_image = remove_grid_lines(image, grid, margin=3) if grid else image
            data = pytesseract.image_to_data(
                ocr_image,
                lang="eng",
                config="--psm 6 -c preserve_interword_spaces=1",
                output_type=pytesseract.Output.DICT,
            )
            logical_text = _logical_text_from_ocr_data(data)
            geometric_text = _geometric_rows_from_ocr_data(data, image.height)
            grid_text = ""
            if grid:
                # A second, sparse-text pass is deliberately limited to the
                # detected table.  It reads individual cells much more cleanly
                # than asking one OCR pass to understand the complete page.
                left, right = grid.x_lines[0], grid.x_lines[-1]
                top, bottom = grid.y_lines[0], grid.y_lines[-1]
                table_crop = ocr_image.crop((left, top, right + 1, bottom + 1))
                table_data = pytesseract.image_to_data(
                    table_crop,
                    lang="eng",
                    config="--psm 11 -c preserve_interword_spaces=1",
                    output_type=pytesseract.Output.DICT,
                )
                table_words = _ocr_words(table_data)
                for word in table_words:
                    word["x"] += left
                    word["y"] += top
                    word["center_y"] += top
                grid_rows = words_to_grid_rows(table_words, grid, keep_empty=True)
                _recover_sparse_position_cells(ocr_image, grid, grid_rows, pytesseract)
                grid_text = serialize_grid_rows([row for row in grid_rows if any(row)])
            ocr_text = "\n".join(part for part in (logical_text, geometric_text, grid_text) if part)
            if _should_replace_extracted_text(current, ocr_text):
                pages[index] = ocr_text
        except Exception as exc:
            LOGGER.info("OCR van PDF-pagina %s overgeslagen: %s", index + 1, type(exc).__name__)
    return pages


def _orient_image_for_ocr(image, rotation: int):
    """Apply rotation metadata only when the visible content is still sideways."""
    normalized = int(rotation or 0) % 360
    candidate = image
    if normalized == 90:
        candidate = image.rotate(90, expand=True)
    elif normalized == 180:
        candidate = image.rotate(180, expand=True)
    elif normalized == 270:
        candidate = image.rotate(-90, expand=True)
    if candidate is image:
        return image
    return candidate if _horizontal_structure_score(candidate) > _horizontal_structure_score(image) * 1.15 else image


def _horizontal_structure_score(image) -> float:
    """Measure whether text and ruling lines predominantly run horizontally."""
    import numpy as np
    from PIL import ImageOps

    sample = ImageOps.autocontrast(ImageOps.grayscale(image.copy()))
    sample.thumbnail((800, 800))
    dark = np.asarray(sample) < 170
    if not dark.any():
        return 0.0
    horizontal = dark.mean(axis=1)
    vertical = dark.mean(axis=0)
    horizontal_count = max(5, int(len(horizontal) * 0.03))
    vertical_count = max(5, int(len(vertical) * 0.03))
    horizontal_strength = float(np.square(np.sort(horizontal)[-horizontal_count:]).mean())
    vertical_strength = float(np.square(np.sort(vertical)[-vertical_count:]).mean())
    return horizontal_strength / max(vertical_strength, 1e-9)


def _needs_ocr(text: str) -> bool:
    raw = str(text or "")
    if _is_corrupted_text(raw):
        return True
    clean = " ".join(raw.split())
    upper = clean.upper()
    if "FINAL TEAM LIST" in upper and ("BIRTH" in upper or "POSITION" in upper):
        return False
    return len(clean) < 350


def _is_corrupted_text(text: str) -> bool:
    raw = str(text or "")
    control_characters = sum(
        1
        for character in raw
        if unicodedata.category(character).startswith("C") and not character.isspace()
    )
    return control_characters / max(1, len(raw)) > 0.02


def _should_replace_extracted_text(current: str, ocr_text: str) -> bool:
    readable_ocr = str(ocr_text or "").strip()
    if len(readable_ocr) <= 80:
        return False
    return _is_corrupted_text(current) or len(readable_ocr) > len(str(current or "").strip())


def _recover_sparse_position_cells(image, grid, rows: list[list[str]], pytesseract_module) -> None:
    """Retry tiny empty position cells, where one-letter codes are often skipped."""
    from PIL import ImageOps

    header_row: int | None = None
    position_column: int | None = None
    birth_column: int | None = None
    for row_index, row in enumerate(rows[:5]):
        for column, value in enumerate(row):
            normalized = re.sub(r"[^a-z]", "", str(value).casefold())
            if normalized in {"pos", "position"}:
                header_row, position_column = row_index, column
            if normalized in {"birthdate", "dateofbirth", "dob"}:
                birth_column = column
        if header_row is not None and birth_column is not None:
            break
    if header_row is None or position_column is None or birth_column is None:
        return

    accepted = {
        "S", "OH", "OP", "MB", "L", "5", "0H", "0P", "M8", "I",
        "SS", "CS", "SC",
    }
    for row_index in range(header_row + 1, min(len(rows), len(grid.y_lines) - 1)):
        row = rows[row_index]
        if birth_column >= len(row) or not re.search(r"\d{1,4}[-/.]\w{1,9}[-/.]\d{2,4}", row[birth_column]):
            continue
        current = re.sub(r"[^A-Z0-9]", "", row[position_column].upper())
        if current in accepted:
            continue
        left, right = grid.x_lines[position_column], grid.x_lines[position_column + 1]
        top, bottom = grid.y_lines[row_index], grid.y_lines[row_index + 1]
        cell = image.crop((left + 2, top + 2, right - 1, bottom - 1))
        cell = ImageOps.autocontrast(cell).resize((max(1, cell.width * 3), max(1, cell.height * 3)))
        candidate = pytesseract_module.image_to_string(
            cell,
            lang="eng",
            config="--psm 10 -c tessedit_char_whitelist=CSOHPMBL0158",
        )
        candidate = re.sub(r"[^A-Z0-9]", "", candidate.upper())
        if candidate in accepted:
            row[position_column] = candidate


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
