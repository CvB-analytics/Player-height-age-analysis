from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from typing import Any

from .date_parser import DateOrder, detect_date_order, parse_date
from .pdf_reader import extract_pages
from .position_parser import normalize_position
from .structured_table import extract_structured_roster_rows

TEAM_RE = re.compile(r"(?mi)^\s*([^\r\n()]{2,80}?)\s*\(\s*([A-Z0-9]{3})\s*\)\s*$")
TEAM_CODE_RE = re.compile(r"\(\s*([A-Z0-9]{3})\s*\)", re.IGNORECASE)
POSITION = r"Libero(?:\s+[12])?|Setter|Outside spiker|Outside hitter|Middle blocker|Middle|Opposite(?: hitter)?"
PLAYER_RE = re.compile(
    rf"^\s*(\d{{1,2}})\s+(.+?)\s+({POSITION})\s+(\d{{1,4}}[./-]\d{{1,2}}[./-]\d{{1,4}})\s+(.+)$",
    re.IGNORECASE,
)
FALLBACK_PLAYER_RE = re.compile(
    r"^\s*(\d{1,2})\s+(.+?)\s+(\d{1,4}[./-]\d{1,2}[./-]\d{1,4})\s+(.+)$",
    re.IGNORECASE,
)
DATE_IN_LINE = re.compile(r"\b\d{1,4}[./-]\d{1,2}[./-]\d{1,4}\b")
POSITION_ALIASES = (
    "libero 1", "libero 2", "outside spiker", "outside hitter", "middle blocker",
    "opposite hitter", "setter", "middle", "opposite",
)
OCR_CODE_TRANSLATION = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B"})
OCR_JERSEY_TRANSLATION = str.maketrans({
    "O": "0", "I": "1", "L": "1", "|": "1", "!": "1",
    "Z": "2", "S": "5", "G": "6", "B": "8",
})
FIVB_TEAM_RE = re.compile(r"(?mi)^\s*([A-Z]{3})\s+[●•\-–—]\s+([^\r\n]+?)\s*$")
FIVB_DATE = r"\d{1,2}-[A-Za-z]{3}-\d{4}"
FIVB_PLAYER_RE = re.compile(
    rf"^\s*(\d{{1,2}})\s+(?:C\s+)?(.+?)\s+(OH|OP|MB|S|L)\s+({FIVB_DATE})\s+(\d{{3}})\b",
    re.IGNORECASE,
)
FIVB_REGISTRATION_PLAYER_RE = re.compile(
    rf"^\s*\d{{4,8}}\s+(?:\S+\s+){{0,4}}?(\d{{1,2}})\s+(?:[CL]\s+)?(.+?)\s+"
    rf"(OH|OP|MB|S|L)\s+({FIVB_DATE})\s+(\d{{3}})\b",
    re.IGNORECASE,
)
FIVB_POSITION_MAPPING = {
    "S": "Setter",
    "OH": "Outside spiker",
    "OP": "Opposite",
    "MB": "Middle blocker",
    "L": "Libero",
}
FIVB_OCR_POSITION_MAPPING = {
    "OH": "OH", "0H": "OH", "OI": "OH",
    "OP": "OP", "0P": "OP",
    "MB": "MB", "M8": "MB",
    "S": "S", "5": "S",
    "L": "L", "I": "L",
}
COMPLETENESS_WARNING_RE = re.compile(
    r"^VOLLEDIGHEIDSCONTROLE:\s+([A-Z0-9]{3})\s+bevat circa\s+(\d+)\s+spelersregels,\s+"
    r"maar er zijn\s+(\d+)\s+herkend\.",
    re.IGNORECASE,
)


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

    def score(self, pages: list[str]) -> int:
        return 1 if self.supports(pages) else -1


