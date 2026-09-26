from src.parser.pdf_reader import _needs_ocr


def test_short_or_empty_pages_are_sent_to_ocr():
    assert _needs_ocr("") is True
    assert _needs_ocr("korte afbeeldingspagina") is True


def test_recognized_roster_text_skips_ocr():
    text = "FINAL TEAM LIST AND DELEGATION\nPersonal Data\nBirth Date\nPosition"
    assert _needs_ocr(text) is False
