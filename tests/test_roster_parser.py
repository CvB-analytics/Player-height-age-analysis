from src.parser.roster_parser import CEVRosterParser, FIVBRosterParser, parse_bulletin


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
