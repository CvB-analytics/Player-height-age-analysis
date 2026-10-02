from __future__ import annotations

POSITION_MAPPING = {
    "setter": "SV",
    "outside spiker": "PL",
    "outside hitter": "PL",
    "outside": "PL",
    "receiver attacker": "PL",
    "wing spiker": "PL",
    "oh": "PL",
    "os": "PL",
    "middle blocker": "MB",
    "middle": "MB",
    "mb": "MB",
    "opposite": "DIA",
    "opposite hitter": "DIA",
    "op": "DIA",
    "opp": "DIA",
    "libero": "LIB",
    "libero 1": "LIB",
    "libero 2": "LIB",
    "l": "LIB",
    "s": "SV",
}


def normalize_position(position: str | None) -> tuple[str, str | None]:
    original = (position or "").strip()
    if original.casefold().startswith("controleren"):
        return "ONBEKEND", "Positie controleren."
    normalized = POSITION_MAPPING.get(original.casefold())
    if normalized:
        return normalized, None
    return "ONBEKEND", f"Onbekende positie: {original or 'leeg'}"
