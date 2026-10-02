from collections import Counter
from datetime import date

import src.parser.roster_parser as roster_parser
from src.parser.roster_parser import (
    CEVRosterParser,
    FIVBRosterParser,
    ParsedPlayer,
    ParseResult,
    _add_missing_concept_rows,
    _reconcile_duplicate_players,
    parse_bulletin,
)


def test_cev_player_line_recognition():
    page = """CEV U20 Volleyball European Championship 2027 | Women
SPAIN   (ESP)
FINAL TEAM LIST AND DELEGATION
N° Name & First Name Position Birth Date Weight Height Standing Reach Spike Reach Last Club
3 POLO MARTÍNEZ Bianca Libero 1 04/11/08 50 158 235 230 Club Name (ESP)
4 BUSQUETS PLANS Anna Setter 21/05/08 67 182 235 298 Club Name (ESP)
TEAM OFFICIAL
"""
    result = CEVRosterParser().parse([page])
    assert len(result.players) == 2
    assert result.players[0].last_name == "POLO MARTÍNEZ"
    assert result.players[0].height_cm == 158
    assert result.players[1].position_normalized == "SV"


def test_fivb_team_composition_profile_recognizes_named_month_dates():
    page = """FIVB Volleyball Women's U21 World Championship
Team composition
ARG ● Argentina
PLAYERS
Shirt no Last name First name Shirt name Pos. Birthdate Height [cm]
1 Perez Dalma Nicole Perez OH 01-Apr-2004 181 295 295 GELP (ARG)
2 Balague Emilia Balague S 08-Dec-2004 181 289 270 Villa Dora (ARG)
7 Perez Sain Constanza Perez Sain OP 15-Dec-2004 184 298 288 UPCN (ARG)
10 Garcia Avril Garcia MB 26-Sep-2004 186 304 280 GELP (ARG)
20 C Caballero Victoria Caballero L 01-Aug-2004 168 275 250 River Plate (ARG)
OFFICIALS"""

    parser = FIVBRosterParser()
    assert parser.supports([page])

    result = parser.parse([page])

    assert result.profile == "FIVB"
    assert result.date_order == "DMY"
    assert len(result.players) == 5
    assert result.teams == [{"country_code": "ARG", "country_name": "Argentina"}]
    assert result.players[0].birth_date.isoformat() == "2004-04-01"
    assert result.players[0].height_cm == 181
    assert result.players[0].position_normalized == "PL"
    assert result.players[-1].position_normalized == "LIB"


def test_fivb_registration_profile_recognizes_id_and_eligibility_columns():
    page = """Women's Volleyball Nations League 2025
O-2bis Team registration
FRA - France
No FIVB Elig. FoO Shirt Role Last name First name Shirt name Pos. Birthdate Height [cm]
168983 R l 1 C Cazaute Héléna Cazaute OH 17-Dec-1997 184 305 285 Club
162899 R l 3 L Giardino Amandine Giardino L 30-Mar-1995 172 275 260 Club
179014 R l 7 Ndiaye Iman Ndiaye OP 13-Jan-2002 188 315 302 Club
162903 R l 9 Stojiljkovic Nina Stojiljkovic S 01-Sep-1996 180 285 274 Club
210294 R l 10 Fanguedou Fatoumata Fanguedou MB 27-Jun-2003 186 309 284 Club
OFFICIALS"""

    result = FIVBRosterParser().parse([page])

    assert result.profile == "FIVB"
    assert len(result.players) == 5
    assert result.teams == [{"country_code": "FRA", "country_name": "France"}]
    assert [player.jersey_number for player in result.players] == [1, 3, 7, 9, 10]
    assert [player.height_cm for player in result.players] == [184, 172, 188, 180, 186]


