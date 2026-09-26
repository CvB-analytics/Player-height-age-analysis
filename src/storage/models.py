from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Tournament:
    name: str
    category: str
    gender: str
    location: str
    start_date: date
    end_date: date | None = None
    source_file: str | None = None


@dataclass
class Team:
    tournament_id: int
    country_code: str
    country_name: str
    final_ranking: int | None = None
