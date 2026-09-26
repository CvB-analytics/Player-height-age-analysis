from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.storage.database import Database
from src.validation.import_validator import validate_import


def render_tournaments(db: Database) -> None:
    st.header("Toernooien")
    tournaments = db.get_tournaments()
    if not tournaments:
        st.info("Er zijn nog geen toernooien. Kies links 'Nieuw toernooi'.")
        return
    labels = {row["id"]: f"{row['name']} ({row['start_date']})" for row in tournaments}
    selected = st.selectbox("Open toernooi", list(labels), format_func=labels.get, key="tournament_select")
    st.session_state["tournament_id"] = selected
    tournament = db.get_tournament(selected)
    players = db.get_players(selected)
    teams = db.get_teams(selected)
    c1, c2, c3 = st.columns(3)
    c1.metric("Teams", len(teams))
    c2.metric("Spelers", len(players))
    c3.metric("Regels controleren", sum(p.get("extraction_status") != "OK" for p in players))
    if tournament:
        st.caption(f"{tournament['category']} | {tournament['location']} | start {tournament['start_date']}")

    if players:
        st.subheader("Opgeslagen spelers corrigeren")
        columns = ["id", "country_code", "jersey_number", "last_name", "first_name", "position_original", "position_normalized", "birth_date", "height_cm", "extraction_status", "extraction_warning"]
        frame = pd.DataFrame(players)[columns]
        edited = st.data_editor(frame, hide_index=True, disabled=["id", "country_code", "extraction_status", "extraction_warning"], use_container_width=True, key=f"players_{selected}")
        if st.button("Correcties opslaan", type="primary"):
            start = date.fromisoformat(tournament["start_date"]) if tournament else None
            rows = validate_import(edited.to_dict("records"), start)
            for row in rows:
                db.update_player(int(row["id"]), row)
            st.success("De correcties zijn in deze sessie bijgewerkt.")
            st.rerun()

    with st.expander("Toernooi verwijderen"):
        confirm = st.checkbox("Ik weet dat dit toernooi en alle spelers worden verwijderd.")
        if st.button("Toernooi definitief verwijderen", disabled=not confirm):
            db.delete_tournament(selected)
            st.session_state.pop("tournament_id", None)
            st.success("Het toernooi is verwijderd.")
            st.rerun()


def render_new_tournament(db: Database) -> None:
    st.header("Nieuw toernooi")
    with st.form("new_tournament"):
        name = st.text_input("Naam")
        category = st.text_input("Categorie", placeholder="Bijvoorbeeld U20")
        gender = st.selectbox("Geslacht", ["Women", "Men", "Mixed", "Anders"])
        location = st.text_input("Locatie")
        start_date = st.date_input("Startdatum", value=date.today())
        has_end = st.checkbox("Einddatum toevoegen")
        end_date = st.date_input("Einddatum", value=start_date, disabled=not has_end)
        submitted = st.form_submit_button("Toernooi aanmaken", type="primary")
    if submitted:
        if not name.strip() or not category.strip() or not location.strip():
            st.error("Vul naam, categorie en locatie in.")
            return
        if has_end and end_date < start_date:
            st.error("De einddatum kan niet vóór de startdatum liggen.")
            return
        tournament_id = db.create_tournament({"name": name.strip(), "category": category.strip(), "gender": gender, "location": location.strip(), "start_date": start_date, "end_date": end_date if has_end else None})
        st.session_state["tournament_id"] = tournament_id
        st.success("Toernooi aangemaakt. Ga nu naar 'Import controleren'.")
