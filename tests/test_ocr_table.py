import numpy as np
from PIL import Image, ImageDraw

from src.parser.ocr_table import (
    GridTable,
    detect_grid_table,
    remove_grid_lines,
    words_to_grid_rows,
)


def test_grid_detection_and_cell_assignment_are_layout_driven():
    image = Image.new("L", (900, 1200), 255)
    draw = ImageDraw.Draw(image)
    x_lines = [40, 110, 190, 310, 470, 580, 690, 790, 860]
    y_lines = [80 + row * 34 for row in range(14)]
    for x in x_lines:
        draw.line((x, y_lines[0], x, y_lines[-1]), fill=0, width=3)
    for y in y_lines:
        draw.line((x_lines[0], y, x_lines[-1], y), fill=0, width=3)

    grid = detect_grid_table(image)

    assert grid is not None
    assert len(grid.x_lines) == len(x_lines)
    assert len(grid.y_lines) == len(y_lines)

    words = [
        {"text": "12", "x": 125, "y": 125, "width": 20, "height": 12},
        {"text": "ALPHA", "x": 330, "y": 125, "width": 60, "height": 12},
        {"text": "Anna", "x": 490, "y": 125, "width": 45, "height": 12},
    ]
    rows = words_to_grid_rows(words, grid)
    populated = next(row for row in rows if "ALPHA" in row)
    assert populated[1] == "12"
    assert populated[3] == "ALPHA"
    assert populated[4] == "Anna"

    cleaned = np.asarray(remove_grid_lines(image, grid, margin=2))
    assert cleaned[y_lines[5], x_lines[0] + 20] == 255
    assert cleaned[y_lines[5] + 10, x_lines[3]] == 255


def test_word_assignment_ignores_text_outside_detected_table():
    grid = GridTable((10, 100, 200), (20, 60, 100))
    rows = words_to_grid_rows(
        [
            {"text": "inside", "x": 20, "y": 30, "width": 30, "height": 10},
            {"text": "outside", "x": 210, "y": 30, "width": 30, "height": 10},
        ],
        grid,
    )

    assert rows == [["inside", ""]]
