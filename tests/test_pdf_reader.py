from PIL import Image, ImageDraw

from src.parser.pdf_reader import (
    _geometric_rows_from_ocr_data,
    _logical_text_from_ocr_data,
    _needs_ocr,
    _orient_image_for_ocr,
    _recover_sparse_position_cells,
    _should_replace_extracted_text,
)
from src.parser.ocr_table import GridTable


def test_short_or_empty_pages_are_sent_to_ocr():
    assert _needs_ocr("") is True
    assert _needs_ocr("korte afbeeldingspagina") is True


def test_recognized_roster_text_skips_ocr():
    text = "FINAL TEAM LIST AND DELEGATION\nPersonal Data\nBirth Date\nPosition"
    assert _needs_ocr(text) is False


def test_sideways_scan_is_rotated_for_readable_ocr():
    portrait = Image.new("RGB", (100, 200), "white")
    draw = ImageDraw.Draw(portrait)
    for x in range(15, 90, 15):
        draw.line((x, 10, x, 190), fill="black", width=2)

    corrected = _orient_image_for_ocr(portrait, 270)

    assert corrected.size == (200, 100)


def test_upright_landscape_page_is_not_rotated_just_because_metadata_is_set():
    landscape = Image.new("RGB", (200, 100), "white")
    draw = ImageDraw.Draw(landscape)
    for y in range(15, 90, 15):
        draw.line((10, y, 190, y), fill="black", width=2)

    corrected = _orient_image_for_ocr(landscape, 90)

    assert corrected.size == (200, 100)


def test_corrupted_embedded_text_is_sent_to_ocr_even_when_it_is_long():
    corrupted = "FINAL TEAM LIST " + ("\x00\x01\x02garbage" * 80)

    assert _needs_ocr(corrupted) is True
    assert _should_replace_extracted_text(corrupted, "readable roster text " * 10) is True


def test_empty_single_character_position_cell_gets_targeted_retry():
    image = Image.new("L", (400, 160), "white")
    grid = GridTable((0, 80, 200, 280, 400), (0, 40, 80, 120, 160))
    rows = [
        ["Shirt", "Name", "Pos.", "Birthdate"],
        ["1", "ALPHA Anna", "", "01-May-2001"],
        ["2", "BETA Bea", "OH", "02-May-2001"],
        ["", "", "", ""],
    ]

    class FakeTesseract:
        @staticmethod
        def image_to_string(*_args, **_kwargs):
            return "S"

    _recover_sparse_position_cells(image, grid, rows, FakeTesseract)

    assert rows[1][2] == "S"
    assert rows[2][2] == "OH"


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
