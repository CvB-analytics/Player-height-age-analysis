from __future__ import annotations

from io import BytesIO
from math import ceil, floor
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#277DA1")
LIGHT = colors.HexColor("#EAF2F8")
GRID = colors.HexColor("#D9E2EC")
TEXT = colors.HexColor("#243B53")
PALETTE = ["#277DA1", "#F94144", "#90BE6D", "#8E6BBE", "#F8961E", "#43AA8B"]


def create_pdf_report(report: dict[str, Any]) -> bytes:
    output = BytesIO()
    page_width, page_height = landscape(A4)
    c = canvas.Canvas(output, pagesize=(page_width, page_height))
    c.setTitle(f"{report['tournament']['name']} - toernooioverzicht")
    _header(c, report, page_width, page_height)
    _metrics(c, report, page_width, page_height)
    _tables(c, report, page_width, page_height)
    _charts(c, report, page_width)
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#52606D"))
    source = report["tournament"].get("source_file") or "Lokale toernooidata"
    c.drawString(28, 14, f"Bron: {source}")
    c.drawRightString(page_width - 28, 14, "Lokaal gegenereerd - geen gegevens verzonden")
    c.showPage()
    c.save()
    return output.getvalue()


def _header(c: canvas.Canvas, report: dict[str, Any], width: float, height: float) -> None:
    tournament = report["tournament"]
    c.setFillColor(NAVY)
    c.rect(0, height - 62, width, 62, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 19)
    c.drawString(28, height - 30, tournament["name"])
    c.setFont("Helvetica", 9)
    context = f"{tournament['category']} | {tournament['location']} | start {tournament['start_date']}"
    c.drawString(28, height - 47, context)


def _metrics(c: canvas.Canvas, report: dict[str, Any], width: float, height: float) -> None:
    summary = report["summary"]
    items = [
        ("Teams", summary["teams"], ""),
        ("Spelers", summary["players"], ""),
        ("Gem. leeftijd", summary["avg_age"], "0.00"),
        ("Gem. lengte", summary["avg_height"], "0.0 cm"),
    ]
    gap = 12
    card_width = (width - 56 - gap * 3) / 4
    y = height - 119
    for index, (label, value, fmt) in enumerate(items):
        x = 28 + index * (card_width + gap)
        c.setFillColor(LIGHT)
        c.roundRect(x, y, card_width, 43, 6, fill=1, stroke=0)
        c.setFillColor(NAVY)
        c.setFont("Helvetica", 8)
        c.drawString(x + 10, y + 29, label)
        c.setFont("Helvetica-Bold", 15)
        if value is None:
            shown = "n.a."
        elif fmt == "0.00":
            shown = f"{value:.2f}"
        elif fmt == "0.0 cm":
            shown = f"{value:.1f} cm"
        else:
            shown = str(value)
        c.drawString(x + 10, y + 9, shown)


def _tables(c: canvas.Canvas, report: dict[str, Any], width: float, height: float) -> None:
    result_map = {row["country_code"]: row for row in report["results"]}
    country_rows = []
    for row in report["countries"]:
        country_rows.append([
            row["country_code"], _shown(result_map.get(row["country_code"], {}).get("ranking")), row["players"],
            _shown(row["avg_age"], 2), _shown(row["avg_net_height"], 1), row["Q1"], row["Q2"], row["Q3"], row["Q4"],
        ])
    team_count = len(country_rows)
    chart_y, chart_height = _chart_layout(team_count)
    table_top = height - 151
    available_table_height = table_top - (chart_y + chart_height + 10)
    country_row_height = min(15, max(8, available_table_height / max(1, team_count + 1)))
    country_font_size = min(7, max(5.5, country_row_height - 4))
    _draw_table(
        c, 28, height - 151, ["Land", "Rank", "Spelers", "Leeftijd", "Netlengte", "Q1", "Q2", "Q3", "Q4"],
        country_rows, [38, 34, 43, 50, 56, 30, 30, 30, 30], country_row_height, country_font_size,
    )

    position_rows = [[r["position"], r["players"], _shown(r["avg_height"], 1), _shown(r["avg_age"], 2)] for r in report["positions"]]
    _draw_table(c, 402, height - 151, ["Positie", "#", "Lengte", "Leeftijd"], position_rows, [58, 34, 52, 52], 15)

    correlations = report["correlations"]
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(620, height - 151, "Rankinganalyse")
    analysis = [
        ("Ranking-lengte", correlations["ranking_height"]),
        ("Ranking-leeftijd", correlations["ranking_age"]),
    ]
    y = height - 171
    for label, value in analysis:
        c.setFillColor(LIGHT)
        c.roundRect(620, y - 3, 192, 18, 3, fill=1, stroke=0)
        c.setFillColor(TEXT)
        c.setFont("Helvetica", 8)
        c.drawString(628, y + 2, label)
        c.setFont("Helvetica-Bold", 9)
        shown = f"{value:.3f}" if value is not None else "Nog niet beschikbaar"
        c.drawRightString(803, y + 2, shown)
        y -= 23
    c.setFillColor(colors.HexColor("#52606D"))
    c.setFont("Helvetica-Oblique", 7)
    note = "Negatief: een hogere waarde hangt samen met een betere (lagere) ranking. Geen oorzakelijk verband."
    _draw_wrapped(c, note, 620, y + 3, 190, 8)

    position_bottom = height - 151 - (len(position_rows) + 1) * 15
    birth_top = min(height - 254, position_bottom - 10)
    birth_bottom = chart_y + chart_height + 8
    _draw_birth_year_table(c, report["birth_years"], 402, birth_top, 410, birth_bottom)


