"""The shapes and heights of the areas in the AIP: ENR 5.1 for the permanent ones, the supplements for the temporary."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .bulletin import AREA_CODE, text_of
from .geometry import Point, closed, coordinates

HEIGHT = re.compile(r"\b(?:UNL|SFC|GND|FL ?\d+|\d+ ?FT (?:MSL|AMSL|AGL)|\d+ ?M (?:MSL|AMSL|AGL))\b")
FLIGHT_LEVEL = re.compile(r"FL ?(\d+)")
ALTITUDE = re.compile(r"(\d+) ?(FT|M) (MSL|AMSL|AGL)")
NAME = r"[A-ZÅÄÖ][A-ZÅÄÖ0-9 ./()'-]*?"
# EFR100 has no name, nor do the parts used only for flight plan validation (EFR122AZ). The heights are in a table
# nested in the row, so the page is read as text and each area runs up to the next one.
ENR_AREA = re.compile(rf"\b({AREA_CODE}) (?:({NAME}) )?Area bounded by lines joining points ((?:(?!Area bounded).)+?) to point of origin\.")
# Each area starts with a line "EFD532A KYYVESI", its corner points on the lines after it, then the upper and the lower
# limit on a line each.
SUPPLEMENT_AREA = re.compile(rf"^({AREA_CODE}) ({NAME})\n((?:.*\d{{6}}N \d{{7}}E.*\n)+)(.*)\n(.*)", re.M)


@dataclass(frozen=True)
class Area:
    code: str
    name: str
    ring: list[Point]
    # Part of its boundary follows the state border, which its corner points alone leave out.
    along_border: bool
    # Heights as given ("FL 240", "SFC", "4000 FT MSL").
    upper: str | None
    lower: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "ring": self.ring,
            "along_border": self.along_border,
            "upper": self.upper,
            "lower": self.lower,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Area:
        return cls(
            code=data["code"],
            name=data["name"],
            ring=[(lat, lon) for lat, lon in data["ring"]],
            along_border=data["along_border"],
            upper=data["upper"],
            lower=data["lower"],
        )


def height(text: str) -> str:
    """A height in one form, as the NOTAMs and the AIP write the same one differently: "FL070" and "FL 70" are "FL 70",
    "1600FT AMSL" and "1600 FT MSL" are "1600 ft MSL". Anything else as given.
    """
    text = " ".join(text.split())
    if m := FLIGHT_LEVEL.fullmatch(text):
        return f"FL {int(m[1])}"
    if m := ALTITUDE.fullmatch(text):
        return f"{int(m[1])} {m[2].lower()} {'AGL' if m[3] == 'AGL' else 'MSL'}"
    return text


def parse_enr_5_1(page: str) -> dict[str, Area]:
    """ENR 5.1's prohibited, restricted and danger areas by code. Raises ValueError when the page has none."""
    text = text_of(page)
    matches = list(ENR_AREA.finditer(text))
    areas = {}
    for match, following in zip(matches, [*matches[1:], None], strict=True):
        heights = HEIGHT.findall(text, match.end(), following.start() if following else len(text))
        area = make_area(match[1], match[2], match[3], heights)
        if area:
            areas[area.code] = area
    if not areas:
        raise ValueError("no areas in ENR 5.1")
    return areas


def parse_supplement(pdf: bytes) -> dict[str, Area]:
    """A supplement's areas by code, none for a supplement about something else. Raises ValueError for a broken PDF."""
    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    except PyPdfError as err:
        raise ValueError(f"unreadable supplement: {err}") from err
    areas = {}
    for match in SUPPLEMENT_AREA.finditer(text):
        area = make_area(match[1], match[2], match[3], HEIGHT.findall(f"{match[4]}\n{match[5]}"))
        if area:
            areas[area.code] = area
    return areas


def make_area(code: str, name: str | None, points: str, heights: list[str]) -> Area | None:
    """None for an area with fewer than three corner points, so a NOTAM naming it shows as unmatched."""
    ring = coordinates(points)
    if len(ring) < 3:
        return None
    return Area(
        code=code,
        name=(name or "").strip(),
        ring=closed(ring),
        along_border="along" in points,
        upper=heights[0] if heights else None,
        lower=heights[1] if len(heights) > 1 else None,
    )
