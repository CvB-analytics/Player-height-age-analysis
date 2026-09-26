from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from .date_parser import DateOrder, detect_date_order, parse_date
from .pdf_reader import extract_pages
from .position_parser import normalize_position

TEAM_RE = re.compile(r"(?m)^\s*([A-Z][A-Z ]{2,}?)\s+\(([A-Z]{3})\)\s*$")
POSITION = r"Libero(?:\s+[12])?|Setter|Outside spiker|Outside hitter|Middle blocker|Middle|Opposite(?: hitter)?"
PLAYER_RE = re.compile(
    rf"^\s*(\d{{1,2}})\s+(.+?)\s+({POSITION})\s+(\d{{1,4}}[./-]\d{{1,2}}[./-]\d{{1,4}})\s+(.+)$",
    re.IGNORECASE,
)
DATE_IN_LINE = re.compile(r"\b\d{1,4}[./-]\d{1,2}[./-]\d{1,4}\b")


@dataclass
class ParsedPlayer:
    country_code: str
    country_name: str
    jersey_number: int | None
    last_name: str
    first_name: str
    full_name_original: str
    position_original: str
    position_normalized: str
    raw_birth_date: str
    birth_date: date | None
    height_cm: int | None
    extraction_status: str
    extraction_warning: str


@dataclass
class ParseResult:
    profile: str
    date_order: DateOrder
    players: list[ParsedPlayer]
    teams: list[dict[str, str]]
    warnings: list[str]

    def as_records(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for player in self.players:
            row = asdict(player)
            row["birth_date"] = player.birth_date.isoformat() if player.birth_date else ""
            rows.append(row)
        return rows


class BaseRosterParser(ABC):
    name = "base"

    @abstractmethod
    def supports(self, pages: list[str]) -> bool: ...

    @abstractmethod
    def parse(self, pages: list[str], forced_date_order: DateOrder | None = None) -> ParseResult: ...


class CEVRosterParser(BaseRosterParser):
    name = "CEV/WEVZA"

    def supports(self, pages: list[str]) -> bool:
        return any(self._is_roster_page(page) for page in pages)

    @staticmethod
    def _is_roster_page(page: str) -> bool:
        upper = page.upper()
        if "FINAL TEAM LIST" in upper and ("BIRTH" in upper or "PERSONAL DATA" in upper):
            return True
        return bool(
            TEAM_RE.search(page)
            and "POSITION" in upper
            and "BIRTH" in upper
            and len(DATE_IN_LINE.findall(page)) >= 3
        )

    @staticmethod
    def _player_lines(text: str) -> list[str]:
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        result: list[str] = []
        current = ""
        pending_prefix = ""
        late_name_continuation = False
        for line in lines:
            upper = line.upper()
            if not line or upper.startswith("TEAM OFFICIAL"):
                if current:
                    result.append(current)
                    current = ""
                if upper.startswith("TEAM OFFICIAL"):
                    break
                continue
            if re.match(r"^\d{1,2}\s+", line):
                if current:
                    result.append(current)
                number_match = re.match(r"^(\d{1,2})\s+(.+)$", line)
                assert number_match
                number, rest = number_match.groups()
                starts_with_position = re.match(rf"^(?:{POSITION})\s+\d{{1,4}}[./-]", rest, re.IGNORECASE)
                if starts_with_position and pending_prefix:
                    current = f"{number} {pending_prefix} {rest}"
                    pending_prefix = ""
                    late_name_continuation = True
                else:
                    current = line
                    pending_prefix = ""
                    late_name_continuation = False
            elif current and not any(marker in upper for marker in ("FINAL TEAM", "PERSONAL DATA", "HIGHEST REACH", "BIRTH DATE", "LAST CLUB")):
                if (
                    DATE_IN_LINE.search(current)
                    and re.search(r"\([A-Z]{3}\)\s*$", current)
                    and any(token.isupper() for token in line.split())
                    and not line.endswith(")")
                ):
                    result.append(current)
                    current = ""
                    pending_prefix = line
                    late_name_continuation = False
                elif late_name_continuation and DATE_IN_LINE.search(current) and len(line.split()) <= 3:
                    current = re.sub(rf"\s+({POSITION})\s+", rf" {line} \1 ", current, count=1, flags=re.IGNORECASE)
                    late_name_continuation = False
                else:
                    current += " " + line
            elif (
                not current
                and line
                and not any(marker in upper for marker in ("FINAL TEAM", "PERSONAL DATA", "HIGHEST REACH", "BIRTH DATE", "LAST CLUB", "NAME & FIRST NAME", "REACH"))
                and not line.startswith("24/08/")
            ):
                pending_prefix = line
        if current:
            result.append(current)
        return result

    @staticmethod
    def _split_name(full_name: str) -> tuple[str, str, bool]:
        clean = re.sub(r"\s*\(c\)\s*", " ", full_name, flags=re.IGNORECASE).strip()
        parts = clean.split()
        boundary = next((index for index, token in enumerate(parts) if not token.isupper()), None)
        if boundary is None or boundary == 0:
            return clean, "", False
        return " ".join(parts[:boundary]), " ".join(parts[boundary:]), True

    def parse(self, pages: list[str], forced_date_order: DateOrder | None = None) -> ParseResult:
        candidates: list[dict[str, Any]] = []
        teams: list[dict[str, str]] = []
        warnings: list[str] = []

        for page in pages:
            if not self._is_roster_page(page):
                continue
            team_match = TEAM_RE.search(page)
            if not team_match:
                warnings.append("Een rosterpagina had geen betrouwbaar herkenbare teamkop.")
                continue
            country_name = re.sub(r"\s+", " ", team_match.group(1)).title()
            country_code = team_match.group(2)
            teams.append({"country_code": country_code, "country_name": country_name})

            header_position = page.upper().find("FINAL TEAM LIST")
            roster = page[header_position:] if header_position >= 0 else page
            for line in self._player_lines(roster):
                match = PLAYER_RE.match(line)
                if not match:
                    if DATE_IN_LINE.search(line):
                        warnings.append(f"Mogelijke spelersregel niet herkend ({country_code}): {line[:90]}")
                    continue
                jersey, full_name, position, raw_date, remainder = match.groups()
                numeric = re.findall(r"(?<!\w)(\d{1,3})(?!\w)", remainder)
                height = int(numeric[1]) if len(numeric) >= 2 else None
                last_name, first_name, split_ok = self._split_name(full_name)
                candidates.append(
                    {
                        "country_code": country_code,
                        "country_name": country_name,
                        "jersey_number": int(jersey),
                        "last_name": last_name,
                        "first_name": first_name,
                        "full_name_original": full_name.strip(),
                        "position_original": position.strip(),
                        "raw_birth_date": raw_date,
                        "height_cm": height,
                        "split_ok": split_ok,
                    }
                )

        detected = detect_date_order(item["raw_birth_date"] for item in candidates)
        order = forced_date_order or detected
        players: list[ParsedPlayer] = []
        seen: set[tuple[str, int | None]] = set()
        for item in candidates:
            row_warnings: list[str] = []
            normalized, position_warning = normalize_position(item["position_original"])
            if position_warning:
                row_warnings.append(position_warning)
            birth = parse_date(item["raw_birth_date"], order)
            if detected == "AMBIGUOUS" and not forced_date_order:
                row_warnings.append("Datumvolgorde is niet overtuigend vastgesteld; kies DD/MM of MM/DD.")
                birth = None
            elif not birth:
                row_warnings.append("Ongeldige of niet herkenbare geboortedatum.")
            elif birth > date.today():
                row_warnings.append("Geboortedatum ligt in de toekomst.")
            if item["height_cm"] is None:
                row_warnings.append("Lengte ontbreekt.")
            elif not 140 <= item["height_cm"] <= 215:
                row_warnings.append("Lengte valt buiten de gebruikelijke controlegrenzen (140-215 cm).")
            if not item["split_ok"]:
                row_warnings.append("Voor- en achternaam konden niet betrouwbaar worden gesplitst.")
            duplicate_key = (item["country_code"], item["jersey_number"])
            if duplicate_key in seen:
                row_warnings.append("Mogelijk dubbel rugnummer binnen hetzelfde team.")
            seen.add(duplicate_key)
            players.append(
                ParsedPlayer(
                    **{key: item[key] for key in (
                        "country_code", "country_name", "jersey_number", "last_name", "first_name",
                        "full_name_original", "position_original", "raw_birth_date", "height_cm"
                    )},
                    position_normalized=normalized,
                    birth_date=birth,
                    extraction_status="Controleren" if row_warnings else "OK",
                    extraction_warning="; ".join(row_warnings),
                )
            )

        if not players:
            warnings.append("Geen spelersregels gevonden. Controleer of dit een ondersteund CEV/WEVZA-bulletin is.")
        return ParseResult(self.name, detected if not forced_date_order else forced_date_order, players, teams, warnings)


class GenericRosterParser(BaseRosterParser):
    name = "generiek"

    def supports(self, pages: list[str]) -> bool:
        return True

    def parse(self, pages: list[str], forced_date_order: DateOrder | None = None) -> ParseResult:
        return ParseResult(
            self.name,
            "AMBIGUOUS",
            [],
            [],
            [
                "Er is geen herkenbare spelerslijst gevonden. Mogelijk wijkt de tabelindeling af "
                "of kon een afbeeldingspagina niet met OCR worden gelezen."
            ],
        )


def parse_bulletin(source: bytes | str, forced_date_order: DateOrder | None = None) -> ParseResult:
    pages = extract_pages(source)
    parsers: list[BaseRosterParser] = [CEVRosterParser(), GenericRosterParser()]
    parser = next(candidate for candidate in parsers if candidate.supports(pages))
    return parser.parse(pages, forced_date_order)
