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
