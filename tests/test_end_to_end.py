from datetime import date
from io import BytesIO
from openpyxl import load_workbook

from src.parser.roster_parser import parse_bulletin
from src.reports.calculations import build_report_data
from src.reports.excel_export import create_excel_report
from src.reports.pdf_export import create_pdf_report
from src.storage.database import Database


def test_pdf_database_report_roundtrip(tmp_path, synthetic_bulletin):
    result = parse_bulletin(str(synthetic_bulletin))
    db = Database(tmp_path / "app.db")
    tournament_id = db.create_tournament(
        {
            "name": "WEVZA U20",
            "category": "U20",
            "gender": "Women",
            "location": "Terville",
            "start_date": date(2026, 8, 25),
            "source_file": synthetic_bulletin.name,
        }
    )
    db.save_players(tournament_id, result.as_records())
    teams = db.get_teams(tournament_id)
    players = db.get_players(tournament_id)
    assert len(teams) == 6
    assert len(players) == 82

    db.save_ranking(tournament_id, {team["id"]: rank for rank, team in enumerate(teams, 1)})
    report = build_report_data(db.get_tournament(tournament_id), db.get_teams(tournament_id), players)
    workbook = load_workbook(BytesIO(create_excel_report(report)))
    assert workbook.sheetnames == ["Overzicht", "Spelers", "Resultaten"]
    assert workbook["Spelers"].max_row == 83
    charts = workbook["Overzicht"]._charts
    assert len(charts) == 2
    assert all(chart.legend is None for chart in charts)
    assert all(chart.dLbls.showVal is True for chart in charts)
    assert all(chart.dLbls.showSerName is False for chart in charts)
    assert all(chart.dLbls.showCatName is False for chart in charts)
    assert all(chart.dLbls.numFmt == "0" for chart in charts)
    height_chart = charts[0]
    assert height_chart.x_axis.title.tx.rich.p[0].r[0].t == "Land"
    assert height_chart.y_axis.title.tx.rich.p[0].r[0].t == "Lengte (cm)"
    assert height_chart.y_axis.majorUnit == 2
    assert workbook["Overzicht"].page_setup.fitToWidth == 1
    assert workbook["Overzicht"].print_area == "'Overzicht'!$A$1:$N$39"
    pdf = create_pdf_report(report)
    assert pdf.startswith(b"%PDF")
