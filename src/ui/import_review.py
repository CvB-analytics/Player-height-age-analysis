from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from src.parser.date_parser import parse_date
from src.parser.pdf_reader import NoUsableTextError
from src.parser.roster_parser import parse_bulletin
from src.storage.database import Database
from src.validation.import_validator import validate_import

EDITOR_COLUMNS = {
    "country_code": "Land", "jersey_number": "Rugnr", "last_name": "Achternaam",
    "first_name": "Voornaam", "position_original": "Positie",
    "birth_date": "Geboortedatum", "height_cm": "Lengte", "extraction_warning": "Opmerking",
}
EDITOR_STATE_KEY = "import_review_display"
EDITOR_VERSION_KEY = "import_editor_version"
EDITOR_WIDGET_PREFIX = "import_editor_grid_"


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
        _reset_editor_state()

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
            _reset_editor_state()
            st.rerun()

    parser_warnings = st.session_state.get("parser_warnings", [])
    completeness_warnings = [warning for warning in parser_warnings if warning.startswith("VOLLEDIGHEIDSCONTROLE:")]
    for warning in parser_warnings:
        st.warning(warning)
    frame = pd.DataFrame(rows)
    start = date.fromisoformat(tournament["start_date"])
    frame = pd.DataFrame(validate_import(frame.to_dict("records"), start))
    if EDITOR_STATE_KEY not in st.session_state:
        initial = frame.reindex(columns=EDITOR_COLUMNS).rename(columns=EDITOR_COLUMNS)
        st.session_state[EDITOR_STATE_KEY] = _validate_and_sort_review(initial, start).to_dict("records")
    review = pd.DataFrame(st.session_state[EDITOR_STATE_KEY]).reindex(columns=EDITOR_COLUMNS.values())
    review = _validate_and_sort_review(review, start)
    st.session_state[EDITOR_STATE_KEY] = review.to_dict("records")

    team_counts = _team_counts(review)
    teams = len([code for code in team_counts if code != "Nog zonder land"])
    issues = int(review["Opmerking"].fillna("").astype(str).str.strip().ne("").sum())
    st.subheader(f"{len(review)} spelers gevonden in {teams} teams")
    st.markdown("**Controle per team**")
    _render_team_counts(team_counts)
    if issues:
        st.warning(f"{issues} regels controleren. De uitleg staat direct in de kolom 'Opmerking'.")
    else:
        st.success("Geen automatische waarschuwingen gevonden.")
    st.caption("Controleer altijd of het aantal gevonden teams en spelers overeenkomt met het brondocument.")
    editor_version = int(st.session_state.get(EDITOR_VERSION_KEY, 0))
    editor_key = f"{EDITOR_WIDGET_PREFIX}{editor_version}"
    for key in list(st.session_state):
        if key.startswith(EDITOR_WIDGET_PREFIX) and key != editor_key:
            st.session_state.pop(key, None)
    edited = st.data_editor(
        review,
        hide_index=True,
        width="stretch",
        height=min(680, max(360, 38 * (min(len(review), 15) + 1))),
        row_height=34,
        disabled=["Opmerking"],
        column_config={
            "Land": st.column_config.TextColumn(width=58, required=True, help="Drielettercode, bijvoorbeeld NED"),
            "Rugnr": st.column_config.NumberColumn(width=64, min_value=0, max_value=99, step=1, format="%d"),
            "Achternaam": st.column_config.TextColumn(width=126),
            "Voornaam": st.column_config.TextColumn(width=108),
            "Positie": st.column_config.TextColumn(width=122, help="Bijvoorbeeld Setter, Libero of Middle blocker"),
            "Geboortedatum": st.column_config.TextColumn(width=112, help="Gebruik JJJJ-MM-DD"),
            "Lengte": st.column_config.NumberColumn(width=72, step=1, format="%d cm"),
            "Opmerking": st.column_config.TextColumn(width=250, disabled=True),
        },
        num_rows="dynamic",
        key=editor_key,
        on_change=_apply_editor_changes,
        args=(editor_key, review.to_dict("records"), start.isoformat()),
    )
    completeness_confirmed = True
    if completeness_warnings:
        st.error("De automatische volledigheidscontrole vond mogelijk ontbrekende teams of spelers.")
        completeness_confirmed = st.checkbox(
            "Ik heb alle rosterpagina's gecontroleerd en ontbrekende spelers handmatig aangevuld.",
            key="confirm_import_completeness",
        )
    if st.button("Import goedkeuren en gebruiken", type="primary", disabled=not completeness_confirmed):
        internal = edited.rename(columns={value: key for key, value in EDITOR_COLUMNS.items()})
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
        for key in ("import_result", "import_pdf_bytes", "import_filename", "import_date_order", "import_profile", "import_date_choice", "parser_warnings", "confirm_import_completeness", EDITOR_STATE_KEY, EDITOR_VERSION_KEY):
            st.session_state.pop(key, None)
        st.success("De import is goedgekeurd en tijdelijk in deze sessie beschikbaar.")
        st.rerun()


