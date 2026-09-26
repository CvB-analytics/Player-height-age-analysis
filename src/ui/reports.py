from __future__ import annotations

import math

import pandas as pd
import streamlit as st
import altair as alt

from src.reports.calculations import build_report_data
from src.reports.excel_export import create_excel_report
from src.reports.pdf_export import create_pdf_report
from src.storage.database import Database


def render_reports(db: Database) -> None:
    st.header("Rapportage")
    tournament_id = st.session_state.get("tournament_id")
    tournament = db.get_tournament(tournament_id) if tournament_id else None
    if not tournament:
        st.info("Maak of open eerst een toernooi.")
        return
    teams = db.get_teams(tournament_id)
    players = db.get_players(tournament_id)
    if not players:
        st.info("Importeer eerst spelers.")
        return
    report = build_report_data(tournament, teams, players)
    summary = report["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Teams", summary["teams"])
    c2.metric("Spelers", summary["players"])
    c3.metric("Gem. leeftijd", f"{summary['avg_age']:.2f}" if summary["avg_age"] is not None else "n.a.")
    c4.metric("Gem. lengte", f"{summary['avg_height']:.1f} cm" if summary["avg_height"] is not None else "n.a.")
    st.subheader("Vergelijking landen")
    country_frame = pd.DataFrame(report["countries"]).rename(columns={
        "country_code": "Land", "players": "# spelers", "avg_age": "Gem. leeftijd", "avg_net_height": "Gem. lengte netspelers"
    })
    st.dataframe(country_frame[["Land", "# spelers", "Gem. leeftijd", "Gem. lengte netspelers", "Q1", "Q2", "Q3", "Q4"]], hide_index=True, use_container_width=True)
    chart_left, chart_right = st.columns(2)
    palette = ["#277DA1", "#F94144", "#90BE6D", "#8E6BBE", "#F8961E", "#43AA8B"]
    # Altair treats dots in field names as nested-property notation. Use a short
    # chart-only name so the country values are rendered instead of an empty axis.
    height_data = country_frame[["Land", "Gem. lengte netspelers"]].rename(columns={"Gem. lengte netspelers": "Lengte"})
    height_values = height_data["Lengte"].dropna()
    height_domain = [math.floor(float(height_values.min()) - 2), math.ceil(float(height_values.max()) + 2)]
    height_bars = alt.Chart(height_data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("Land:N", sort=None, title=None),
        y=alt.Y("Lengte:Q", scale=alt.Scale(domain=height_domain, zero=False, nice=False), title="Centimeter"),
        color=alt.Color("Land:N", scale=alt.Scale(range=palette), legend=None),
        tooltip=["Land", alt.Tooltip("Lengte:Q", title="Gem. lengte", format=".1f")],
    )
    height_labels = height_bars.mark_text(dy=-8, color="#C9D5E3").encode(text=alt.Text("Lengte:Q", format=".1f"))
    chart_left.altair_chart((height_bars + height_labels).properties(title="Gem. lengte netspelers per land", height=280), use_container_width=True)
    quarter_data = pd.DataFrame({"Kwartaal": ["Q1", "Q2", "Q3", "Q4"], "Spelers": [report["quarters"][q] for q in ("Q1", "Q2", "Q3", "Q4")]})
    quarter_bars = alt.Chart(quarter_data).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("Kwartaal:N", sort=None, title=None),
        y=alt.Y("Spelers:Q", title="Aantal spelers"),
        color=alt.Color("Kwartaal:N", scale=alt.Scale(range=palette[:4]), legend=None),
        tooltip=["Kwartaal", "Spelers"],
    )
    quarter_labels = quarter_bars.mark_text(dy=-8, color="#C9D5E3").encode(text="Spelers:Q")
    chart_right.altair_chart((quarter_bars + quarter_labels).properties(title="Geboortekwartaal alle spelers", height=280), use_container_width=True)
    safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in tournament["name"]).strip("_")
    excel = create_excel_report(report)
    pdf = create_pdf_report(report)
    download_left, download_right = st.columns(2)
    download_left.download_button(
        "Excel downloaden", data=excel, file_name=f"{safe_name or 'toernooi'}_rapport.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True,
    )
    download_right.download_button(
        "A4-PDF downloaden", data=pdf, file_name=f"{safe_name or 'toernooi'}_overzicht.pdf",
        mime="application/pdf", use_container_width=True,
    )
    st.caption("Excel bevat één gecombineerd, afdrukbaar A4-overzicht plus de tabbladen Spelers en Resultaten. De PDF bevat hetzelfde coachoverzicht op één pagina.")
