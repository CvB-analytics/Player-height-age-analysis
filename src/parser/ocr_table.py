from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class GridTable:
    x_lines: tuple[int, ...]
    y_lines: tuple[int, ...]


def deskew_table_image(image: Image.Image, max_angle: float = 3.0) -> tuple[Image.Image, float]:
    """Straighten small scan angles by maximizing long horizontal structures."""
    sample = image.convert("L")
    sample.thumbnail((1000, 1000))
    best_angle = 0.0
    best_score = float("-inf")
    for angle in np.arange(-max_angle, max_angle + 0.001, 0.25):
        rotated = sample.rotate(
            float(angle),
            resample=Image.Resampling.BILINEAR,
            expand=False,
            fillcolor=255,
        )
        dark = np.asarray(rotated) < 150
        margin = max(1, int(dark.shape[1] * 0.02))
        projections = dark[:, margin:-margin].mean(axis=1)
        strongest = np.sort(projections)[-min(30, len(projections)) :]
        score = float(np.square(strongest).sum())
        if score > best_score:
            best_score = score
            best_angle = float(angle)
    if abs(best_angle) < 0.12:
        return image.convert("L"), 0.0
    return (
        image.convert("L").rotate(
            best_angle,
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor=255,
        ),
        best_angle,
    )


def detect_grid_table(image: Image.Image) -> GridTable | None:
    """Detect the dominant dense table without knowing its federation or columns."""
    grayscale = np.asarray(image.convert("L"))
    dark = grayscale < 130
    height, width = dark.shape
    x_margin = max(1, int(width * 0.02))
    horizontal_scores = dark[:, x_margin : width - x_margin].mean(axis=1)
    horizontal = _line_centers(horizontal_scores, 0.22)
    min_gap = max(7, int(height * 0.007))
    horizontal = _merge_nearby_lines(horizontal, min_gap)
    data_lines = _longest_regular_run(
        horizontal,
        min_gap=min_gap,
        max_gap=max(18, int(height * 0.032)),
    )
    if len(data_lines) < 7:
        return None

    # A bulletin often places the officials table directly below the roster.
    # Both grids can have the same row height, so a plain "longest run" joins
    # them and weakens the vertical-line signal.  A volleyball roster needs far
    # fewer than 23 cell rows (headers included); keeping the first 24 grid
    # boundaries isolates that table without assuming a federation layout.
    data_lines = data_lines[:24]

    first_data = data_lines[0]
    header_window = max(30, int(height * 0.065))
    preceding = [line for line in horizontal if 0 < first_data - line <= header_window][-3:]
    y_lines = tuple(sorted(set(preceding + data_lines)))
    if len(y_lines) < 8:
        return None

    vertical_scores = dark[first_data : data_lines[-1] + 1, :].mean(axis=0)
    vertical = _line_centers(vertical_scores, 0.55)
    vertical = _merge_nearby_lines(vertical, max(4, int(width * 0.002)))
    vertical = [line for line in vertical if width * 0.01 <= line <= width * 0.99]
    if len(vertical) < 6:
        return None
    return GridTable(tuple(vertical), y_lines)


def remove_grid_lines(image: Image.Image, grid: GridTable, margin: int = 2) -> Image.Image:
    """Whiten detected ruling lines while preserving cell content and coordinates."""
    result = np.asarray(image.convert("L")).copy()
    x_start, x_end = grid.x_lines[0], grid.x_lines[-1]
    y_start, y_end = grid.y_lines[0], grid.y_lines[-1]
    for y in grid.y_lines:
        result[max(0, y - margin) : y + margin + 1, x_start : x_end + 1] = 255
    for x in grid.x_lines:
        result[y_start : y_end + 1, max(0, x - margin) : x + margin + 1] = 255
    return Image.fromarray(result, mode="L")


def words_to_grid_rows(words: list[dict[str, Any]], grid: GridTable) -> list[list[str]]:
    """Assign OCR words to cells using their visual center points."""
    rows: list[list[list[tuple[int, str]]]] = [
        [[] for _ in range(len(grid.x_lines) - 1)]
        for _ in range(len(grid.y_lines) - 1)
    ]
    for word in words:
        center_x = word["x"] + word["width"] / 2
        center_y = word["y"] + word["height"] / 2
        column = bisect_right(grid.x_lines, center_x) - 1
        row = bisect_right(grid.y_lines, center_y) - 1
        if 0 <= row < len(rows) and 0 <= column < len(rows[row]):
            rows[row][column].append((word["x"], str(word["text"])))

    result: list[list[str]] = []
    for row in rows:
        values = [" ".join(text for _, text in sorted(cell)) for cell in row]
        if any(values):
            result.append(values)
    return result


def serialize_grid_rows(rows: list[list[str]]) -> str:
    return "\n".join("\t".join(row) for row in rows)


def _line_centers(scores: np.ndarray, threshold: float) -> list[int]:
    indexes = np.flatnonzero(scores >= threshold)
    clusters: list[list[int]] = []
    for raw_index in indexes:
        index = int(raw_index)
        if not clusters or index > clusters[-1][-1] + 1:
            clusters.append([index])
        else:
            clusters[-1].append(index)
    return [round(sum(cluster) / len(cluster)) for cluster in clusters]


def _longest_regular_run(lines: list[int], min_gap: int, max_gap: int) -> list[int]:
    best: list[int] = []
    current: list[int] = []
    for line in lines:
        if not current:
            current = [line]
        elif min_gap <= line - current[-1] <= max_gap:
            current.append(line)
        else:
            if len(current) > len(best):
                best = current
            current = [line]
    if len(current) > len(best):
        best = current
    return best


def _merge_nearby_lines(lines: list[int], min_gap: int) -> list[int]:
    merged: list[list[int]] = []
    for line in lines:
        if not merged or line - merged[-1][-1] >= min_gap:
            merged.append([line])
        else:
            merged[-1].append(line)
    return [round(sum(group) / len(group)) for group in merged]
