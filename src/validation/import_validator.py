from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from .player_validator import validate_player


def validate_import(rows: list[dict[str, Any]], tournament_start: date | None = None) -> list[dict[str, Any]]:
    keys = Counter((row.get("country_code"), row.get("jersey_number")) for row in rows)
    validated: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        warnings = validate_player(copy, tournament_start)
        if keys[(copy.get("country_code"), copy.get("jersey_number"))] > 1:
            warnings.append("Dubbele combinatie van team en rugnummer.")
        copy["extraction_warning"] = "; ".join(dict.fromkeys(warnings))
        copy["extraction_status"] = "Controleren" if warnings else "OK"
        validated.append(copy)
    return validated
