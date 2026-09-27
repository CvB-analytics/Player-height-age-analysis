from src.parser.roster_parser import CEVRosterParser, parse_bulletin


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


def test_synthetic_bulletin_integration(synthetic_bulletin):
    result = parse_bulletin(str(synthetic_bulletin))
    assert len(result.teams) == 6
    assert len(result.players) == 82
    assert result.date_order == "DMY"
