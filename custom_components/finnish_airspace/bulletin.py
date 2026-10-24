"""The NOTAM bulletin for the Helsinki FIR on ais.fi, and what each NOTAM says about airspace areas.

The page is Word's HTML. Each NOTAM is a table of its own under a heading for the aerodrome or the en-route part, and
a NOTAM about several aerodromes is repeated under each of them.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime, time
from enum import StrEnum

from .geometry import Point, circle, closed, coordinates

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# The first cell of each NOTAM's table holds a lone "+". The texts are full of "+358" phone numbers, so the cell is
# the separator, not the character.
NOTAM_START = re.compile(r"<td[^>]*>\s*<p[^>]*>\s*<span[^>]*>\+</span>\s*</p>\s*</td>")
FIELDS = re.compile(
    r"^(?P<text>.*?)\s*(?:LOWER:\s*(?P<lower>.*?)\s*UPPER:\s*(?P<upper>.*?)\s*)?"
    r"FROM:\s*(?P<start>\d{2}[A-Z]{3}\d{2} \d{4})\s*TO:\s*(?P<end>PERM|\d{2}[A-Z]{3}\d{2} \d{4})(?P<est>\s+EST)?\s*"
    r"\((?P<id>[A-Z]\d{4}/\d{2})\)(?:\s*SCHEDULE:\s*(?P<schedule>.*))?$"
)
NOTAM_ID = re.compile(r"\(([A-Z]\d{4}/\d{2})\)")
NEXT_UPDATE = re.compile(r"Next update at APRX ([01]\d|2[0-3])([0-5]\d) UTC")
# EFR118, EFD532B, and the AIP's two-letter parts such as EFR122AZ.
AREA_CODE = r"EF[PRD]\d+[A-Z]*"
CODE = re.compile(rf"\b{AREA_CODE}\b")
RADIUS = re.compile(r"RADIUS\s+(\d+(?:[.,]\d+)?)\s*(KM|NM|M)\b")
# AIRAC supplements are published apart from the others.
SUPPLEMENT = re.compile(r"\b(AIRAC )?AIP SUP (\d{3})/(\d{4})")
# An aerodrome's NOTAM may name an area only to say what happens "WHEN … IS ACTIVE", so an activation must say ACT.
ACT = re.compile(r"\bACT\b")


class Kind(StrEnum):
    # An area whose shape the NOTAM gives itself: a circle or a list of corner points.
    NEW_AREA = "new_area"
    # An area of the AIP switched on by its code: the code and the word ACT.
    ACTIVATION = "activation"
    # Announces an area that a later NOTAM activates.
    TRIGGER = "trigger"
    # Changes an area's limits for good.
    CHANGE = "change"
    OTHER = "other"


class AreaType(StrEnum):
    PROHIBITED = "prohibited"
    RESTRICTED = "restricted"
    DANGER = "danger"


AREA_TYPES = {"P": AreaType.PROHIBITED, "R": AreaType.RESTRICTED, "D": AreaType.DANGER}


@dataclass(frozen=True)
class Supplement:
    number: int
    year: int
    airac: bool


@dataclass(frozen=True)
class Notam:
    id: str
    text: str
    # Heights as given ("SFC", "FL170", "2000FT AMSL"), None when the NOTAM leaves them out.
    lower: str | None
    upper: str | None
    start: datetime
    # None for PERM.
    end: datetime | None
    estimated: bool
    schedule: str | None

    @property
    def codes(self) -> list[str]:
        return list(dict.fromkeys(CODE.findall(self.text)))

    @property
    def area_type(self) -> AreaType | None:
        for words, area_type in (
            ("PROHIBITED AREA", AreaType.PROHIBITED),
            ("RESTRICTED AREA", AreaType.RESTRICTED),
            ("DANGER AREA", AreaType.DANGER),
        ):
            if words in self.text:
                return area_type
        codes = self.codes
        return AREA_TYPES[codes[0][2]] if codes else None

    @property
    def shape(self) -> list[Point] | None:
        """The NOTAM's own shape: a circle from a centre and a radius, or three or more corner points."""
        points = coordinates(self.text)
        radius = RADIUS.search(self.text)
        if len(points) == 1 and radius:
            value = float(radius[1].replace(",", "."))
            return circle(points[0], {"KM": value, "M": value / 1000, "NM": value * 1.852}[radius[2]])
        return closed(points) if len(points) >= 3 else None

    @property
    def supplement(self) -> Supplement | None:
        match = SUPPLEMENT.search(self.text)
        return Supplement(int(match[2]), int(match[3]), bool(match[1])) if match else None

    @property
    def kind(self) -> Kind:
        if "TRIGGER NOTAM" in self.text:
            return Kind.TRIGGER
        if self.text.startswith("CHANGE AREA"):
            return Kind.CHANGE
        if self.area_type and self.shape:
            return Kind.NEW_AREA
        if self.codes and ACT.search(self.text):
            return Kind.ACTIVATION
        return Kind.OTHER


@dataclass(frozen=True)
class Bulletin:
    # A time of day in UTC: the page gives no date.
    next_update: time | None
    notams: list[Notam]
    # The texts of NOTAMs that didn't parse.
    failed: list[str]
    # Ids in the page that are in no NOTAM's table, which means NOTAM_START missed them.
    missed: list[str]


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def notam_time(value: str) -> datetime:
    day, month, year, hhmm = value[:2], value[2:5], value[5:7], value[8:]
    return datetime(2000 + int(year), MONTHS.index(month) + 1, int(day), int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)


def parse_bulletin(page: str) -> Bulletin:
    """Every NOTAM in the bulletin once. Raises ValueError when there are none, as the page is then not a bulletin."""
    notams: dict[str, Notam] = {}
    failed = []
    for match in NOTAM_START.finditer(page):
        body = text_of(page[match.end() : page.index("</table>", match.end())])
        fields = FIELDS.match(body)
        try:
            if not fields:
                raise ValueError
            notam = Notam(
                id=fields["id"],
                text=fields["text"],
                lower=fields["lower"] or None,
                upper=fields["upper"] or None,
                start=notam_time(fields["start"]),
                end=None if fields["end"] == "PERM" else notam_time(fields["end"]),
                estimated=bool(fields["est"]),
                schedule=fields["schedule"] or None,
            )
        except ValueError:
            failed.append(body)
            continue
        notams.setdefault(notam.id, notam)
    if not notams:
        raise ValueError("no NOTAMs in the bulletin")
    failed_ids = {i for text in failed for i in NOTAM_ID.findall(text)}
    missed = set(NOTAM_ID.findall(text_of(page))) - notams.keys() - failed_ids
    next_update = NEXT_UPDATE.search(page)
    return Bulletin(
        next_update=time(int(next_update[1]), int(next_update[2])) if next_update else None,
        notams=list(notams.values()),
        failed=list(dict.fromkeys(failed)),
        missed=sorted(missed),
    )
