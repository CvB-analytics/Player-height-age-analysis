from datetime import date

from src.reports.calculations import age_on_date, birth_quarter, build_report_data, pearson


def test_age_and_quarter():
    assert age_on_date(date(2008, 8, 25), date(2026, 8, 25)) == 18.0
    assert birth_quarter(date(2008, 1, 1)) == "Q1"
    assert birth_quarter(date(2008, 12, 31)) == "Q4"


def test_net_height_excludes_libero_and_pearson():
    tournament = {"name": "Test", "category": "U20", "gender": "Women", "location": "X", "start_date": "2026-08-25"}
    teams = [
        {"id": 1, "country_code": "AAA", "country_name": "A", "final_ranking": 1},
        {"id": 2, "country_code": "BBB", "country_name": "B", "final_ranking": 2},
        {"id": 3, "country_code": "CCC", "country_name": "C", "final_ranking": 3},
    ]
    players = [
        {"id": 1, "country_code": "AAA", "country_name": "A", "position_normalized": "MB", "birth_date": "2008-01-01", "height_cm": 190, "last_name": "A", "first_name": "A", "jersey_number": 1},
        {"id": 2, "country_code": "AAA", "country_name": "A", "position_normalized": "LIB", "birth_date": "2008-02-01", "height_cm": 150, "last_name": "B", "first_name": "B", "jersey_number": 2},
        {"id": 3, "country_code": "BBB", "country_name": "B", "position_normalized": "MB", "birth_date": "2008-03-01", "height_cm": 180, "last_name": "C", "first_name": "C", "jersey_number": 1},
        {"id": 4, "country_code": "CCC", "country_name": "C", "position_normalized": "SV", "birth_date": "2008-04-01", "height_cm": 170, "last_name": "D", "first_name": "D", "jersey_number": 1},
    ]
    report = build_report_data(tournament, teams, players)
    assert report["countries"][0]["avg_net_height"] == 190.0
    assert round(report["correlations"]["ranking_height"], 6) == -1.0
    assert round(pearson([1, 2, 3], [3, 2, 1]), 6) == -1.0


def test_report_output_is_sorted_by_ranking_with_unranked_teams_last():
    tournament = {"name": "Test", "category": "U20", "gender": "Women", "location": "X", "start_date": "2026-08-25"}
    teams = [
        {"id": 1, "country_code": "AAA", "country_name": "A", "final_ranking": 3},
        {"id": 2, "country_code": "BBB", "country_name": "B", "final_ranking": 1},
        {"id": 3, "country_code": "CCC", "country_name": "C", "final_ranking": None},
        {"id": 4, "country_code": "DDD", "country_name": "D", "final_ranking": 2},
    ]
    players = [
        {"id": index, "country_code": code, "country_name": code, "position_normalized": "MB", "birth_date": "2008-01-01", "height_cm": 180 + index, "last_name": code, "first_name": code, "jersey_number": 1}
        for index, code in enumerate(("AAA", "BBB", "CCC", "DDD"), 1)
    ]

    report = build_report_data(tournament, teams, players)

    assert [row["country_code"] for row in report["countries"]] == ["BBB", "DDD", "AAA", "CCC"]
    assert [row["ranking"] for row in report["countries"]] == [1, 2, 3, None]
    assert [row["ranking"] for row in report["results"]] == [1, 2, 3, None]
