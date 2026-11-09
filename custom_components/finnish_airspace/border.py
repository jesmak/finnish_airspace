"""The stretches of the state border ENR 5.1's areas follow, from border.json (scripts/border.py writes it)."""

from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path
from typing import Any

from .geometry import Point

# An end point further than this from the line means the AIP no longer matches it, and the area isn't drawn.
MATCH_KM = 1.0


@cache
def data() -> dict[str, Any]:
    """Read once, in the executor, as parsing ENR 5.1 is."""
    return json.loads((Path(__file__).parent / "border.json").read_text())


@cache
def lines() -> dict[str, list[Point]]:
    return {name: [(lat, lon) for lat, lon in points] for name, points in data()["borders"].items()}


def border_dataset() -> str:
    """The dataset the line was cut from and when it was delivered, for the credit the survey's licence asks for."""
    return data()["dataset"]


def along(name: str, start: Point, end: Point) -> list[Point] | None:
    """The border's points between two of the AIP's, in that direction, or None when the AIP names a border the file
    doesn't have, or an end point too far from it.
    """
    line = lines().get(name)
    if not line:
        return None
    i, j = nearest(line, start), nearest(line, end)
    if km(line[i], start) > MATCH_KM or km(line[j], end) > MATCH_KM:
        return None
    # The line's own points at the ends are left out, as the AIP's are there already.
    return line[i + 1 : j] if i <= j else line[j + 1 : i][::-1]


def nearest(line: list[Point], to: Point) -> int:
    return min(range(len(line)), key=lambda k: km(line[k], to))


def km(a: Point, b: Point) -> float:
    return math.hypot((a[0] - b[0]) * 111.32, (a[1] - b[1]) * 111.32 * math.cos(math.radians((a[0] + b[0]) / 2)))
