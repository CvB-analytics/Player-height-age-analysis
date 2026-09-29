from src.parser.roster_parser import FIVBRosterParser
from src.parser.structured_table import extract_structured_roster_rows


def _scanned_grid_page() -> str:
    rows = [
        ["No FIVB", "Elig.", "Courses", "Shirt", "Role", "Last name", "First name", "Shirt name", "Pos.", "Birthdate", "Height [cm]"],
        ["151857", "check", "", "8", "", "ALPHA", "Anna", "ALPHA", "S", "18-Jun-1994", "180"],
        ["164660", "check", "", "10", "", "BETA", "Bea", "BETA", "MB", "06-Sep-2001", "186"],
    ]
    return "\n".join(
        [
            "Volleyball Nations League",
            "TST - Testland",
            "O-2bis Team registration",
            "garbled prose OCR 151857 1997 strange words",
            *("\t".join(row) for row in rows),
        ]
    )


def test_structured_table_uses_header_columns_and_ignores_fivb_id():
    rows = extract_structured_roster_rows(_scanned_grid_page())

    assert len(rows) == 2
    assert rows[0].jersey_number == 8
    assert rows[0].last_name == "ALPHA"
    assert rows[0].first_name == "Anna"
    assert rows[0].raw_birth_date == "18-Jun-1994"
    assert rows[0].height_cm == 180


def test_fivb_parser_prefers_structured_cells_over_garbled_prose():
    result = FIVBRosterParser().parse([_scanned_grid_page()])

    assert [player.jersey_number for player in result.players] == [8, 10]
    assert [player.full_name_original for player in result.players] == ["ALPHA Anna", "BETA Bea"]
    assert result.players[0].birth_date.isoformat() == "1994-06-18"
    assert [player.height_cm for player in result.players] == [180, 186]
