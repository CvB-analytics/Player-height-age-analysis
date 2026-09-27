from __future__ import annotations

from datetime import date
from typing import Any

from src.parser.date_parser import parse_date
from src.parser.position_parser import normalize_position


def validate_player(row: dict[str, Any], tournament_start: date | None = None) -> list[str]:
    warnings: list[str] = []
    if not str(row.get("country_code") or "").strip():
        warnings.append("Land ontbreekt.")
    if not row.get("jersey_number"):
        warnings.append("Rugnummer ontbreekt.")
    if not str(row.get("last_name") or "").strip():
        warnings.append("Achternaam ontbreekt.")
    if not str(row.get("first_name") or "").strip():
        warnings.append("Voornaam ontbreekt.")
    position = str(row.get("position_original") or "").strip()
    normalized = str(row.get("position_normalized") or "").strip().upper()
    if position:
        mapped, position_warning = normalize_position(position)
        if mapped != "ONBEKEND":
            row["position_normalized"] = mapped
        elif normalized not in {"SV", "PL", "MB", "DIA", "LIB"} and position_warning:
            row["position_normalized"] = "ONBEKEND"
            warnings.append(position_warning)
    elif normalized not in {"SV", "PL", "MB", "DIA", "LIB"}:
        warnings.append("Positie ontbreekt of is onbekend.")
    birth = parse_date(row.get("birth_date"), "YMD")
    if not birth:
        warnings.append("Geboortedatum is ongeldig. Gebruik JJJJ-MM-DD.")
    elif birth > date.today():
        warnings.append("Geboortedatum ligt in de toekomst.")
    elif tournament_start:
        age = tournament_start.year - birth.year - ((tournament_start.month, tournament_start.day) < (birth.month, birth.day))
        if not 12 <= age <= 40:
            warnings.append(f"Leeftijd ({age}) is ongebruikelijk voor een jeugd-/seniorentoernooi.")
    try:
        height = int(row.get("height_cm"))
        if not 140 <= height <= 215:
            warnings.append("Lengte valt buiten 140-215 cm.")
    except (TypeError, ValueError):
        warnings.append("Lengte ontbreekt of is geen heel aantal centimeters.")
    return warnings
