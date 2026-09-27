from datetime import date

from src.ui.import_review import _apply_editor_patch, _team_counts


def _row(land: str, rugnr: int, name: str) -> dict:
    return {
        "Land": land,
        "Rugnr": rugnr,
        "Achternaam": name,
        "Voornaam": "Test",
        "Positie": "Setter",
        "Geboortedatum": "2009-01-01",
        "Lengte": 180,
        "Opmerking": "",
    }


def test_added_player_moves_to_its_team_and_updates_counts():
    records = [_row("ESP", 2, "Bravo"), _row("NED", 3, "Delta")]
    state = {"edited_rows": {}, "deleted_rows": [], "added_rows": [_row("ESP", 1, "Alpha")]}

    result = _apply_editor_patch(records, state, date(2026, 8, 25))

    assert list(zip(result["Land"], result["Rugnr"])) == [("ESP", 1), ("ESP", 2), ("NED", 3)]
    assert _team_counts(result) == {"ESP": 2, "NED": 1}


def test_blank_country_stays_visible_and_is_marked_for_review():
    result = _apply_editor_patch([], {"added_rows": [_row("", 7, "Unknown")]}, date(2026, 8, 25))

    assert len(result) == 1
    assert "Land ontbreekt" in result.iloc[0]["Opmerking"]
    assert _team_counts(result) == {"Nog zonder land": 1}