def test_fivb_reserve_players_are_excluded():
    page = """Volleyball Nations League
O-2bis Team registration
TST - Testland
No FIVB Shirt Last name First name Pos. Birthdate Height
168983 1 Alpha Anna S 17-Dec-1997 184
162899 3 Beta Bea L 30-Mar-1995 172
RESERVE PLAYERS
179014 7 Gamma Gina OP 13-Jan-2002 188
OFFICIALS"""

    result = FIVBRosterParser().parse([page])

    assert [player.jersey_number for player in result.players] == [1, 3]


def test_fivb_table_columns_are_detected_by_header_name():
    table = [
        ["No FIVB", "Elig.", "FoO", "Shirt", "Role", "Last name", "First name", "Shirt name", "Pos.", "Birthdate", "Height\n[cm]"],
        ["168983", "R", "l", "1", "C", "Cazaute", "Héléna", "Cazaute", "OH", "17-Dec-1997", "184"],
        ["162899", "R", "l", "3", "L", "Giardino", "Amandine", "Giardino", "L", "30-Mar-1995", "172"],
    ]

    rows = FIVBRosterParser._rows_from_tables([table])

    assert rows == [
        (1, "Cazaute", "Héléna", "OH", "17-Dec-1997", 184),
        (3, "Giardino", "Amandine", "L", "30-Mar-1995", 172),
    ]


def test_fivb_geometric_and_logical_ocr_rows_are_deduplicated():
    page = """174474 5 Yordanova Maria Yordanova OH 25-May-2002 184
174474 5 Yordanova Maria Yordanova OH 25-May-2002 184"""

    rows = FIVBRosterParser._rows_from_text(page)

    assert rows == [(5, "Yordanova", "Maria", "OH", "25-May-2002", 184)]


def test_fivb_damaged_scan_rows_are_added_for_review():
    page = """Volleyball Nations League 2024
O-2bis Team registration
BUL - Bulgaria
No FIVB Elig. Shirt Role Last name First name Shirt name Pos. Birthdate Height [cm]
174474 check 5 Yordanova Maria Yordanova 0H 25-May-2002 184 295 283 Club
142347 check 6 Paskova Miroslava Paskova 0H 16-Feb-1996 181 299 280 Club
142348 check 8 Barakova Petya Barakova S 18-Jun-1994 180 299 271 Club
OFFICIALS"""

    result = FIVBRosterParser().parse([page])

    assert len(result.players) == 3
    assert [player.jersey_number for player in result.players] == [8, 5, 6]
    assert {player.position_normalized for player in result.players} == {"SV", "PL"}
    assert all(player.extraction_status == "Controleren" for player in result.players if player.jersey_number in {5, 6})
    assert any("extra regel(s) uit de scan toegevoegd" in warning for warning in result.warnings)


def test_fivb_scan_page_survives_missing_registration_heading():
    page = """FIVB roster scan
BUL - Bulgaria
No FIVB Shirt Last name First name Pos. Birthdate Height
174474 5 Yordanova Maria Yordanova OH 25-May-2002 184
142347 6 Paskova Miroslava Paskova OH 16-Feb-1996 181
142348 8 Barakova Petya Barakova S 18-Jun-1994 180
OFFICIALS"""

    assert FIVBRosterParser._is_roster_page(page) is True


def test_detected_but_unreadable_rows_become_editable_concepts():
    result = ParseResult(
        profile="FIVB",
        date_order="AMBIGUOUS",
        players=[],
        teams=[
            {"country_code": "BUL", "country_name": "Bulgaria"},
            {"country_code": "NED", "country_name": "Netherlands"},
        ],
        warnings=[
            "Geen spelersregels gevonden. Controleer of dit een ondersteund CEV/WEVZA-bulletin is.",
            "VOLLEDIGHEIDSCONTROLE: BUL bevat circa 10 spelersregels, maar er zijn 0 herkend. Controleer en vul ontbrekende spelers aan.",
            "VOLLEDIGHEIDSCONTROLE: NED bevat circa 8 spelersregels, maar er zijn 0 herkend. Controleer en vul ontbrekende spelers aan.",
        ],
    )

    repaired = _add_missing_concept_rows(result)

    assert len(repaired.players) == 18
    assert Counter(player.country_code for player in repaired.players) == {"BUL": 10, "NED": 8}
    assert repaired.date_order == "DMY"
    assert all(player.extraction_status == "Controleren" for player in repaired.players)
    assert not any(warning.startswith("Geen spelersregels gevonden.") for warning in repaired.warnings)
    assert any("10 onzekere conceptregel(s)" in warning for warning in repaired.warnings)


