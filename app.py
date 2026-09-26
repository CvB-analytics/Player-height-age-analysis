from __future__ import annotations

import logging
from pathlib import Path

import streamlit as st

from src.storage.database import Database
from src.ui.import_review import render_import
from src.ui.reports import render_reports
from src.ui.results import render_results
from src.ui.tournament import render_new_tournament, render_tournaments

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=DATA_DIR / "app.log",
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
    </style>
    """,
    unsafe_allow_html=True,
)


def main() -> None:
    db = Database(DATA_DIR / "app.db")
    st.title("Volleybaltoernooi verwerken")
    st.caption("Alles blijft lokaal op deze computer. De app gebruikt geen AI, cloudservice of externe API.")
    pages = {
        "Toernooien": render_tournaments,
        "Nieuw toernooi": render_new_tournament,
        "Import controleren": render_import,
        "Resultaten": render_results,
        "Rapportage": render_reports,
    }
    selected = st.sidebar.radio("Navigatie", list(pages))
    tournament_id = st.session_state.get("tournament_id")
    tournament = db.get_tournament(tournament_id) if tournament_id else None
    st.sidebar.divider()
    st.sidebar.caption(f"Actief: {tournament['name']}" if tournament else "Geen actief toernooi")
    try:
        pages[selected](db)
    except Exception as exc:
        logging.exception("Onverwachte fout in scherm %s", selected)
        st.error("Er ging iets mis. De gegevens zijn niet stilletjes opgeslagen. Sluit de app niet; probeer de vorige stap opnieuw.")
        with st.expander("Technische informatie voor ondersteuning"):
            st.code(str(exc))


if __name__ == "__main__":
    main()
