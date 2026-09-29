from PIL import Image

from src.parser.pdf_reader import (
    _geometric_rows_from_ocr_data,
    _logical_text_from_ocr_data,
    _needs_ocr,
    _orient_image_for_ocr,
)


def test_short_or_empty_pages_are_sent_to_ocr():
    assert _needs_ocr("") is True
    assert _needs_ocr("korte afbeeldingspagina") is True


def test_recognized_roster_text_skips_ocr():
    text = "FINAL TEAM LIST AND DELEGATION\nPersonal Data\nBirth Date\nPosition"
    assert _needs_ocr(text) is False


def test_sideways_scan_is_rotated_for_readable_ocr():
    portrait = Image.new("RGB", (100, 200), "white")

    corrected = _orient_image_for_ocr(portrait, 270)

    assert corrected.size == (200, 100)


def test_dense_table_words_are_reassembled_by_visual_row():
    data = {
        "text": [
            "174474", "5", "Yordanova", "Maria", "OH", "25-May-2002", "184",
            "142347", "6", "Paskova", "Miroslava", "OH", "16-Feb-1996", "181",
        ],
        "conf": [90] * 14,
        "left": [10, 90, 150, 300, 500, 560, 690, 10, 90, 150, 300, 500, 560, 690],
        "top": [100, 101, 99, 102, 100, 101, 100, 140, 139, 141, 140, 139, 140, 141],
        "width": [60, 20, 120, 90, 30, 110, 35, 60, 20, 100, 100, 30, 110, 35],
        "height": [18] * 14,
        # Simulate the common failure where OCR assigns every table cell to a separate line.
        "block_num": list(range(1, 15)),
        "par_num": [1] * 14,
        "line_num": [1] * 14,
    }

    logical = _logical_text_from_ocr_data(data)
    geometric = _geometric_rows_from_ocr_data(data, 1000)

    assert "174474\n5\nYordanova" in logical
    assert "174474 5 Yordanova Maria OH 25-May-2002 184" in geometric
    assert "142347 6 Paskova Miroslava OH 16-Feb-1996 181" in geometric
