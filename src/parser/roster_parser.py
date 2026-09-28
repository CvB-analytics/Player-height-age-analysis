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
FIVB_TEAM_RE = re.compile(r"(?mi)^\s*([A-Z]{3})\s+[●•]\s+([^\r\n]+?)\s*$")
FIVB_DATE = r"\d{1,2}-[A-Za-z]{3}-\d{4}"
FIVB_PLAYER_RE = re.compile(
    rf"^\s*(\d{{1,2}})\s+(?:C\s+)?(.+?)\s+(OH|OP|MB|S|L)\s+({FIVB_DATE})\s+(\d{{3}})\b",
    re.IGNORECASE,
)
FIVB_POSITION_MAPPING = {
    "S": "Setter",
    "OH": "Outside spiker",
    "OP": "Opposite",
    "MB": "Middle blocker",
    "L": "Libero",
}


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
            if item["height_cm"] is None:
                row_warnings.append("Lengte ontbreekt.")
            elif not 140 <= item["height_cm"] <= 215:
                row_warnings.append("Lengte valt buiten de gebruikelijke controlegrenzen (140-215 cm).")
            if not item["split_ok"]:
                row_warnings.append("Voor- en achternaam konden niet betrouwbaar worden gesplitst.")
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
        return any(self._is_roster_page(page) for page in pages)

    @staticmethod
    def _is_roster_page(page: str) -> bool:
        upper = page.upper()
        return (
            "TEAM COMPOSITION" in upper
            and "BIRTHDATE" in upper
            and "SHIRT" in upper
            and bool(FIVB_TEAM_RE.search(page))
        )

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
        rows: list[tuple[int, str, str, str, str, int]],
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
            lines.append(
                f"{jersey} {full_name} {FIVB_POSITION_MAPPING[position.upper()]} "
                f"{numeric_date} 0 {height}"
            )
        lines.append("TEAM OFFICIALS:")
        return "\n".join(lines)

    @classmethod
    def _rows_from_tables(cls, tables: list[list[list[Any]]]) -> list[tuple[int, str, str, str, str, int]]:
        for table in tables:
            header = " ".join(cls._clean_cell(cell) for row in table[:3] for cell in row)
            if "Birthdate" not in header or "Last name" not in header:
                continue
            rows: list[tuple[int, str, str, str, str, int]] = []
            for row in table[3:]:
                if len(row) < 7:
                    continue
                jersey_match = re.match(r"^(\d{1,2})\b", cls._clean_cell(row[0]))
                position = cls._clean_cell(row[4]).upper()
                raw_date = cls._clean_cell(row[5])
                height_text = cls._clean_cell(row[6])
                if not jersey_match or position not in FIVB_POSITION_MAPPING or not re.fullmatch(FIVB_DATE, raw_date):
                    continue
                if not height_text.isdigit():
                    continue
                rows.append((
                    int(jersey_match.group(1)),
                    cls._clean_cell(row[1]),
                    cls._clean_cell(row[2]),
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
        for line in page.splitlines():
            match = FIVB_PLAYER_RE.match(re.sub(r"\s+", " ", line).strip())
            if not match:
                continue
            jersey, prefix, position, raw_date, height = match.groups()
            last_name, first_name = cls._split_text_name(prefix)
            rows.append((int(jersey), last_name, first_name, position.upper(), raw_date, int(height)))
        return rows

    def _parse_synthetic(
        self,
        synthetic_pages: list[str],
        forced_date_order: DateOrder | None,
    ) -> ParseResult:
        result = CEVRosterParser().parse(synthetic_pages, forced_date_order)
        result.profile = self.name
        return result

    def parse(self, pages: list[str], forced_date_order: DateOrder | None = None) -> ParseResult:
        synthetic_pages = []
        for page in pages:
            if not self._is_roster_page(page):
                continue
            team = self._team_from_page(page)
            if team:
                synthetic_pages.append(self._synthetic_page(team, self._rows_from_text(page)))
        return self._parse_synthetic(synthetic_pages, forced_date_order)

    def parse_document(
        self,
        source: bytes | str,
        pages: list[str],
        forced_date_order: DateOrder | None = None,
    ) -> ParseResult:
        """Use PDF table geometry when available and fall back to extracted text per page."""
        fallback_by_page: dict[int, str] = {}
        for index, page in enumerate(pages):
            if not self._is_roster_page(page):
                continue
            team = self._team_from_page(page)
            if team:
                fallback_by_page[index] = self._synthetic_page(team, self._rows_from_text(page))

        structured_by_page: dict[int, str] = {}
        raw = source if isinstance(source, bytes) else Path(source).read_bytes()
        try:
            import pdfplumber

            with pdfplumber.open(BytesIO(raw)) as pdf:
                for index in fallback_by_page:
                    team = self._team_from_page(pages[index])
                    rows = self._rows_from_tables(pdf.pages[index].extract_tables())
                    if team and rows:
                        structured_by_page[index] = self._synthetic_page(team, rows)
        except Exception:
            structured_by_page = {}

        merged = [structured_by_page.get(index, page) for index, page in fallback_by_page.items()]
        return self._parse_synthetic(merged, forced_date_order)


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
    parsers: list[BaseRosterParser] = [CEVRosterParser(), FIVBRosterParser(), GenericRosterParser()]
    parser = next(candidate for candidate in parsers if candidate.supports(pages))
    if isinstance(parser, FIVBRosterParser):
        return parser.parse_document(source, pages, forced_date_order)
    return parser.parse(pages, forced_date_order)
