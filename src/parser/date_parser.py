from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable, Literal

DateOrder = Literal["DMY", "MDY", "YMD", "AMBIGUOUS"]

NUMERIC_DATE_RE = re.compile(r"^\s*(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})\s*$")
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
    "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12,
    "december": 12,
}


def _year(value: int) -> int:
    if value >= 100:
        return value
    return 2000 + value if value <= 49 else 1900 + value


def detect_date_order(date_strings: Iterable[str]) -> DateOrder:
    """Detect one numeric date order for a complete table/document.

    ISO dates are accepted alongside another consistent order. When the
    non-ISO values do not prove DMY or MDY, the result stays AMBIGUOUS.
    """
    values = [str(value or "") for value in date_strings]
    evidence: set[str] = set()
    saw_numeric = False
    saw_iso = False
    for raw in values:
        match = NUMERIC_DATE_RE.match(str(raw or ""))
        if not match:
            continue
        saw_numeric = True
        first, second, _ = (int(item) for item in match.groups())
        if first >= 1000:
            saw_iso = True
            continue
        if first > 12 and second <= 12:
            evidence.add("DMY")
        elif second > 12 and first <= 12:
            evidence.add("MDY")
        elif first > 12 and second > 12:
            return "AMBIGUOUS"
    if len(evidence) == 1:
        return evidence.pop()  # type: ignore[return-value]
    if len(evidence) > 1:
        return "AMBIGUOUS"
    if saw_iso and saw_numeric:
        # Only pure ISO input is unambiguous; mixed ambiguous slash dates are not.
        non_iso = [
            text for text in values
            if (match := NUMERIC_DATE_RE.match(text)) and int(match.group(1)) < 1000
        ]
        return "AMBIGUOUS" if non_iso else "YMD"
    return "YMD" if saw_iso else "AMBIGUOUS"


def parse_date(value: str | date | datetime | None, order: DateOrder = "DMY") -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = re.sub(r"\s+", " ", str(value).strip().replace(",", ""))
    match = NUMERIC_DATE_RE.match(text)
    try:
        if match:
            a, b, c = (int(item) for item in match.groups())
            if a >= 1000 or order == "YMD":
                year, month, day = a, b, c
            elif order == "DMY":
                day, month, year = a, b, _year(c)
            elif order == "MDY":
                month, day, year = a, b, _year(c)
            else:
                return None
            return date(year, month, day)

        parts = text.split()
        if len(parts) == 3:
            if parts[0].lower() in MONTHS:
                month, day, year = MONTHS[parts[0].lower()], int(parts[1]), _year(int(parts[2]))
            elif parts[1].lower() in MONTHS:
                day, month, year = int(parts[0]), MONTHS[parts[1].lower()], _year(int(parts[2]))
            else:
                return None
            return date(year, month, day)
    except (ValueError, TypeError):
        return None
    return None
