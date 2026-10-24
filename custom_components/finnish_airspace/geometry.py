"""Coordinates as the AIP and the NOTAMs write them, and the shapes made of them."""

from __future__ import annotations

import math
import re

# Latitude and longitude, in degrees.
Point = tuple[float, float]

# 634500N 0263000E, also without the space and with decimal seconds.
COORDINATE = re.compile(r"(\d{2})(\d{2})(\d{2}(?:\.\d+)?)([NS])\s*(\d{3})(\d{2})(\d{2}(?:\.\d+)?)([EW])")


def coordinates(text: str) -> list[Point]:
    result = []
    for m in COORDINATE.finditer(text):
        lat = int(m[1]) + int(m[2]) / 60 + float(m[3]) / 3600
        lon = int(m[5]) + int(m[6]) / 60 + float(m[7]) / 3600
        result.append((-lat if m[4] == "S" else lat, -lon if m[8] == "W" else lon))
    return result


def closed(ring: list[Point]) -> list[Point]:
    return ring if ring[0] == ring[-1] else [*ring, ring[0]]


def circle(center: Point, radius_km: float, points: int = 64) -> list[Point]:
    lat, lon = center
    ring = [
        (
            lat + radius_km / 111.32 * math.cos(2 * math.pi * i / points),
            lon + radius_km / (111.32 * math.cos(math.radians(lat))) * math.sin(2 * math.pi * i / points),
        )
        for i in range(points)
    ]
    return closed(ring)


def distance_km(point: Point, rings: list[list[Point]]) -> float:
    """From a point to the nearest of the rings, 0 inside one.

    On a plane laid at the point, which is off by a few per cent for an area at the other end of Finland.
    """
    lat0, lon0 = point
    scale = math.cos(math.radians(lat0))
    nearest = math.inf
    for ring in rings:
        flat = [((lon - lon0) * 111.32 * scale, (lat - lat0) * 111.32) for lat, lon in ring]
        inside = False
        for (x1, y1), (x2, y2) in zip(flat, flat[1:], strict=False):
            # A ray from the point to the east crosses the edge.
            if (y1 > 0) != (y2 > 0) and x1 + (x2 - x1) * -y1 / (y2 - y1) > 0:
                inside = not inside
            nearest = min(nearest, to_segment(x1, y1, x2, y2))
        if inside:
            return 0.0
    return nearest


def to_segment(x1: float, y1: float, x2: float, y2: float) -> float:
    """From the origin to the segment between two points."""
    dx, dy = x2 - x1, y2 - y1
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, -(x1 * dx + y1 * dy) / length))
    return math.hypot(x1 + t * dx, y1 + t * dy)
