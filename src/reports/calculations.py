from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

NET_POSITIONS = {"SV", "PL", "DIA", "MB"}


def age_on_date(birth_date: date, on_date: date) -> float:
    days = (on_date - birth_date).days
    return round(days / 365.2425, 2)


def birth_quarter(value: date) -> str:
    return f"Q{((value.month - 1) // 3) + 1}"


def pearson(values_x: list[float], values_y: list[float]) -> float | None:
    if len(values_x) < 3 or len(values_x) != len(values_y):
        return None
    if len(set(values_x)) < 2 or len(set(values_y)) < 2:
        return None
    return float(np.corrcoef(values_x, values_y)[0, 1])


def prepare_players(players: list[dict[str, Any]], tournament_start: date) -> pd.DataFrame:
    frame = pd.DataFrame(players)
    if frame.empty:
        return frame
    frame["birth_date"] = pd.to_datetime(frame["birth_date"], errors="coerce")
    frame["height_cm"] = pd.to_numeric(frame["height_cm"], errors="coerce")
    frame["age"] = frame["birth_date"].apply(
        lambda value: age_on_date(value.date(), tournament_start) if pd.notna(value) else np.nan
    )
    frame["birth_year"] = frame["birth_date"].dt.year.astype("Int64")
    frame["birth_month"] = frame["birth_date"].dt.month.astype("Int64")
    frame["quarter"] = frame["birth_date"].apply(
        lambda value: birth_quarter(value.date()) if pd.notna(value) else ""
    )
    return frame


def build_report_data(tournament: dict[str, Any], teams: list[dict[str, Any]], players: list[dict[str, Any]]) -> dict[str, Any]:
    start = _date(tournament["start_date"])
    frame = prepare_players(players, start)
    country_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    if not frame.empty:
        for code, group in frame.groupby("country_code", sort=True):
            net = group[group["position_normalized"].isin(NET_POSITIONS)]
            country_rows.append(
                {
                    "country_code": code,
                    "country_name": group["country_name"].iloc[0],
                    "players": int(len(group)),
                    "avg_age": _mean(group["age"]),
                    "avg_net_height": _mean(net["height_cm"]),
                    **{quarter: int((group["quarter"] == quarter).sum()) for quarter in ("Q1", "Q2", "Q3", "Q4")},
                }
            )
        for position, group in frame.groupby("position_normalized", sort=True):
            position_rows.append(
                {"position": position, "players": int(len(group)), "avg_height": _mean(group["height_cm"]), "avg_age": _mean(group["age"])}
            )

    ranking_map = {team["country_code"]: team.get("final_ranking") for team in teams}
    for row in country_rows:
        row["ranking"] = ranking_map.get(row["country_code"])
    country_rows.sort(key=lambda row: _ranking_sort_key(row["country_code"], ranking_map))
    result_rows: list[dict[str, Any]] = []
    for row in country_rows:
        result_rows.append(
            {
                "country_code": row["country_code"],
                "ranking": ranking_map.get(row["country_code"]),
                "avg_net_height": row["avg_net_height"],
                "avg_age": row["avg_age"],
            }
        )
    complete = bool(result_rows) and all(row["ranking"] is not None for row in result_rows)
    corr_height = pearson(
        [float(row["ranking"]) for row in result_rows],
        [float(row["avg_net_height"]) for row in result_rows],
    ) if complete and all(row["avg_net_height"] is not None for row in result_rows) else None
    corr_age = pearson(
        [float(row["ranking"]) for row in result_rows],
        [float(row["avg_age"]) for row in result_rows],
    ) if complete and all(row["avg_age"] is not None for row in result_rows) else None

    quarters = {q: int((frame["quarter"] == q).sum()) if not frame.empty else 0 for q in ("Q1", "Q2", "Q3", "Q4")}
    years = (
        {int(k): int(v) for k, v in frame["birth_year"].dropna().value_counts().sort_index().items()}
        if not frame.empty else {}
    )
    return {
        "tournament": tournament,
        "teams": teams,
        "players_frame": frame,
        "summary": {
            "teams": len(teams), "players": len(frame), "avg_age": _mean(frame.get("age", pd.Series(dtype=float))),
            "avg_height": _mean(frame.get("height_cm", pd.Series(dtype=float))),
        },
        "countries": country_rows,
        "positions": position_rows,
        "birth_years": years,
        "quarters": quarters,
        "results": result_rows,
        "correlations": {"ranking_height": corr_height, "ranking_age": corr_age},
    }


def _ranking_sort_key(country_code: str, ranking_map: dict[str, Any]) -> tuple[bool, float, str]:
    """Sort ranked teams from 1 through x and keep unranked teams last."""
    ranking = ranking_map.get(country_code)
    return (ranking is None, float(ranking) if ranking is not None else float("inf"), country_code)


def _mean(series: pd.Series) -> float | None:
    result = series.mean()
    return None if pd.isna(result) else round(float(result), 2)


def _date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])