def _row_key(row: dict) -> tuple[str, int] | None:
    try:
        return str(row.get("country_code") or "").strip().upper(), int(float(row.get("jersey_number")))
    except (TypeError, ValueError):
        return None


def _reset_editor_state() -> None:
    st.session_state.pop(EDITOR_STATE_KEY, None)
    st.session_state[EDITOR_VERSION_KEY] = int(st.session_state.get(EDITOR_VERSION_KEY, 0)) + 1


def _apply_editor_changes(editor_key: str, records: list[dict[str, Any]], start_date: str) -> None:
    """Apply Streamlit's compact edit patch, then rebuild and sort the complete grid."""
    state = st.session_state.get(editor_key, {})
    start = date.fromisoformat(start_date)
    st.session_state[EDITOR_STATE_KEY] = _apply_editor_patch(records, state, start).to_dict("records")
    sort_changed = any(
        any(column in {"Land", "Rugnr"} for column in changes)
        for changes in state.get("edited_rows", {}).values()
    )
    if state.get("added_rows") or state.get("deleted_rows") or sort_changed:
        st.session_state[EDITOR_VERSION_KEY] = int(st.session_state.get(EDITOR_VERSION_KEY, 0)) + 1


def _apply_editor_patch(records: list[dict[str, Any]], state: dict[str, Any], start: date) -> pd.DataFrame:
    frame = pd.DataFrame(records).reindex(columns=EDITOR_COLUMNS.values())
    for raw_index, changes in state.get("edited_rows", {}).items():
        index = int(raw_index)
        if 0 <= index < len(frame):
            for column, value in changes.items():
                if column in frame.columns:
                    frame.at[index, column] = value
    deleted = sorted((int(index) for index in state.get("deleted_rows", [])), reverse=True)
    if deleted:
        frame = frame.drop(index=[index for index in deleted if 0 <= index < len(frame)]).reset_index(drop=True)
    added = state.get("added_rows", [])
    if added:
        frame = pd.concat([frame, pd.DataFrame(added)], ignore_index=True).reindex(columns=EDITOR_COLUMNS.values())
    return _validate_and_sort_review(frame, start)


def _validate_and_sort_review(frame: pd.DataFrame, start: date) -> pd.DataFrame:
    display = frame.reindex(columns=EDITOR_COLUMNS.values()).copy()
    display = display.astype(object).where(pd.notna(display), None)
    internal = display.rename(columns={value: key for key, value in EDITOR_COLUMNS.items()})
    validated = pd.DataFrame(validate_import(internal.to_dict("records"), start))
    result = validated.reindex(columns=EDITOR_COLUMNS).rename(columns=EDITOR_COLUMNS)
    result["Land"] = result["Land"].fillna("").astype(str).str.strip().str.upper()
    result["_rugnr_sort"] = pd.to_numeric(result["Rugnr"], errors="coerce")
    result["_land_sort"] = result["Land"].replace("", "ZZZZ")
    result = result.sort_values(["_land_sort", "_rugnr_sort", "Achternaam"], na_position="last", kind="stable")
    return result.drop(columns=["_rugnr_sort", "_land_sort"]).reset_index(drop=True)


def _team_counts(review: pd.DataFrame) -> dict[str, int]:
    codes = review.get("Land", pd.Series(dtype=object)).fillna("").astype(str).str.strip().str.upper()
    counts = codes[codes.ne("")].value_counts(sort=False).sort_index().to_dict()
    missing = int(codes.eq("").sum())
    if missing:
        counts["Nog zonder land"] = missing
    return {str(code): int(count) for code, count in counts.items()}


def _render_team_counts(team_counts: dict[str, int]) -> None:
    if not team_counts:
        st.info("Nog geen landen gevonden.")
        return
    chips = "".join(
        f'<div class="team-count"><span>{escape(code)}</span><strong>{count}</strong></div>'
        for code, count in team_counts.items()
    )
    st.markdown(f'<div class="team-count-grid">{chips}</div>', unsafe_allow_html=True)
