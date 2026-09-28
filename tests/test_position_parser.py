from src.parser.position_parser import normalize_position


def test_position_mapping():
    assert normalize_position("Setter")[0] == "SV"
    assert normalize_position("Outside hitter")[0] == "PL"
    assert normalize_position("Libero 2")[0] == "LIB"
    assert normalize_position("Mystery")[0] == "ONBEKEND"


def test_review_placeholder_has_plain_language_warning():
    assert normalize_position("Controleren - voorstel: setter") == ("ONBEKEND", "Positie controleren.")
