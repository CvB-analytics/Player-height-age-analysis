from __future__ import annotations

POSITION_MAPPING = {
    "setter": "SV",
    "outside spiker": "PL",
    "outside hitter": "PL",
    "middle blocker": "MB",
    "middle": "MB",
    "opposite": "DIA",
    "opposite hitter": "DIA",
    "libero": "LIB",
    "libero 1": "LIB",
    "libero 2": "LIB",
}


def normalize_position(position: str | None) -> tuple[str, str | None]:
    original = (position or "").strip()
    normalized = POSITION_MAPPING.get(original.casefold())
    if normalized:
        return normalized, None
    return "ONBEKEND", f"Onbekende positie: {original or 'leeg'}"
