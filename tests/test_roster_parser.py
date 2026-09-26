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


def test_synthetic_bulletin_integration(synthetic_bulletin):
    result = parse_bulletin(str(synthetic_bulletin))
    assert len(result.teams) == 6
    assert len(result.players) == 82
    assert result.date_order == "DMY"
