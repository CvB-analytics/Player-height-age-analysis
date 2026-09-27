from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.parser.date_parser import parse_date
from src.parser.pdf_reader import NoUsableTextError
from src.parser.roster_parser import parse_bulletin
from src.storage.database import Database
from src.validation.import_validator import validate_import

DISPLAY_COLUMNS = {
    "country_code": "Land", "jersey_number": "Rugnr", "last_name": "Achternaam",
    "first_name": "Voornaam", "position_original": "Positie bron",
    "position_normalized": "Positie", "raw_birth_date": "Datum bron",
    "birth_date": "Geboortedatum", "height_cm": "Lengte", "extraction_status": "Status",
    "extraction_warning": "Waarschuwing",
}


def render_import(db: Database) -> None:
    st.header("Import controleren")
    tournament_id = st.session_state.get("tournament_id")
    tournament = db.get_tournament(tournament_id) if tournament_id else None
    if not tournament:
        st.info("Maak of open eerst een toernooi.")
        return
    st.caption(f"Actief toernooi: {tournament['name']}")
    uploaded = st.file_uploader("PDF selecteren", type=["pdf"], accept_multiple_files=False)
    if uploaded and st.button("PDF verwerken", type="primary"):
        try:
            with st.spinner("Het bulletin wordt in deze sessie uitgelezen..."):
                result = parse_bulletin(uploaded.getvalue())
        except NoUsableTextError as exc:
            st.error(str(exc))
            return
        st.session_state["import_pdf_bytes"] = uploaded.getvalue()
        st.session_state["import_filename"] = uploaded.name
        st.session_state["import_result"] = result.as_records()
        st.session_state["import_date_order"] = result.date_order
        st.session_state["import_profile"] = result.profile
        st.session_state["parser_warnings"] = result.warnings

    rows = st.session_state.get("import_result")
    if rows == []:
        for warning in st.session_state.get("parser_warnings", []):
            st.warning(warning)
        st.error(
            "Deze PDF leverde nog geen herkenbare spelersregels op. "
            "De datumkeuze is daarom niet van toepassing."
        )
        return
    if rows is None:
        return

    order = st.session_state.get("import_date_order")
    if order == "AMBIGUOUS":
        st.warning("De datumvolgorde is niet betrouwbaar vast te stellen. Kies de indeling die voor de hele import geldt.")
        choice = st.radio("Datumindeling", ["DD/MM", "MM/DD"], horizontal=True, key="import_date_choice")
        if st.button("Datums opnieuw interpreteren"):
            pdf_bytes = st.session_state.get("import_pdf_bytes")
            if not pdf_bytes:
                st.error("De tijdelijke PDF is niet meer beschikbaar. Selecteer het bestand opnieuw.")
                return
            result = parse_bulletin(pdf_bytes, "DMY" if choice == "DD/MM" else "MDY")
            st.session_state["import_result"] = result.as_records()
            st.session_state["import_date_order"] = result.date_order
            st.session_state["import_profile"] = result.profile
            st.session_state["parser_warnings"] = result.warnings
            st.rerun()

    parser_warnings = st.session_state.get("parser_warnings", [])
    completeness_warnings = [warning for warning in parser_warnings if warning.startswith("VOLLEDIGHEIDSCONTROLE:")]
    for warning in parser_warnings:
        st.warning(warning)
    frame = pd.DataFrame(rows)
    start = date.fromisoformat(tournament["start_date"])
    frame = pd.DataFrame(validate_import(frame.to_dict("records"), start))
    visible = list(DISPLAY_COLUMNS)
    review = frame[visible].rename(columns=DISPLAY_COLUMNS)
    teams = review["Land"].nunique()
    issues = int((review["Status"] != "OK").sum())
    st.subheader(f"{len(review)} spelers gevonden in {teams} teams")
    if issues:
        st.warning(f"{issues} regels controleren. Open de kolom 'Waarschuwing' voor uitleg.")
    else:
        st.success("Geen automatische waarschuwingen gevonden.")
    st.caption("Controleer altijd of het aantal gevonden teams en spelers overeenkomt met het brondocument.")
    edited = st.data_editor(
        review,
        hide_index=True,
        use_container_width=True,
        disabled=["Datum bron", "Status", "Waarschuwing"],
        column_config={"Geboortedatum": st.column_config.TextColumn(help="Gebruik JJJJ-MM-DD")},
        num_rows="dynamic",
        key="import_editor",
    )
    completeness_confirmed = True
    if completeness_warnings:
        st.error("De automatische volledigheidscontrole vond mogelijk ontbrekende teams of spelers.")
        completeness_confirmed = st.checkbox(
            "Ik heb alle rosterpagina's gecontroleerd en ontbrekende spelers handmatig aangevuld.",
            key="confirm_import_completeness",
        )
    if st.button("Import goedkeuren en gebruiken", type="primary", disabled=not completeness_confirmed):
        internal = edited.rename(columns={value: key for key, value in DISPLAY_COLUMNS.items()})
        saved_rows = internal.to_dict("records")
        by_key = {_row_key(r): r for r in rows if _row_key(r) is not None}
        for row in saved_rows:
            original = by_key.get(_row_key(row))
            row["country_name"] = original.get("country_name", row["country_code"]) if original else row["country_code"]
            row["full_name_original"] = original.get("full_name_original", "") if original else ""
            row["birth_date"] = parse_date(row.get("birth_date"), "YMD")
        saved_rows = validate_import(saved_rows, start)
        remaining = sum(row["extraction_status"] != "OK" for row in saved_rows)
        if remaining:
            st.error(f"Er zijn nog {remaining} regels met waarschuwingen. Corrigeer deze eerst; de import is niet verwerkt.")
            return
        db.save_players(tournament_id, saved_rows)
        db.update_tournament_source(tournament_id, st.session_state.get("import_filename", ""))
        for key in ("import_result", "import_pdf_bytes", "import_filename", "import_date_order", "import_profile", "import_date_choice", "parser_warnings", "confirm_import_completeness"):
            st.session_state.pop(key, None)
        st.success("De import is goedgekeurd en tijdelijk in deze sessie beschikbaar.")
        st.rerun()


def _row_key(row: dict) -> tuple[str, int] | None:
    try:
        return str(row.get("country_code") or "").strip().upper(), int(float(row.get("jersey_number")))
    except (TypeError, ValueError):
        return None