def _player(
    jersey: int,
    last_name: str,
    first_name: str,
    birth_date: date,
    height: int,
    status: str = "OK",
) -> ParsedPlayer:
    return ParsedPlayer(
        country_code="BUL",
        country_name="Bulgaria",
        jersey_number=jersey,
        last_name=last_name,
        first_name=first_name,
        full_name_original=f"{last_name} {first_name}".strip(),
        position_original="Outside spiker",
        position_normalized="PL",
        raw_birth_date=birth_date.isoformat(),
        birth_date=birth_date,
        height_cm=height,
        extraction_status=status,
        extraction_warning="" if status == "OK" else "Controleren",
    )


def test_shifted_scan_variant_is_merged_with_clean_player_row():
    damaged = _player(4, "10 Exampleva Alina", "", date(1997, 7, 19), 185, "Controleren")
    clean = _player(10, "EXAMPLEVA", "Alina", date(1997, 7, 19), 185)
    result = ParseResult("FIVB", "DMY", [damaged, clean], [], [])

    reconciled = _reconcile_duplicate_players(result)

    assert reconciled.players == [clean]


def test_same_birth_date_does_not_merge_different_players():
    first = _player(7, "ALPHA", "Anna", date(2005, 6, 10), 180)
    second = _player(12, "BETA", "Bea", date(2005, 6, 10), 180)
    result = ParseResult("FIVB", "DMY", [first, second], [], [])

    reconciled = _reconcile_duplicate_players(result)

    assert reconciled.players == [first, second]


def test_shifted_rows_are_repaired_even_without_a_clean_duplicate():
    combined = _player(4, "3 Sampleva Eva", "", date(1996, 1, 2), 190, "Controleren")
    moved_name = _player(4, "62", "Reserveva Rita", date(1998, 10, 21), 174, "Controleren")
    compound_first = _player(4, "14 Double Name First", "Second", date(1998, 6, 27), 177, "Controleren")
    result = ParseResult("FIVB", "DMY", [combined, moved_name, compound_first], [], [])

    reconciled = _reconcile_duplicate_players(result)

    assert [player.jersey_number for player in reconciled.players] == [3, 62, 14]
    assert (combined.last_name, combined.first_name) == ("Sampleva", "Eva")
    assert (moved_name.last_name, moved_name.first_name) == ("Reserveva", "Rita")
    assert (compound_first.last_name, compound_first.first_name) == ("Double Name", "First Second")


def test_shirt_number_glued_to_role_marker_is_recovered():
    shifted = _player(0, "MW 6C", "Sampleva Sara", date(1998, 2, 16), 181, "Controleren")
    result = ParseResult("FIVB", "DMY", [shifted], [], [])

    reconciled = _reconcile_duplicate_players(result)

    assert reconciled.players[0].jersey_number == 6
    assert reconciled.players[0].last_name == "Sampleva"
    assert reconciled.players[0].first_name == "Sara"


def test_wrapped_first_name_is_inserted_before_position():
    page = """FRANCE (FRA)
FINAL TEAM LIST AND DELEGATION
Name & First Name Position Birth Date Weight Height
9 MELINARD-CHANTEUR Outside spiker 14/11/07 61 183 Club (FRA)
Maelyss
TEAM OFFICIALS:"""

    result = CEVRosterParser().parse([page])

    assert len(result.players) == 1
    assert result.players[0].last_name == "MELINARD-CHANTEUR"
    assert result.players[0].first_name == "Maelyss"


