from __future__ import annotations

import pandas as pd
import streamlit as st

from src.reports.calculations import build_report_data
from src.storage.database import Database


def render_results(db: Database) -> None:
    st.header("Resultaten / ranking")
    tournament_id = st.session_state.get("tournament_id")
    tournament = db.get_tournament(tournament_id) if tournament_id else None
    if not tournament:
        st.info("Maak of open eerst een toernooi.")
        return
    teams = db.get_teams(tournament_id)
    players = db.get_players(tournament_id)
    if not teams:
        st.info("Importeer eerst spelers en teams.")
        return
    frame = pd.DataFrame(
        [{"team_id": team["id"], "Land": team["country_code"], "Eindranking": team["final_ranking"]} for team in teams]
    )
    edited = st.data_editor(
        frame,
        hide_index=True,
        disabled=["team_id", "Land"],
        column_config={"team_id": None, "Eindranking": st.column_config.NumberColumn(min_value=1, max_value=len(teams), step=1)},
        use_container_width=True,
    )
    if st.button("Ranking opslaan", type="primary"):
        values = [int(v) for v in edited["Eindranking"].dropna().tolist()]
        if len(values) != len(set(values)):
            st.error("Elke ranking mag maar één keer voorkomen.")
        elif values and any(value < 1 or value > len(teams) for value in values):
            st.error(f"Gebruik rankings van 1 tot en met {len(teams)}.")
        else:
            rankings = {int(row["team_id"]): (int(row["Eindranking"]) if pd.notna(row["Eindranking"]) else None) for _, row in edited.iterrows()}
            db.save_ranking(tournament_id, rankings)
            st.success("De ranking is opgeslagen.")
            st.rerun()

    report = build_report_data(tournament, teams, players)
    correlations = report["correlations"]
    st.subheader("Analyse na eindranking")
    if correlations["ranking_height"] is None:
        st.info("Vul alle eindrankings in. Daarna verschijnen de correlaties automatisch.")
    else:
        c1, c2 = st.columns(2)
        c1.metric("Correlatie ranking-lengte", f"{correlations['ranking_height']:.3f}")
        c2.metric("Correlatie ranking-leeftijd", f"{correlations['ranking_age']:.3f}")
        st.caption("Negatief betekent dat een hogere gemiddelde waarde samenhangt met een betere (lagere) ranking. Correlatie beschrijft samenhang, geen oorzaak.")
