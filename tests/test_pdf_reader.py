from PIL import Image

from src.parser.pdf_reader import _needs_ocr, _orient_image_for_ocr


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
