from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class StructuredRosterRow:
    jersey_number: int | None
    last_name: str
    first_name: str
    full_name: str
    position: str
    raw_birth_date: str
    height_cm: int | None


HEADER_ALIASES = {
    "jersey": ("shirt", "shirt no", "shirt number", "jersey", "rugnr", "number", "no"),
    "last": ("last name", "surname", "family name"),
    "first": ("first name", "given name"),
    "name": ("name first name", "name and first name", "player name", "name"),
    "position": ("pos", "position"),
    "birth": ("birthdate", "birth date", "date of birth", "dob", "geboortedatum"),
    "height": ("height", "height cm", "lengte"),
}

DATE_PATTERN = re.compile(
    r"(?:\d{1,4}[./-]\d{1,2}[./-]\d{1,4}|\d{1,2}[- ](?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[- ]\d{2,4})",
    re.IGNORECASE,
)


def extract_structured_roster_rows(page: str) -> list[StructuredRosterRow]:
    """Read roster rows from tab-separated OCR/PDF cells by header meaning.

    This layer is federation-neutral: it only needs recognizable column labels.
    It intentionally ignores identifiers and eligibility columns that previously
    leaked into player names when a complete OCR line was parsed as prose.
    """
    best: list[StructuredRosterRow] = []
    for table in _tabular_blocks(page):
        mapping, header_end = _find_header(table)
        if not mapping:
            continue
        parsed = [_parse_row(row, mapping) for row in table[header_end:]]
        rows = [row for row in parsed if row is not None]
        if len(rows) > len(best):
            best = rows
    return best


def _tabular_blocks(page: str) -> list[list[list[str]]]:
    blocks: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in page.splitlines():
        if "\t" not in line:
            if current:
                blocks.append(current)
                current = []
            continue
        current.append([_clean(cell) for cell in line.split("\t")])
    if current:
        blocks.append(current)
    return [block for block in blocks if len(block) >= 2]


def _find_header(table: list[list[str]]) -> tuple[dict[str, int], int]:
    width = max((len(row) for row in table), default=0)
    best: tuple[int, dict[str, int], int] = (0, {}, 0)
    for start in range(min(5, len(table))):
        for depth in range(1, min(3, len(table) - start) + 1):
            combined = [
                " ".join(
                    table[row_index][column]
                    for row_index in range(start, start + depth)
                    if column < len(table[row_index]) and table[row_index][column]
                )
                for column in range(width)
            ]
            mapping: dict[str, int] = {}
            used: set[int] = set()
            for field in ("birth", "height", "position", "last", "first", "name", "jersey"):
                match = _best_header_column(field, combined, used)
                if match is not None:
                    mapping[field] = match
                    used.add(match)
            score = _mapping_score(mapping)
            # Prefer the shallowest complete header. Including the first data
            # row can otherwise make its values look like extra header labels
            # and silently discard that player.
            if score >= 8:
                return mapping, start + depth
            if score > best[0]:
                best = (score, mapping, start + depth)
    return (best[1], best[2]) if best[0] >= 8 else ({}, 0)


def _best_header_column(field: str, cells: list[str], used: set[int]) -> int | None:
    best: tuple[float, int] | None = None
    for index, cell in enumerate(cells):
        if index in used:
            continue
        normalized = _header_text(cell)
        if not normalized:
            continue
        for alias in HEADER_ALIASES[field]:
            alias_normalized = _header_text(alias)
            if normalized == alias_normalized:
                score = 1.0
            elif alias_normalized in normalized:
                score = 0.93 - min(0.2, (len(normalized) - len(alias_normalized)) / 100)
            else:
                score = SequenceMatcher(None, normalized, alias_normalized).ratio()
            if best is None or score > best[0]:
                best = (score, index)
    threshold = 0.70 if field in {"birth", "position", "height"} else 0.76
    return best[1] if best and best[0] >= threshold else None


def _mapping_score(mapping: dict[str, int]) -> int:
    score = 0
    score += 3 if "birth" in mapping else 0
    score += 2 if "jersey" in mapping else 0
    score += 2 if "height" in mapping else 0
    score += 1 if "position" in mapping else 0
    score += 3 if {"last", "first"} <= mapping.keys() else 0
    score += 2 if "name" in mapping else 0
    return score


def _parse_row(row: list[str], mapping: dict[str, int]) -> StructuredRosterRow | None:
    def cell(field: str) -> str:
        index = mapping.get(field)
        return _clean(row[index]) if index is not None and index < len(row) else ""

    raw_date = cell("birth")
    date_match = DATE_PATTERN.search(raw_date)
    if not date_match:
        return None
    raw_date = date_match.group(0)

    jersey_match = re.search(r"(?<!\d)(\d{1,2})(?!\d)", cell("jersey"))
    jersey = int(jersey_match.group(1)) if jersey_match else None
    if jersey is not None and not 0 < jersey <= 99:
        jersey = None

    height_values = [int(value) for value in re.findall(r"(?<!\d)(\d{3})(?!\d)", cell("height"))]
    height = next((value for value in height_values if 140 <= value <= 215), None)

    last_name = cell("last")
    first_name = cell("first")
    full_name = cell("name")
    if last_name or first_name:
        full_name = f"{last_name} {first_name}".strip()
    elif full_name:
        last_name, first_name = _split_combined_name(full_name)
    if not full_name:
        return None

    return StructuredRosterRow(
        jersey_number=jersey,
        last_name=last_name,
        first_name=first_name,
        full_name=full_name,
        position=cell("position"),
        raw_birth_date=raw_date,
        height_cm=height,
    )


def _split_combined_name(value: str) -> tuple[str, str]:
    parts = value.split()
    boundary = next((index for index, token in enumerate(parts) if not token.isupper()), None)
    if boundary is None or boundary == 0:
        return value, ""
    return " ".join(parts[:boundary]), " ".join(parts[boundary:])


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" |")


def _header_text(value: str) -> str:
    text = str(value or "").casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()
