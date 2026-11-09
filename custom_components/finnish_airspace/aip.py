"""The shapes and heights of the areas in the AIP: ENR 5.1 for the permanent ones, the supplements for the temporary."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .border import along
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
# "… 690307N 0285545E then along Finland_Russia border up to 601201N 0271735E - …"
ALONG_BORDER = re.compile(r"then along (\w+) border up to")
# ENR 5.1's activity column, after the types of activity: "MILOPS H24", "UAV NOTAM", "AUP/UUP", or once a schedule of
# its own, "BLAST MON-FRI 1100-1300 UTC (1000-1200 UTC)". The first of these words after the heights says which.
ACTIVITY = re.compile(r"\b(?:H24|NOTAM|AUP/UUP|MON|TUE|WED|THU|FRI|SAT|SUN)\b")
ACTIVITY_END = re.compile(r"\s+AMC manageable area|\s+\d+ [A-Z][a-z]")
ALWAYS = "H24"


@dataclass(frozen=True)
class Area:
    code: str
    name: str
    ring: list[Point]
    # Part of its boundary follows the state border.
    along_border: bool
    # A stretch it follows isn't in border.json, so its ring is wrong.
    incomplete: bool
    # Heights as given ("FL 240", "SFC", "4000 FT MSL").
    upper: str | None
    lower: str | None
    # When ENR 5.1 has it in force without a NOTAM: ALWAYS, or a schedule as published. None for one a NOTAM switches
    # on, and for every area of a supplement.
    activity: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "ring": self.ring,
            "along_border": self.along_border,
            "incomplete": self.incomplete,
            "upper": self.upper,
            "lower": self.lower,
            "activity": self.activity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Area:
        return cls(
            code=data["code"],
            name=data["name"],
            ring=[(lat, lon) for lat, lon in data["ring"]],
            along_border=data["along_border"],
            incomplete=data["incomplete"],
            upper=data["upper"],
            lower=data["lower"],
            activity=data["activity"],
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
        rest = text[match.end() : following.start() if following else len(text)]
        # The upper and the lower limit, then the activity column, which is read from after them.
        heights = list(HEIGHT.finditer(rest))[:2]
        area = make_area(match[1], match[2], match[3], [h[0] for h in heights], activity(rest[heights[-1].end() if heights else 0 :]))
        if area:
            areas[area.code] = area
    if not areas:
        raise ValueError("no areas in ENR 5.1")
    return areas


def activity(column: str) -> str | None:
    """ALWAYS, a schedule as published, or None for an area a NOTAM switches on, or a column not understood."""
    m = ACTIVITY.search(column)
    if not m or m[0] in ("NOTAM", "AUP/UUP"):
        return None
    if m[0] == ALWAYS:
        return ALWAYS
    schedule = column[m.start() :]
    end = ACTIVITY_END.search(schedule)
    return " ".join((schedule[: end.start()] if end else schedule).split())


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


def make_area(code: str, name: str | None, points: str, heights: list[str], activity_: str | None = None) -> Area | None:
    """None for an area with fewer than three corner points, so a NOTAM naming it shows as unmatched. A stretch along
    the state border gets the border's own points between the AIP's.
    """
    # The corner points, then by twos the border followed and the corner points after it.
    parts = ALONG_BORDER.split(points)
    ring = coordinates(parts[0])
    incomplete = False
    for border, after in zip(parts[1::2], parts[2::2], strict=True):
        corners = coordinates(after)
        stretch = along(border, ring[-1], corners[0]) if ring and corners else None
        if stretch is None:
            incomplete = True
        else:
            ring += stretch
        ring += corners
    if len(ring) < 3:
        return None
    return Area(
        code=code,
        name=(name or "").strip(),
        ring=closed(ring),
        along_border=len(parts) > 1,
        incomplete=incomplete,
        upper=heights[0] if heights else None,
        lower=heights[1] if len(heights) > 1 else None,
        activity=activity_,
    )
