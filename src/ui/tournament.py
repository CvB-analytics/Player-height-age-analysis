from __future__ import annotations

from datetime import date

import streamlit as st

from src.storage.database import Database


def render_new_tournament(db: Database) -> None:
    st.header("Nieuw toernooi")
    created_name = st.session_state.pop("new_tournament_created", None)
    if created_name:
        st.success(f"{created_name} is aangemaakt. Ga nu naar 'Import controleren'.")
    st.caption(
        "Per browsersessie wordt één tijdelijk toernooi gebruikt. "
        "Een nieuw toernooi vervangt alle gegevens van het huidige toernooi."
    )
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
        db.clear_tournaments()
        tournament_id = db.create_tournament({"name": name.strip(), "category": category.strip(), "gender": gender, "location": location.strip(), "start_date": start_date, "end_date": end_date if has_end else None})
        for key in list(st.session_state):
            if key != "database":
                st.session_state.pop(key, None)
        st.session_state["tournament_id"] = tournament_id
        st.session_state["new_tournament_created"] = name.strip()
        st.rerun()