class CEVRosterParser(BaseRosterParser):
    name = "CEV/WEVZA"

    def supports(self, pages: list[str]) -> bool:
        return any(self._is_roster_page(page) for page in pages)

    def score(self, pages: list[str]) -> int:
        text = "\n".join(pages).upper()
        if not self.supports(pages):
            return -1
        score = 2
        score += 5 if "FINAL TEAM LIST" in text else 0
        score += 3 if "PERSONAL DATA" in text else 0
        score += 2 if len(DATE_IN_LINE.findall(text)) >= 3 else 0
        return score

    @staticmethod
    def _is_roster_page(page: str) -> bool:
        if extract_structured_roster_rows(page):
            return True
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
    def _team_from_page(page: str) -> tuple[str, str] | None:
        header_position = page.upper().find("FINAL TEAM LIST")
        header = page[:header_position] if header_position >= 0 else page
        matches = list(TEAM_RE.finditer(header))
        if matches:
            match = matches[-1]
            country_name = re.sub(r"\s+", " ", match.group(1)).strip().title()
            raw_code = match.group(2)
        else:
            code_matches = list(TEAM_CODE_RE.finditer(header))
            if not code_matches:
                return None
            code_match = code_matches[-1]
            raw_code = code_match.group(1)
            preceding_line = header[:code_match.start()].splitlines()[-1] if header[:code_match.start()].splitlines() else ""
            country_name = re.sub(r"\s+", " ", preceding_line).strip(" -|").title()
        country_code = raw_code.upper().translate(OCR_CODE_TRANSLATION)
        if not re.fullmatch(r"[A-Z]{3}", country_code):
            return None
        if not country_name:
            country_name = country_code
        return country_name, country_code

    @staticmethod
    def _match_player_line(line: str) -> tuple[str, str, str, str, str] | None:
        exact = PLAYER_RE.match(line)
        if exact:
            return exact.groups()
        fallback = FALLBACK_PLAYER_RE.match(line)
        if not fallback:
            return None
        jersey, prefix, raw_date, remainder = fallback.groups()
        words = prefix.split()
        best: tuple[float, int, str] | None = None
        for width in (1, 2):
            if len(words) <= width:
                continue
            observed = " ".join(words[-width:]).lower().replace("|", "l")
            for alias in POSITION_ALIASES:
                score = SequenceMatcher(None, observed, alias).ratio()
                if best is None or score > best[0]:
                    best = (score, width, alias)
        if best is None or best[0] < 0.72:
            # Keep a date-bearing row even when OCR has damaged the position.
            # The complete text before the date is retained as the original
            # name so the coach can correct it instead of recreating the row.
            full_name = prefix.strip()
            if not full_name:
                return None
            return jersey, full_name, "Onbekend", raw_date, remainder
        _, width, position = best
        full_name = " ".join(words[:-width]).strip()
        if not full_name:
            return None
        return jersey, full_name, position, raw_date, remainder

    @staticmethod
    def _date_lines(text: str) -> list[str]:
        """Return physical OCR lines containing a player-like date before officials."""
        player_section = re.split(r"TEAM OFFICIAL", text, maxsplit=1, flags=re.IGNORECASE)[0]
        return [
            re.sub(r"\s+", " ", line).strip()
            for line in player_section.splitlines()
            if DATE_IN_LINE.search(line)
        ]

    @staticmethod
    def _position_from_prefix(prefix: str, threshold: float = 0.60) -> tuple[str, str | None]:
        words = prefix.split()
        best: tuple[float, int, str] | None = None
        for width in (1, 2):
            if len(words) <= width:
                continue
            observed = " ".join(words[-width:]).lower().replace("|", "l")
            for alias in POSITION_ALIASES:
                score = SequenceMatcher(None, observed, alias).ratio()
                if best is None or score > best[0]:
                    best = (score, width, alias)
        if best is None or best[0] < threshold:
            return prefix.strip(), None
        _, width, position = best
        return " ".join(words[:-width]).strip(), position

    @classmethod
    def _salvage_date_line(cls, line: str) -> tuple[int | None, str, str, str, str] | None:
        """Keep an OCR row even when its jersey column or row start is damaged."""
        date_match = DATE_IN_LINE.search(line)
        if not date_match:
            return None
        prefix = re.sub(r"^[^\wÀ-ÿ|!]+", "", line[:date_match.start()]).strip()
        prefix = re.sub(r"^[|Il!]+\s*(?=\d{1,2}\s)", "", prefix)
        remainder = line[date_match.end():].strip()
        raw_date = date_match.group(0)
        if not prefix:
            return None

        jersey: int | None = None
        number_match = re.match(r"^(\d{1,2})\s+(.+)$", prefix)
        if number_match:
            jersey = int(number_match.group(1))
            prefix = number_match.group(2).strip()
        else:
            tokens = prefix.split()
            if len(tokens) >= 3 and len(tokens[0]) <= 2:
                translated = tokens[0].upper().translate(OCR_JERSEY_TRANSLATION)
                if translated.isdigit() and 0 < int(translated) <= 99:
                    jersey = int(translated)
                    prefix = " ".join(tokens[1:]).strip()

        full_name, position_hint = cls._position_from_prefix(prefix)
        if not full_name:
            full_name = prefix or "Onbekende speler"
        position = f"Controleren - voorstel: {position_hint}" if position_hint else "Controleren"
        return jersey, full_name, position, raw_date, remainder

    @staticmethod
    def _height_from_remainder(remainder: str) -> int | None:
        numbers = [int(value) for value in re.findall(r"(?<!\w)(\d{1,3})(?!\w)", remainder)]
        return next((value for value in numbers if 140 <= value <= 215), None)

    @staticmethod
    def _player_lines(text: str) -> list[str]:
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        result: list[str] = []
        current = ""
        pending_prefix = ""
        late_name_continuation = False
        for line in lines:
            line = re.sub(r"^[|Il!]+\s*(?=\d{1,2}\s)", "", line)
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

        for page_number, page in enumerate(pages, start=1):
            if not self._is_roster_page(page):
                continue
            team = self._team_from_page(page)
            if not team:
                country_code = f"P{page_number:02d}"[-3:]
                country_name = f"Onbekend team pagina {page_number}"
                warnings.append(
                    f"VOLLEDIGHEIDSCONTROLE: De teamkop op pagina {page_number} was niet herkenbaar. "
                    f"De spelers zijn opgenomen onder tijdelijke code {country_code}; corrigeer teamnaam en code."
                )
            else:
                country_name, country_code = team
            teams.append({"country_code": country_code, "country_name": country_name})

            header_position = page.upper().find("FINAL TEAM LIST")
            roster = page[header_position:] if header_position >= 0 else page
            player_section = re.split(r"TEAM OFFICIAL", roster, maxsplit=1, flags=re.IGNORECASE)[0]
            structured_rows = extract_structured_roster_rows(page)
            if structured_rows:
                for row in structured_rows:
                    position_key = re.sub(r"[^A-Z0-9]", "", row.position.upper())
                    position_code = FIVB_OCR_POSITION_MAPPING.get(position_key, position_key)
                    position = FIVB_POSITION_MAPPING.get(position_code, row.position or "Controleren")
                    candidates.append(
                        {
                            "country_code": country_code,
                            "country_name": country_name,
                            "jersey_number": row.jersey_number,
                            "last_name": row.last_name,
                            "first_name": row.first_name,
                            "full_name_original": row.full_name,
                            "position_original": position,
                            "raw_birth_date": row.raw_birth_date,
                            "height_cm": row.height_cm,
                            "split_ok": bool(row.last_name and row.first_name),
                        }
                    )
                continue
            expected_rows = len(DATE_IN_LINE.findall(player_section))
            matched_rows = 0
            matched_players: Counter[tuple[int | None, str]] = Counter()
            for line in self._player_lines(roster):
                match = self._match_player_line(line)
                if not match:
                    if DATE_IN_LINE.search(line):
                        warnings.append(f"Mogelijke spelersregel niet herkend ({country_code}).")
                    continue
                matched_rows += 1
                jersey, full_name, position, raw_date, remainder = match
                jersey_number = int(jersey)
                matched_players[(jersey_number, raw_date)] += 1
                height = self._height_from_remainder(remainder)
                last_name, first_name, split_ok = self._split_name(full_name)
                candidates.append(
                    {
                        "country_code": country_code,
                        "country_name": country_name,
                        "jersey_number": jersey_number,
                        "last_name": last_name,
                        "first_name": first_name,
                        "full_name_original": full_name.strip(),
                        "position_original": position.strip(),
                        "raw_birth_date": raw_date,
                        "height_cm": height,
                        "split_ok": split_ok,
                    }
                )
            salvaged_rows = 0
            for line in self._date_lines(roster):
                salvaged = self._salvage_date_line(line)
                if not salvaged:
                    continue
                jersey, full_name, position, raw_date, remainder = salvaged
                matched_key = (jersey, raw_date)
                if jersey is not None and matched_players[matched_key] > 0:
                    matched_players[matched_key] -= 1
                    continue
                last_name, first_name, split_ok = self._split_name(full_name)
                candidates.append(
                    {
                        "country_code": country_code,
                        "country_name": country_name,
                        "jersey_number": jersey,
                        "last_name": last_name,
                        "first_name": first_name,
                        "full_name_original": full_name.strip(),
                        "position_original": position,
                        "raw_birth_date": raw_date,
                        "height_cm": self._height_from_remainder(remainder),
                        "split_ok": split_ok,
                    }
                )
                matched_rows += 1
                salvaged_rows += 1
            if salvaged_rows:
                warnings.append(
                    f"{country_code}: {salvaged_rows} extra regel(s) toegevoegd die gecontroleerd moeten worden."
                )
            if expected_rows > matched_rows:
                warnings.append(
                    f"VOLLEDIGHEIDSCONTROLE: {country_code} bevat circa {expected_rows} spelersregels, "
                    f"maar er zijn er {matched_rows} herkend. Controleer en vul ontbrekende spelers aan."
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
            elif birth.year < 1950:
                row_warnings.append("Geboortejaar is onwaarschijnlijk; controleer de datum.")
            if item["height_cm"] is None:
                row_warnings.append("Lengte ontbreekt.")
            elif not 140 <= item["height_cm"] <= 215:
                row_warnings.append("Lengte valt buiten de gebruikelijke controlegrenzen (140-215 cm).")
            if not item["split_ok"]:
                row_warnings.append("Voor- en achternaam konden niet betrouwbaar worden gesplitst.")
            if item["jersey_number"] is None:
                row_warnings.append("Rugnummer ontbreekt.")
            duplicate_key = (item["country_code"], item["jersey_number"])
            if item["jersey_number"] is not None:
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


class FIVBRosterParser(BaseRosterParser):
    """Parser for FIVB Team composition tables with named month dates."""

    name = "FIVB"

    def supports(self, pages: list[str]) -> bool:
        return any(self._is_possible_roster_page(page) for page in pages)

    def score(self, pages: list[str]) -> int:
        text = "\n".join(pages).upper()
        if not self.supports(pages):
            return -1
        score = 2
        score += 6 if "NO FIVB" in text or "O-2BIS" in text else 0
        score += 4 if "TEAM REGISTRATION" in text or "TEAM COMPOSITION" in text else 0
        score += 3 if re.search(FIVB_DATE, text, re.IGNORECASE) else 0
        return score

    @staticmethod
    def _is_roster_page(page: str) -> bool:
        if extract_structured_roster_rows(page):
            return True
        upper = page.upper()
        dates = len(re.findall(FIVB_DATE, page, re.IGNORECASE))
        marker_groups = [
            "TEAM COMPOSITION" in upper or "TEAM REGISTRATION" in upper,
            "BIRTHDATE" in upper or "BIRTH DATE" in upper,
            "SHIRT" in upper or "NO FIVB" in upper,
            "RESERVE PLAYERS" in upper or "OFFICIALS" in upper,
            "HEIGHT" in upper or "HIGHEST REACH" in upper,
        ]
        return dates >= 3 and sum(marker_groups) >= 2

    @classmethod
    def _is_possible_roster_page(cls, page: str) -> bool:
        if cls._is_roster_page(page):
            return True
        upper = page.upper()
        dates = len(re.findall(FIVB_DATE, page, re.IGNORECASE))
        roster_marker = any(
            marker in upper
            for marker in ("TEAM REGISTRATION", "BIRTHDATE", "BIRTH DATE", "NO FIVB", "RESERVE PLAYERS")
        )
        return dates >= 1 and roster_marker and cls._team_from_page(page) is not None

    @staticmethod
    def _team_from_page(page: str) -> tuple[str, str] | None:
        match = FIVB_TEAM_RE.search(page)
        if not match:
            return None
        return re.sub(r"\s+", " ", match.group(2)).strip(), match.group(1).upper()

    @staticmethod
    def _numeric_date(raw_date: str) -> str | None:
        parsed = parse_date(raw_date.replace("-", " "), "DMY")
        return parsed.strftime("%d/%m/%Y") if parsed else None

    @staticmethod
    def _clean_cell(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    @classmethod
    def _synthetic_page(
        cls,
        team: tuple[str, str],
        rows: list[tuple[int | None, str, str, str, str, int | None]],
    ) -> str:
        country_name, country_code = team
        lines = [
            f"{country_name} ({country_code})",
            "FINAL TEAM LIST AND DELEGATION",
            "Name & First Name Position Birth Date Weight Height",
        ]
        for jersey, last_name, first_name, position, raw_date, height in rows:
            numeric_date = cls._numeric_date(raw_date)
            if not numeric_date:
                continue
            full_name = f"{last_name.upper()} {first_name}".strip()
            position_label = FIVB_POSITION_MAPPING.get(position.upper(), "Controleren")
            lines.append(
                f"{jersey if jersey is not None else ''} {full_name} {position_label} "
                f"{numeric_date} 0 {height or 0}"
            )
        lines.append("TEAM OFFICIALS:")
        return "\n".join(lines)

    @classmethod
    def _rows_from_tables(cls, tables: list[list[list[Any]]]) -> list[tuple[int, str, str, str, str, int]]:
        for table in tables:
            header_index: int | None = None
            columns: dict[str, int] = {}
            for index, row in enumerate(table[:5]):
                cells = [cls._clean_cell(cell).casefold() for cell in row]
                wanted = {
                    "shirt": next((i for i, value in enumerate(cells) if value.startswith("shirt")), None),
                    "last": next((i for i, value in enumerate(cells) if "last name" in value), None),
                    "first": next((i for i, value in enumerate(cells) if "first name" in value), None),
                    "position": next((i for i, value in enumerate(cells) if value.rstrip(".") == "pos"), None),
                    "birthdate": next((i for i, value in enumerate(cells) if "birthdate" in value), None),
                    "height": next((i for i, value in enumerate(cells) if value.startswith("height")), None),
                }
                if all(value is not None for value in wanted.values()):
                    header_index = index
                    columns = {key: int(value) for key, value in wanted.items() if value is not None}
                    break
            if header_index is None:
                continue
            rows: list[tuple[int, str, str, str, str, int]] = []
            for row in table[header_index + 1:]:
                if len(row) <= max(columns.values()):
                    continue
                jersey_match = re.match(r"^(\d{1,2})\b", cls._clean_cell(row[columns["shirt"]]))
                position = cls._clean_cell(row[columns["position"]]).upper()
                raw_date = cls._clean_cell(row[columns["birthdate"]])
                height_text = cls._clean_cell(row[columns["height"]])
                if not jersey_match or position not in FIVB_POSITION_MAPPING or not re.fullmatch(FIVB_DATE, raw_date):
                    continue
                if not height_text.isdigit():
                    continue
                rows.append((
                    int(jersey_match.group(1)),
                    cls._clean_cell(row[columns["last"]]),
                    cls._clean_cell(row[columns["first"]]),
                    position,
                    raw_date,
                    int(height_text),
                ))
            if rows:
                return rows
        return []

    @staticmethod
    def _split_text_name(prefix: str) -> tuple[str, str]:
        """Best-effort fallback when PDF table geometry is unavailable."""
        tokens = prefix.split()
        if len(tokens) < 2:
            return prefix, ""
        normalized = [re.sub(r"[^a-z0-9]", "", token.casefold()) for token in tokens]
        shirt_start: int | None = None
        match_at: int | None = None
        for start in range(1, len(tokens)):
            first = normalized[start]
            previous = next((index for index, value in enumerate(normalized[:start]) if value == first), None)
            if previous is not None:
                shirt_start, match_at = start, previous
                break
        if shirt_start is None:
            official = tokens[:-1] if len(tokens) > 2 else tokens
            return official[0], " ".join(official[1:])
        official = tokens[:shirt_start]
        boundary = match_at if match_at and match_at > 0 else 1
        return " ".join(official[:boundary]), " ".join(official[boundary:])

    @classmethod
    def _rows_from_text(cls, page: str) -> list[tuple[int, str, str, str, str, int]]:
        rows: list[tuple[int, str, str, str, str, int]] = []
        seen: set[tuple[int, str]] = set()
        for line in page.splitlines():
            clean = re.sub(r"\s+", " ", line).strip()
            match = FIVB_PLAYER_RE.match(clean) or FIVB_REGISTRATION_PLAYER_RE.match(clean)
            if not match:
                continue
            jersey, prefix, position, raw_date, height = match.groups()
            key = (int(jersey), raw_date.casefold())
            if key in seen:
                continue
            seen.add(key)
            last_name, first_name = cls._split_text_name(prefix)
            rows.append((int(jersey), last_name, first_name, position.upper(), raw_date, int(height)))
        return rows

    @classmethod
    def _rows_from_page(
        cls, page: str
    ) -> list[tuple[int | None, str, str, str, str, int | None]]:
        """Prefer header-addressed cells and use prose reconstruction as fallback."""
        structured = extract_structured_roster_rows(page)
        rows: list[tuple[int | None, str, str, str, str, int | None]] = []
        for row in structured:
            raw_position = re.sub(r"[^A-Z0-9]", "", row.position.upper())
            position = FIVB_OCR_POSITION_MAPPING.get(raw_position, raw_position)
            rows.append(
                (
                    row.jersey_number,
                    row.last_name,
                    row.first_name,
                    position,
                    row.raw_birth_date,
                    row.height_cm,
                )
            )
        return rows or cls._rows_from_text(page)

    @classmethod
    def _salvage_scan_line(
        cls, line: str
    ) -> tuple[int | None, str, str, str, str, int | None] | None:
        """Recover a reviewable FIVB row when OCR damaged its column structure."""
        date_match = re.search(FIVB_DATE, line, re.IGNORECASE)
        if not date_match:
            return None
        prefix = re.sub(r"\s+", " ", line[:date_match.start()]).strip()
        suffix = line[date_match.end():]
        raw_date = date_match.group(0)
        height = next(
            (int(value) for value in re.findall(r"(?<!\d)(\d{3})(?!\d)", suffix) if 140 <= int(value) <= 215),
            None,
        )

        tokens = prefix.split()
        jersey_index = next(
            (
                index
                for index, token in enumerate(tokens)
                if re.fullmatch(r"\d{1,2}", token) and 0 < int(token) <= 99
            ),
            None,
        )
        jersey = int(tokens[jersey_index]) if jersey_index is not None else None
        name_start = jersey_index + 1 if jersey_index is not None else 0
        if name_start < len(tokens) and tokens[name_start].upper() in {"C", "L"}:
            name_start += 1

        position_index: int | None = None
        position = ""
        for index in range(len(tokens) - 1, name_start - 1, -1):
            cleaned = re.sub(r"[^A-Z0-9]", "", tokens[index].upper())
            mapped = FIVB_OCR_POSITION_MAPPING.get(cleaned)
            if mapped:
                position_index = index
                position = mapped
                break
        name_tokens = tokens[name_start:position_index] if position_index is not None else tokens[name_start:]
        while name_tokens and re.fullmatch(r"\d{4,8}|[✓✔☑□|]", name_tokens[0]):
            name_tokens.pop(0)
        full_name = " ".join(name_tokens).strip() or "Onbekende speler"
        last_name, first_name = cls._split_text_name(full_name)
        return jersey, last_name, first_name, position, raw_date, height

    @classmethod
    def _add_salvaged_scan_rows(
        cls,
        result: ParseResult,
        source_pages: list[tuple[int, str, tuple[str, str], bool]],
    ) -> ParseResult:
        existing = {
            (
                player.country_code,
                player.jersey_number,
                player.birth_date.isoformat() if player.birth_date else player.raw_birth_date.casefold(),
            )
            for player in result.players
        }
        teams = {(team["country_code"], team["country_name"]) for team in result.teams}
        added_by_country: Counter[str] = Counter()
        seen_lines: set[tuple[str, int | None, str, str]] = set()
        for _, page, (country_name, country_code), _ in source_pages:
            teams.add((country_code, country_name))
            player_section = re.split(r"\bOFFICIALS\b", page, maxsplit=1, flags=re.IGNORECASE)[0]
            for line in player_section.splitlines():
                salvaged = cls._salvage_scan_line(line)
                if not salvaged:
                    continue
                jersey, last_name, first_name, position, raw_date, height = salvaged
                numeric_date = cls._numeric_date(raw_date)
                birth_date = parse_date(numeric_date, "DMY") if numeric_date else None
                date_key = birth_date.isoformat() if birth_date else raw_date.casefold()
                identity = (country_code, jersey, date_key)
                line_key = (country_code, jersey, date_key, f"{last_name} {first_name}".casefold())
                if identity in existing or line_key in seen_lines:
                    continue
                seen_lines.add(line_key)
                existing.add(identity)
                position_original = FIVB_POSITION_MAPPING.get(position, "Controleren")
                normalized, _ = normalize_position(position_original)
                row_warnings = ["Regel automatisch uit de scan toegevoegd; controleer de gegevens."]
                if jersey is None:
                    row_warnings.append("Rugnummer ontbreekt.")
                if not position:
                    row_warnings.append("Positie ontbreekt.")
                if height is None:
                    row_warnings.append("Lengte ontbreekt.")
                result.players.append(
                    ParsedPlayer(
                        country_code=country_code,
                        country_name=country_name,
                        jersey_number=jersey,
                        last_name=last_name,
                        first_name=first_name,
                        full_name_original=f"{last_name} {first_name}".strip(),
                        position_original=position_original,
                        position_normalized=normalized,
                        raw_birth_date=numeric_date or raw_date,
                        birth_date=birth_date,
                        height_cm=height,
                        extraction_status="Controleren",
                        extraction_warning="; ".join(row_warnings),
                    )
                )
                added_by_country[country_code] += 1
        result.teams = [
            {"country_code": code, "country_name": name}
            for code, name in sorted(teams)
        ]
        if added_by_country:
            result.date_order = "DMY"
        for country_code, count in sorted(added_by_country.items()):
            result.warnings.append(
                f"{country_code}: {count} extra regel(s) uit de scan toegevoegd die gecontroleerd moeten worden."
            )
        return result

    def _parse_synthetic(
        self,
        synthetic_pages: list[str],
        forced_date_order: DateOrder | None,
    ) -> ParseResult:
        result = CEVRosterParser().parse(synthetic_pages, forced_date_order)
        result.profile = self.name
        return result

    @staticmethod
    def _temporary_team(page_number: int) -> tuple[str, str]:
        offset = max(0, page_number - 1)
        code = f"P{chr(ord('A') + (offset // 26) % 26)}{chr(ord('A') + offset % 26)}"
        return f"Onbekend team pagina {page_number}", code

    @classmethod
    def _add_fivb_checks(
        cls,
        result: ParseResult,
        source_pages: list[tuple[int, str, tuple[str, str], bool]],
    ) -> ParseResult:
        counts = Counter(player.country_code for player in result.players)
        for page_number, page, (_, country_code), temporary in source_pages:
            if temporary:
                result.warnings.append(
                    f"VOLLEDIGHEIDSCONTROLE: De teamkop op pagina {page_number} was niet herkenbaar. "
                    f"De spelers zijn opgenomen onder tijdelijke code {country_code}; corrigeer teamnaam en code."
                )
            player_section = re.split(r"\bOFFICIALS\b", page, maxsplit=1, flags=re.IGNORECASE)[0]
            structured_rows = extract_structured_roster_rows(page)
            expected = len(structured_rows) or len(
                set(re.findall(FIVB_DATE, player_section, re.IGNORECASE))
            )
            if expected > counts[country_code]:
                result.warnings.append(
                    f"VOLLEDIGHEIDSCONTROLE: {country_code} bevat circa {expected} spelersregels, "
                    f"maar er zijn er {counts[country_code]} herkend. Controleer en vul ontbrekende spelers aan."
                )
        return result

    def parse(self, pages: list[str], forced_date_order: DateOrder | None = None) -> ParseResult:
        synthetic_pages = []
        source_pages: list[tuple[int, str, tuple[str, str], bool]] = []
        for index, page in enumerate(pages, start=1):
            if not self._is_possible_roster_page(page):
                continue
            detected_team = self._team_from_page(page)
            team = detected_team or self._temporary_team(index)
            source_pages.append((index, page, team, detected_team is None))
            synthetic_pages.append(self._synthetic_page(team, self._rows_from_page(page)))
        result = self._parse_synthetic(synthetic_pages, forced_date_order)
        result = self._add_salvaged_scan_rows(result, source_pages)
        return self._add_fivb_checks(result, source_pages)

    def parse_document(
        self,
        source: bytes | str,
        pages: list[str],
        forced_date_order: DateOrder | None = None,
    ) -> ParseResult:
        """Use PDF table geometry when available and fall back to extracted text per page."""
        fallback_by_page: dict[int, str] = {}
        source_pages: list[tuple[int, str, tuple[str, str], bool]] = []
        teams_by_page: dict[int, tuple[str, str]] = {}
        for index, page in enumerate(pages):
            if not self._is_possible_roster_page(page):
                continue
            detected_team = self._team_from_page(page)
            team = detected_team or self._temporary_team(index + 1)
            teams_by_page[index] = team
            source_pages.append((index + 1, page, team, detected_team is None))
            fallback_by_page[index] = self._synthetic_page(team, self._rows_from_page(page))

        structured_by_page: dict[int, str] = {}
        raw = source if isinstance(source, bytes) else Path(source).read_bytes()
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(raw)) as pdf:
                for index in fallback_by_page:
                    team = teams_by_page[index]
                    rows = self._rows_from_tables(pdf.pages[index].extract_tables())
                    if rows:
                        structured_by_page[index] = self._synthetic_page(team, rows)
        except Exception:
            structured_by_page = {}

        merged = [structured_by_page.get(index, page) for index, page in fallback_by_page.items()]
        result = self._parse_synthetic(merged, forced_date_order)
        unstructured_pages = [
            item for item in source_pages if not extract_structured_roster_rows(item[1])
        ]
        result = self._add_salvaged_scan_rows(result, unstructured_pages)
        return self._add_fivb_checks(result, source_pages)


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
                "of kon een afbeeldingspagina niet betrouwbaar worden gelezen."
            ],
        )