def _draw_birth_year_table(
    c: canvas.Canvas,
    birth_years: dict[int, int],
    x: float,
    top: float,
    width: float,
    bottom: float,
) -> None:
    items = sorted((int(year), int(count)) for year, count in birth_years.items())
    if not items or top <= bottom + 24:
        return
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x, top, "Aantal spelers per geboortejaar")

    table_top = top - 8
    row_height = 11
    rows_per_block = max(1, int((table_top - bottom) // row_height) - 1)
    block_count = max(1, ceil(len(items) / rows_per_block))
    block_width = width / block_count
    year_width = block_width * 0.62
    count_width = block_width - year_width
    for block_index in range(block_count):
        block_rows = items[block_index * rows_per_block : (block_index + 1) * rows_per_block]
        block_x = x + block_index * block_width
        _draw_table(
            c,
            block_x,
            table_top,
            ["Jaar", "#"],
            block_rows,
            [year_width, count_width],
            row_height,
            6.5,
        )


def _draw_table(c, x, top, headers, rows, widths, row_height, font_size=7) -> None:
    total_width = sum(widths)
    c.setFillColor(NAVY)
    c.rect(x, top - row_height, total_width, row_height, fill=1, stroke=0)
    cursor = x
    c.setFont("Helvetica-Bold", font_size)
    c.setFillColor(colors.white)
    for header, col_width in zip(headers, widths):
        c.drawCentredString(cursor + col_width / 2, top - row_height + max(2.5, (row_height - font_size) / 2), header)
        cursor += col_width
    for row_index, row in enumerate(rows):
        y = top - row_height * (row_index + 2)
        c.setFillColor(colors.white if row_index % 2 else LIGHT)
        c.rect(x, y, total_width, row_height, fill=1, stroke=0)
        cursor = x
        c.setFont("Helvetica", font_size)
        c.setFillColor(TEXT)
        for value, col_width in zip(row, widths):
            text = str(value if value is not None else "")
            while stringWidth(text, "Helvetica", font_size) > col_width - 5 and text:
                text = text[:-1]
            c.drawCentredString(cursor + col_width / 2, y + max(2.5, (row_height - font_size) / 2), text)
            cursor += col_width
        c.setStrokeColor(GRID)
        c.line(x, y, x + total_width, y)


def _charts(c: canvas.Canvas, report: dict[str, Any], width: float) -> None:
    countries = report["countries"]
    chart_y, chart_height = _chart_layout(len(countries))
    _bar_panel(c, 28, chart_y, 380, chart_height, "Geboortekwartaal alle spelers", list(report["quarters"]), list(report["quarters"].values()), 0, None)
    values = [r["avg_net_height"] for r in countries]
    available = [value for value in values if value is not None]
    y_min = max(0, floor(min(available) / 5) * 5 - 5) if available else 0
    y_max = ceil(max(available) / 5) * 5 + 5 if available else 200
    _bar_panel(c, 430, chart_y, 382, chart_height, "Gem. lengte netspelers per land", [r["country_code"] for r in countries], values, y_min, y_max)


def _chart_layout(team_count: int) -> tuple[float, float]:
    """Keep a one-page A4 overview while reserving enough room for larger country tables."""
    return (36, 238) if team_count <= 9 else (28, 200)


def _bar_panel(c, x, y, panel_width, panel_height, title, labels, values, y_min, y_max) -> None:
    c.setStrokeColor(GRID)
    c.setFillColor(colors.white)
    c.roundRect(x, y, panel_width, panel_height, 8, fill=1, stroke=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x + panel_width / 2, y + panel_height - 18, title)
    plot_x, plot_y = x + 38, y + 31
    plot_w, plot_h = panel_width - 54, panel_height - 66
    numeric = [float(v or 0) for v in values]
    maximum = y_max if y_max is not None else max(5, ceil(max(numeric) / 5) * 5 + 5)
    span = max(1, maximum - y_min)
    for step in range(5):
        value = y_min + span * step / 4
        grid_y = plot_y + plot_h * step / 4
        c.setStrokeColor(GRID)
        c.line(plot_x, grid_y, plot_x + plot_w, grid_y)
        c.setFillColor(colors.HexColor("#6B7C93"))
        c.setFont("Helvetica", 6)
        c.drawRightString(plot_x - 5, grid_y - 2, f"{value:.0f}")
    slot = plot_w / max(1, len(labels))
    bar_width = min(38, slot * 0.55)
    label_font = 7 if len(labels) <= 12 else max(5, 7 - (len(labels) - 12) * 0.18)
    for index, (label, value) in enumerate(zip(labels, numeric)):
        bar_x = plot_x + index * slot + (slot - bar_width) / 2
        bar_h = max(0, (value - y_min) / span * plot_h)
        c.setFillColor(colors.HexColor(PALETTE[index % len(PALETTE)]))
        c.rect(bar_x, plot_y, bar_width, bar_h, fill=1, stroke=0)
        c.setFillColor(TEXT)
        c.setFont("Helvetica-Bold", label_font)
        shown = f"{value:.0f}"
        c.drawCentredString(bar_x + bar_width / 2, plot_y + bar_h + 4, shown)
        c.setFont("Helvetica", label_font)
        c.drawCentredString(bar_x + bar_width / 2, plot_y - 11, str(label))


def _draw_wrapped(c, text: str, x: float, y: float, width: float, leading: float) -> None:
    words = text.split()
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if stringWidth(candidate, "Helvetica-Oblique", 7) <= width:
            line = candidate
        else:
            c.drawString(x, y, line)
            y -= leading
            line = word
    if line:
        c.drawString(x, y, line)


def _shown(value: Any, decimals: int | None = None) -> str:
    if value is None:
        return "-"
    if decimals is None:
        return str(value)
    return f"{float(value):.{decimals}f}"