def test_short_and_damaged_outside_position_labels_are_normalized():
    page = """TESTLAND (TST)
FINAL TEAM LIST AND DELEGATION
Name & First Name Position Birth Date Weight Height
1 ALPHA Anna OH 13/03/09 65 180
2 BETA Bea Outslde splker 14/03/09 66 181
3 GAMMA Gina S 15/03/09 67 182
TEAM OFFICIALS:"""

    result = CEVRosterParser().parse([page])

    assert [player.position_normalized for player in result.players] == ["PL", "PL", "SV"]


def test_parse_bulletin_prefers_fivb_when_scan_contains_mixed_markers(monkeypatch):
    page = """FINAL TEAM LIST
O-2bis Team registration
BUL - Bulgaria
No FIVB Shirt Last name First name Pos. Birthdate Height
174474 5 Yordanova Maria Yordanova OH 25-May-2002 184
142347 6 Paskova Miroslava Paskova OH 16-Feb-1996 181
142348 8 Barakova Petya Barakova S 18-Jun-1994 180
OFFICIALS"""
    monkeypatch.setattr(roster_parser, "extract_pages", lambda _: [page])

    result = parse_bulletin(b"not-a-real-pdf")

    assert result.profile == "FIVB"
    assert len(result.players) == 3


def test_parser_profile_is_selected_by_evidence_not_list_order(monkeypatch):
    page = """FIVB international event
TESTLAND (TST)
FINAL TEAM LIST AND DELEGATION
Shirt\tName & First Name\tPosition\tBirth Date\tHeight
1\tALPHA Anna\tSetter\t13/03/09\t180
2\tBETA Bea\tMiddle blocker\t04/07/09\t188
3\tGAMMA Gina\tLibero\t11/11/09\t170
"""
    monkeypatch.setattr(roster_parser, "extract_pages", lambda _: [page])

    result = parse_bulletin(b"not-a-real-pdf")

    assert result.profile == "CEV/WEVZA"
    assert len(result.players) == 3


def test_fivb_roster_without_team_header_is_kept_for_review():
    page = """FIVB Volleyball Nations League
Team registration
No FIVB Elig. FoO Shirt Role Last name First name Shirt name Pos. Birthdate Height [cm]
168983 R l 1 C Cazaute Héléna Cazaute OH 17-Dec-1997 184 305 285 Club
162899 R l 3 L Giardino Amandine Giardino L 30-Mar-1995 172 275 260 Club
179014 R l 7 Ndiaye Iman Ndiaye OP 13-Jan-2002 188 315 302 Club
OFFICIALS"""

    result = FIVBRosterParser().parse([page])

    assert len(result.players) == 3
    assert {player.country_code for player in result.players} == {"PAA"}
    assert any("tijdelijke code PAA" in warning for warning in result.warnings)


def test_recognizes_roster_from_columns_without_exact_legacy_heading():
    page = """
INTERNATIONAL U18 EVENT
TESTLAND (TST)
TEAM ROSTER
Name & First Name Position Birth Date Weight Height
1 ALPHA Anna Setter 13/03/09 65 180
2 BETA Bea Middle blocker 04/07/09 70 188
3 GAMMA Gina Libero 1 11/11/09 58 170
TEAM OFFICIALS:
"""
    parser = CEVRosterParser()

    assert parser.supports([page])
    result = parser.parse([page])
    assert result.date_order == "DMY"
    assert len(result.players) == 3


def test_team_header_tolerates_broken_unicode_and_ocr_digit_in_code():
    pages = [
        """T�RKIYE (TUR)
FINAL TEAM LIST AND DELEGATION
Name & First Name Position Birth Date Weight Height
1 ALPHA Anna Setter 13/03/09 65 180
2 BETA Bea Middle blocker 04/07/09 70 188
3 GAMMA Gina Libero 1 11/11/09 58 170
TEAM OFFICIALS:""",
        """ICELAND (1SL)
FINAL TEAM LIST AND DELEGATION
Name & First Name Position Birth Date Weight Height
| 4 DELTA Dora Setter 15/03/10 60 178
5 EPSILON Eva Middie blocker 15/05/10 65 183
6 ZETA Zoë Outside splker 28/12/09 70 176
TEAM OFFICIALS:""",
    ]

    result = CEVRosterParser().parse(pages)

    assert [team["country_code"] for team in result.teams] == ["TUR", "ISL"]
    assert len(result.players) == 6
    assert not any(warning.startswith("VOLLEDIGHEIDSCONTROLE:") for warning in result.warnings)


