from __future__ import annotations

import logging

import streamlit as st

from src.storage.database import Database
from src.ui.import_review import render_import
from src.ui.navigation import NAVIGATION_KEY, apply_pending_navigation
from src.ui.reports import render_reports
from src.ui.results import render_results
from src.ui.tournament import render_new_tournament

APP_VERSION = "0.6.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

st.set_page_config(page_title="Volleybaltoernooi verwerken", page_icon="🏐", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; max-width: 1500px;}
    [data-testid="stMetric"] {background:#eef5f9; border:1px solid #d8e4ec; padding:14px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,.08);}
    [data-testid="stMetric"] * {color:#17324D !important;}
    .team-count-grid {display:grid; grid-template-columns:repeat(auto-fit,minmax(82px,1fr)); gap:7px; margin:2px 0 12px;}
    .team-count {display:flex; align-items:center; justify-content:space-between; gap:8px; background:#eef5f9; border:1px solid #d8e4ec; border-radius:8px; padding:7px 10px; color:#17324D; font-size:.9rem;}
    .team-count strong {font-size:1rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _session_database() -> Database:
    if "database" not in st.session_state:
        st.session_state["database"] = Database()
    return st.session_state["database"]


def _clear_session() -> None:
    database = st.session_state.get("database")
    if database is not None:
        database.close()
    st.session_state.clear()
    st.rerun()


def main() -> None:
    db = _session_database()
    st.title("Volleybaltoernooi verwerken")
    st.caption(
        "Gegevens blijven alleen in deze browsersessie en worden niet permanent opgeslagen. "
        "De app gebruikt geen AI of externe analyse-API."
    )
    pages = {
        "Nieuw toernooi": render_new_tournament,
        "Import controleren": render_import,
        "Resultaten": render_results,
        "Rapportage": render_reports,
    }
    apply_pending_navigation(list(pages))
    selected = st.sidebar.radio("Navigatie", list(pages), key=NAVIGATION_KEY)
    tournament_id = st.session_state.get("tournament_id")
    tournament = db.get_tournament(tournament_id) if tournament_id else None
    st.sidebar.divider()
    st.sidebar.caption(f"Actief: {tournament['name']}" if tournament else "Geen actief toernooi")
    st.sidebar.caption(f"Appversie {APP_VERSION}")
    with st.sidebar.expander("Sessiedata wissen"):
        st.caption("Verwijdert direct het tijdelijke toernooi en alle spelers uit deze browsersessie.")
        confirm_clear = st.checkbox("Ik wil alle sessiegegevens wissen.", key="confirm_clear_session")
        if st.button("Alles wissen", disabled=not confirm_clear, use_container_width=True):
            _clear_session()
    try:
        pages[selected](db)
    except Exception as exc:
        logging.exception("Onverwachte fout in scherm %s", selected)
        st.error("Er ging iets mis. Probeer de vorige stap opnieuw; gegevens worden niet permanent opgeslagen.")
        with st.expander("Technische informatie voor ondersteuning"):
            st.code(str(exc))


if __name__ == "__main__":
    main()
