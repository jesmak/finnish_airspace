"""Writes custom_components/finnish_airspace/border.json: the stretches of the state border that ENR 5.1's areas follow.

The line is the National Land Survey of Finland's realm outline, SuomenValtakunta_2025_100k (CC BY 4.0), cut between
the AIP's end points and simplified to 100 m. Run again only when the survey publishes a new edition, or ENR 5.1 names
another stretch of the border:

    pip install pyshp pyproj
    python scripts/border.py
"""

from __future__ import annotations

import json
import math
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path

import shapefile
from pyproj import Transformer

EDITION = 2025
DATASET = f"SuomenValtakunta_{EDITION}_100k"
SOURCE = f"https://mirrors.nic.funet.fi/index/geodata/mml/hallintorajat_100k/{EDITION}/"
OUTPUT = Path(__file__).parent.parent / "custom_components" / "finnish_airspace" / "border.json"
TOLERANCE_M = 100
# The stretches ENR 5.1 follows, by the name it gives them, between the end points it gives (EFR100 and EFD400).
STRETCHES = {
    "Finland_Norway": ("690935N 0284905E", "690307N 0285545E"),
    "Finland_Russia": ("690307N 0285545E", "601201N 0271735E"),
}

to_wgs84 = Transformer.from_crs(3067, 4326, always_xy=True)
to_tm35 = Transformer.from_crs(4326, 3067, always_xy=True)


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        for extension in ("shp", "shx", "dbf", "prj"):
            urllib.request.urlretrieve(f"{SOURCE}{DATASET}.{extension}", f"{folder}/{DATASET}.{extension}")
        shapes = shapefile.Reader(f"{folder}/{DATASET}.shp").shapes()
    if len(shapes) != 1 or len(shapes[0].parts) != 1:
        raise SystemExit(f"Expected the realm as one ring, got {len(shapes)} shapes")
    ring = shapes[0].points
    borders = {}
    for name, (start, end) in STRETCHES.items():
        stretch = simplified(cut(ring, tm35(start), tm35(end)), TOLERANCE_M)
        borders[name] = [[round(lat, 5), round(lon, 5)] for lon, lat in (to_wgs84.transform(x, y) for x, y in stretch)]
        print(f"{name}: {len(stretch)} points")
    # The survey's licence asks the credit to name the dataset and when it was delivered, as "06/2014".
    data = {"dataset": f"{DATASET} {datetime.now():%m/%Y}", "borders": borders}
    OUTPUT.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    print(f"Wrote {OUTPUT}, {OUTPUT.stat().st_size} bytes")


def tm35(text: str) -> tuple[float, float]:
    """An AIP coordinate, 690935N 0284905E, in metres on ETRS-TM35FIN."""
    lat, lon = text.split()
    longitude = int(lon[:3]) + int(lon[3:5]) / 60 + int(lon[5:7]) / 3600
    latitude = int(lat[:2]) + int(lat[2:4]) / 60 + int(lat[4:6]) / 3600
    return to_tm35.transform(longitude, latitude)


def cut(ring: list[tuple[float, float]], start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    """The ring's points from the one nearest to start to the one nearest to end, the shorter way round by the number of
    points, which for a stretch of the border is also the shorter by length, as the rest is the whole of Finland.
    """
    size = len(ring) - 1 if ring[0] == ring[-1] else len(ring)
    i, j = nearest(ring[:size], start), nearest(ring[:size], end)
    forward = [ring[(i + k) % size] for k in range((j - i) % size + 1)]
    backward = [ring[(i - k) % size] for k in range((i - j) % size + 1)]
    return forward if len(forward) <= len(backward) else backward


def nearest(points: list[tuple[float, float]], to: tuple[float, float]) -> int:
    return min(range(len(points)), key=lambda k: math.dist(points[k], to))


def simplified(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas–Peucker, iteratively, as the stretch has thousands of points."""
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        far, index = 0.0, 0
        for k in range(first + 1, last):
            distance = to_line(points[k], points[first], points[last])
            if distance > far:
                far, index = distance, k
        if far > tolerance:
            keep[index] = True
            stack += [(first, index), (index, last)]
    return [point for point, kept in zip(points, keep, strict=True) if kept]


def to_line(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    (x, y), (x1, y1), (x2, y2) = point, a, b
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / length))
    return math.hypot(x - x1 - t * dx, y - y1 - t * dy)


if __name__ == "__main__":
    main()