def test_unknown_position_row_is_kept_for_manual_correction():
    page = """TESTLAND (TST)
FINAL TEAM LIST AND DELEGATION
Name & First Name Position Birth Date Weight Height
1 ALPHA Anna Setter 13/03/09 65 180
2 BETA Bea Unknown role 04/07/09 70 188
3 GAMMA Gina Libero 1 11/11/09 58 170
TEAM OFFICIALS:"""

    result = CEVRosterParser().parse([page])

    assert len(result.players) == 3
    uncertain = result.players[1]
    assert uncertain.position_normalized == "ONBEKEND"
    assert uncertain.extraction_status == "Controleren"
    assert "Onbekende positie" in uncertain.extraction_warning
    assert not any(warning.startswith("VOLLEDIGHEIDSCONTROLE: TST") for warning in result.warnings)


def test_roster_without_team_header_uses_temporary_page_team():
    page = """FINAL TEAM LIST AND DELEGATION
Name & First Name Position Birth Date Weight Height
1 ALPHA Anna Setter 13/03/09 65 180
2 BETA Bea Middle blocker 04/07/09 70 188
3 GAMMA Gina Libero 1 11/11/09 58 170
TEAM OFFICIALS:"""

    result = CEVRosterParser().parse([page])

    assert result.teams == [{"country_code": "P01", "country_name": "Onbekend team pagina 1"}]
    assert len(result.players) == 3
    assert {player.country_code for player in result.players} == {"P01"}
    assert any("tijdelijke code P01" in warning for warning in result.warnings)


def test_date_rows_with_damaged_or_missing_jersey_are_added_as_concepts():
    page = """SCANLAND (SCN)
FINAL TEAM LIST AND DELEGATION
Name & First Name Position Birth Date Weight Height
1 ALPHA Anna Setter 13/03/09 65 180 230 290
S BETA Bea Middle blocker 04/07/09 70 188 240 300
GAMMA Gina Outside spiker 11/11/09 68 176 225 285
4 DELTA Dora Libero 15/03/10 58 170 215 270
TEAM OFFICIALS:"""

    result = CEVRosterParser().parse([page])

    assert len(result.players) == 4
    concepts = [player for player in result.players if player.position_original.startswith("Controleren")]
    assert len(concepts) == 2
    assert concepts[0].jersey_number == 5
    assert concepts[0].height_cm == 188
    assert concepts[1].jersey_number is None
    assert concepts[1].height_cm == 176
    assert all(player.extraction_status == "Controleren" for player in concepts)
    assert any("2 extra regel(s)" in warning for warning in result.warnings)
    assert not any(warning.startswith("VOLLEDIGHEIDSCONTROLE: SCN") for warning in result.warnings)


def test_height_uses_first_plausible_value_when_scan_columns_shift():
    page = """SCANLAND (SCN)
FINAL TEAM LIST AND DELEGATION
Name & First Name Position Birth Date Weight Height
1 ALPHA Anna Setter 13/03/09 1 178 227 271
2 BETA Bea Middle blocker 04/07/09 176 1 220 274
3 GAMMA Gina Libero 11/11/09 58 170 215 270
TEAM OFFICIALS:"""

    result = CEVRosterParser().parse([page])

    assert [player.height_cm for player in result.players] == [178, 176, 170]


def test_synthetic_bulletin_integration(synthetic_bulletin):
    result = parse_bulletin(str(synthetic_bulletin))
    assert len(result.teams) == 6
    assert len(result.players) == 82
    assert result.date_order == "DMY"
