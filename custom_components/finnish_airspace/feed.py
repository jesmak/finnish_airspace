"""The areas in force: the bulletin's NOTAMs matched with the AIP's shapes, as the feed's items and the event's news."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .aip import Area, height
from .bulletin import AreaType, Bulletin, Kind, Notam, Supplement
from .geometry import Point, distance_km
from .schedule import Window, merged, schedule_windows

# The feed shows the areas in force, and those starting within this.
AHEAD = timedelta(hours=24)
# An area is remembered this long after its last NOTAM ends, so one issued again under a new id is not news. An area
# without a code is known by its NOTAM's id, so one replacing it is.
REMEMBER = timedelta(days=7)
# The areas whose appearance is news. Danger areas are most of the NOTAMs (shooting, flares, drones), every week.
NEWS = (AreaType.RESTRICTED, AreaType.PROHIBITED)

# Each supplement's areas by code.
type Supplements = dict[Supplement, dict[str, Area]]


@dataclass(frozen=True)
class Activation:
    """One NOTAM of an item, with its heights and windows."""

    notam: Notam
    # In one form ("FL 70", "1600 ft MSL"). From the NOTAM, or from the AIP when the NOTAM leaves them out and the
    # areas it names agree.
    lower: str | None
    upper: str | None
    # None when the whole period stands, for a NOTAM without a schedule or with one not read.
    windows: list[Window] | None
    # Codes found neither in the supplement it names nor in ENR 5.1.
    missing: list[str]


@dataclass(frozen=True)
class Item:
    """The areas a NOTAM names, with every NOTAM naming the same ones."""

    # "area:EFD190A,EFD190B" by the codes, or "notam:A6090/26" for a new area without one.
    key: str
    codes: list[str]
    # The AIP's names of the areas found, once each.
    names: list[str]
    area_type: AreaType
    # Its shape is a NOTAM's own rather than the AIP's.
    new_area: bool
    rings: list[list[Point]]
    # Codes some NOTAM of the item found nowhere.
    missing: list[str]
    activations: list[Activation]
    active: bool
    # When the window in force closes, None when it doesn't or none is.
    active_until: datetime | None
    # When the next window opens, None while one is in force.
    next_start: datetime | None
    distance_km: float | None
    # In force, or starting within AHEAD, with a shape to draw.
    in_feed: bool


@dataclass(frozen=True)
class Airspace:
    """Everything the bulletin says about areas, at one moment."""

    # Every item with a NOTAM not yet ended, in the bulletin's order.
    items: list[Item]
    # NOTAMs naming an area without saying ACT, which the parser can't tell from an activation worded some other way.
    without_act: list[Notam]
    # The texts of the NOTAMs that didn't parse, and the ids of those the parser missed.
    failed: list[str]
    missed: list[str]
    updated: datetime

    @property
    def not_found(self) -> list[tuple[Notam, list[str]]]:
        """NOTAMs naming an area found nowhere, with those codes."""
        return [(a.notam, a.missing) for item in self.items for a in item.activations if a.missing]


def airspace(
    bulletin: Bulletin,
    enr: dict[str, Area],
    supplements: Supplements,
    home: Point,
    now: datetime,
) -> Airspace:
    groups: dict[str, list[Notam]] = {}
    without_act = []
    for notam in bulletin.notams:
        if notam.kind in (Kind.NEW_AREA, Kind.ACTIVATION):
            if notam.end is None or to_midnight((notam.start, notam.end))[1] > now:
                groups.setdefault(item_key(notam), []).append(notam)
        elif notam.kind == Kind.OTHER and notam.codes:
            without_act.append(notam)
    return Airspace(
        items=[make_item(key, notams, enr, supplements, home, now) for key, notams in groups.items()],
        without_act=without_act,
        failed=bulletin.failed,
        missed=bulletin.missed,
        updated=now,
    )


def item_key(notam: Notam) -> str:
    return f"area:{','.join(sorted(notam.codes))}" if notam.codes else f"notam:{notam.id}"


def find_area(code: str, supplement: Supplement | None, enr: dict[str, Area], supplements: Supplements) -> Area | None:
    """From the supplement the NOTAM names, otherwise from ENR 5.1.

    None for an area following the state border, whose corner points alone make a wedge over much of the east.
    """
    area = (supplements.get(supplement, {}).get(code) if supplement else None) or enr.get(code)
    return None if area is None or area.along_border else area


def make_item(
    key: str,
    notams: list[Notam],
    enr: dict[str, Area],
    supplements: Supplements,
    home: Point,
    now: datetime,
) -> Item:
    rings: list[list[Point]] = []
    names: list[str] = []
    activations = []
    # A code whose area a NOTAM of the item sets up itself is not looked up in the AIP.
    shaped = {code for notam in notams if notam.kind == Kind.NEW_AREA for code in notam.codes}
    # The NOTAMs' shapes are pooled, as a code's area is taken to be in one place. On 2026-10-24 no code was both in
    # ENR 5.1 and in a supplement, and none was named with two supplements.
    for notam in notams:
        areas: list[Area] = []
        missing: list[str] = []
        if notam.kind == Kind.NEW_AREA:
            shape = notam.shape
            if shape and shape not in rings:
                rings.append(shape)
        else:
            for code in notam.codes:
                if code in shaped:
                    continue
                area = find_area(code, notam.supplement, enr, supplements)
                if area is None:
                    missing.append(code)
                    continue
                areas.append(area)
                if area.ring not in rings:
                    rings.append(area.ring)
                if area.name and area.name not in names:
                    names.append(area.name)
        activations.append(
            Activation(
                notam=notam,
                lower=notam_height(notam.lower, [area.lower for area in areas]),
                upper=notam_height(notam.upper, [area.upper for area in areas]),
                windows=scheduled(notam),
                missing=missing,
            )
        )

    # An open end is far enough in the future for the comparisons below.
    never = now + timedelta(days=36500)
    windows = merged([window for a in activations for window in a.windows or [period(a.notam, never)] if window[1] > now])
    current = next((window for window in windows if window[0] <= now), None)
    next_start = None if current else min((opens for opens, _ in windows), default=None)
    first = notams[0]
    return Item(
        key=key,
        codes=list(dict.fromkeys(code for notam in notams for code in notam.codes)),
        names=names,
        # Never None for these kinds: a new area has a type, an activation a code.
        area_type=first.area_type or AreaType.DANGER,
        new_area=any(notam.kind == Kind.NEW_AREA for notam in notams),
        rings=rings,
        missing=list(dict.fromkeys(code for a in activations for code in a.missing)),
        activations=activations,
        active=current is not None,
        active_until=current[1] if current and current[1] != never else None,
        next_start=next_start,
        distance_km=round(distance_km(home, rings), 1) if rings else None,
        in_feed=bool(rings) and (current is not None or (next_start is not None and next_start <= now + AHEAD)),
    )


def period(notam: Notam, never: datetime) -> Window:
    """The whole period, closing at midnight where TO is 23:59, and at `never` without an end."""
    return to_midnight((notam.start, notam.end)) if notam.end else (notam.start, never)


def scheduled(notam: Notam) -> list[Window] | None:
    """The schedule's windows, closing at midnight where TO is 23:59. The schedule is read with TO as published, since
    its last window must end at TO.
    """
    windows = schedule_windows(notam.start, notam.end, notam.schedule) if notam.schedule else None
    return [to_midnight(window) for window in windows] if windows else None


def to_midnight(window: Window) -> Window:
    """A window closing at 23:59 closes at midnight, so a NOTAM until 23:59 and the next from 00:00 leave no gap."""
    opens, closes = window
    return (opens, closes + timedelta(minutes=1)) if (closes.hour, closes.minute, closes.second) == (23, 59, 0) else window


def notam_height(given: str | None, from_areas: list[str | None]) -> str | None:
    if given:
        return height(given)
    known = set(from_areas)
    return height(known.pop()) if len(known) == 1 and None not in known else None


def news(items: list[Item], seen: dict[str, str], now: datetime) -> list[Item]:
    """The restricted and prohibited areas not seen before, remembering them in `seen` (key: when to forget it)."""
    for key, forget in list(seen.items()):
        if datetime.fromisoformat(forget) < now:
            del seen[key]
    result = []
    for item in items:
        if item.area_type not in NEWS:
            continue
        if item.key not in seen:
            result.append(item)
        last_end = max((activation.notam.end or now for activation in item.activations), default=now)
        seen[item.key] = (max(last_end, now) + REMEMBER).isoformat()
    return result


def event_data(item: Item) -> dict[str, Any]:
    """The event of a new area, from its first NOTAM."""
    first = min(item.activations, key=lambda activation: activation.notam.start)
    notam = first.notam
    return {
        "notam": notam.id,
        "codes": item.codes,
        "names": item.names,
        "area_type": item.area_type.value,
        "new_area": item.new_area,
        "text": notam.text,
        "start": notam.start.isoformat(),
        "end": notam.end.isoformat() if notam.end else None,
        "estimated": notam.estimated,
        "schedule": notam.schedule,
        "lower": first.lower,
        "upper": first.upper,
        "active": item.active,
        "distance_km": item.distance_km,
    }
