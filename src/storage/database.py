from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS tournament (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    gender TEXT NOT NULL,
    location TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    source_file TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS team (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
    country_code TEXT NOT NULL,
    country_name TEXT NOT NULL,
    final_ranking INTEGER,
    UNIQUE(tournament_id, country_code)
);
CREATE TABLE IF NOT EXISTS player (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
    team_id INTEGER NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    jersey_number INTEGER,
    last_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    full_name_original TEXT,
    position_original TEXT,
    position_normalized TEXT,
    birth_date TEXT,
    height_cm INTEGER,
    extraction_status TEXT,
    extraction_warning TEXT
);
CREATE TABLE IF NOT EXISTS match (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL REFERENCES tournament(id) ON DELETE CASCADE,
    date TEXT,
    team_a INTEGER REFERENCES team(id),
    team_b INTEGER REFERENCES team(id),
    sets_a INTEGER,
    sets_b INTEGER
);
CREATE INDEX IF NOT EXISTS idx_player_tournament ON player(tournament_id);
CREATE INDEX IF NOT EXISTS idx_team_tournament ON team(tournament_id);
"""


class Database:
    def __init__(self, path: str | Path = "data/app.db") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def create_tournament(self, values: dict[str, Any]) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO tournament
                   (name, category, gender, location, start_date, end_date, source_file)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    values["name"], values["category"], values["gender"], values["location"],
                    _iso(values["start_date"]), _iso(values.get("end_date")), values.get("source_file"),
                ),
            )
            return int(cursor.lastrowid)

    def get_tournaments(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tournament ORDER BY start_date DESC, created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_tournament(self, tournament_id: int) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM tournament WHERE id = ?", (tournament_id,)).fetchone()
        return dict(row) if row else None

    def update_tournament_source(self, tournament_id: int, source_file: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE tournament SET source_file = ? WHERE id = ?", (source_file, tournament_id))

    def save_players(self, tournament_id: int, rows: list[dict[str, Any]]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM player WHERE tournament_id = ?", (tournament_id,))
            teams: dict[str, int] = {}
            imported_codes = sorted({str(row["country_code"]).strip().upper() for row in rows})
            for row in rows:
                code = str(row["country_code"]).strip().upper()
                connection.execute(
                    """INSERT INTO team (tournament_id, country_code, country_name)
                       VALUES (?, ?, ?)
                       ON CONFLICT(tournament_id, country_code)
                       DO UPDATE SET country_name = excluded.country_name""",
                    (tournament_id, code, row.get("country_name") or code),
                )
            if imported_codes:
                placeholders = ",".join("?" for _ in imported_codes)
                connection.execute(
                    f"DELETE FROM team WHERE tournament_id = ? AND country_code NOT IN ({placeholders})",
                    (tournament_id, *imported_codes),
                )
            for team in connection.execute("SELECT id, country_code FROM team WHERE tournament_id = ?", (tournament_id,)):
                teams[team["country_code"]] = team["id"]
            for row in rows:
                code = str(row["country_code"]).strip().upper()
                connection.execute(
                    """INSERT INTO player (
                       tournament_id, team_id, jersey_number, last_name, first_name, full_name_original,
                       position_original, position_normalized, birth_date, height_cm,
                       extraction_status, extraction_warning
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        tournament_id, teams[code], _int_or_none(row.get("jersey_number")),
                        str(row.get("last_name") or "").strip(), str(row.get("first_name") or "").strip(),
                        row.get("full_name_original"), row.get("position_original"), row.get("position_normalized"),
                        _iso(row.get("birth_date")), _int_or_none(row.get("height_cm")),
                        row.get("extraction_status"), row.get("extraction_warning"),
                    ),
                )

    def get_teams(self, tournament_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM team WHERE tournament_id = ? ORDER BY country_code", (tournament_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def get_players(self, tournament_id: int) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT p.*, t.country_code, t.country_name, t.final_ranking
                   FROM player p JOIN team t ON t.id = p.team_id
                   WHERE p.tournament_id = ? ORDER BY t.country_code, p.jersey_number, p.id""",
                (tournament_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_player(self, player_id: int, values: dict[str, Any]) -> None:
        allowed = {
            "jersey_number", "last_name", "first_name", "position_original", "position_normalized",
            "birth_date", "height_cm", "extraction_status", "extraction_warning",
        }
        fields = [key for key in values if key in allowed]
        if not fields:
            return
        sql = ", ".join(f"{field} = ?" for field in fields)
        params = [_iso(values[field]) if field == "birth_date" else values[field] for field in fields]
        with self.connect() as connection:
            connection.execute(f"UPDATE player SET {sql} WHERE id = ?", (*params, player_id))

    def save_ranking(self, tournament_id: int, rankings: dict[int, int | None]) -> None:
        with self.connect() as connection:
            for team_id, ranking in rankings.items():
                connection.execute(
                    "UPDATE team SET final_ranking = ? WHERE id = ? AND tournament_id = ?",
                    (_int_or_none(ranking), team_id, tournament_id),
                )

    def delete_tournament(self, tournament_id: int) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM tournament WHERE id = ?", (tournament_id,))


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