def parse_bulletin(source: bytes | str, forced_date_order: DateOrder | None = None) -> ParseResult:
    pages = extract_pages(source)
    parsers: list[BaseRosterParser] = [FIVBRosterParser(), CEVRosterParser(), GenericRosterParser()]
    parser = max(parsers, key=lambda candidate: candidate.score(pages))
    if isinstance(parser, FIVBRosterParser):
        result = parser.parse_document(source, pages, forced_date_order)
    else:
        result = parser.parse(pages, forced_date_order)
    return _add_missing_concept_rows(result)


def _add_missing_concept_rows(result: ParseResult) -> ParseResult:
    """Never discard an estimated player row merely because its fields are unreadable."""
    estimates: dict[str, int] = {}
    retained_warnings: list[str] = []
    for warning in result.warnings:
        match = COMPLETENESS_WARNING_RE.match(warning)
        if match:
            country_code, expected, _ = match.groups()
            estimates[country_code.upper()] = max(estimates.get(country_code.upper(), 0), int(expected))
        else:
            retained_warnings.append(warning)
    if not estimates:
        return result

    country_names = {team["country_code"]: team["country_name"] for team in result.teams}
    counts = Counter(player.country_code for player in result.players)
    added: Counter[str] = Counter()
    for country_code, expected in estimates.items():
        missing = max(0, expected - counts[country_code])
        for index in range(missing):
            concept_number = counts[country_code] + index + 1
            result.players.append(
                ParsedPlayer(
                    country_code=country_code,
                    country_name=country_names.get(country_code, country_code),
                    jersey_number=None,
                    last_name="Controleren",
                    first_name=f"Speler {concept_number}",
                    full_name_original="",
                    position_original="Controleren",
                    position_normalized="ONB",
                    raw_birth_date="",
                    birth_date=None,
                    height_cm=None,
                    extraction_status="Controleren",
                    extraction_warning=(
                        "Mogelijke spelersregel automatisch toegevoegd. "
                        "Vul rugnummer, naam, positie, geboortedatum en lengte aan."
                    ),
                )
            )
            added[country_code] += 1
        retained_warnings.append(
            f"VOLLEDIGHEIDSCONTROLE: {country_code} bevat circa {expected} spelersregels. "
            f"{added[country_code]} onzekere conceptregel(s) zijn toegevoegd; controleer en vul ze aan."
        )
    if added:
        retained_warnings = [
            warning
            for warning in retained_warnings
            if not warning.startswith("Geen spelersregels gevonden.")
        ]
        result.date_order = "DMY"
    result.warnings = retained_warnings
    return result
