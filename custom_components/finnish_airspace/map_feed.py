"""The items as a map feed for map-feed-card: names, list rows, details, colours and the legend, in English or Finnish."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, tzinfo
from typing import Any

from .bulletin import AreaType, Supplement
from .const import SUPPLEMENT_URL
from .feed import Activation, Item, to_midnight

# The danger areas, most of the items, a quiet grey, so they stay in the background and keep clear of the colours an
# aircraft feed gives altitudes.
COLORS = {AreaType.PROHIBITED: "#e03131", AreaType.RESTRICTED: "#d4603f", AreaType.DANGER: "#8f9aab"}
# An area not in force now stands back.
LATER_OPACITY = 0.45
BULLETIN_PAGE = "https://www.ais.fi/en/pre-flight-information-bulletins"
# The next windows of a schedule shown in the details.
WINDOWS_SHOWN = 3
FLIGHT_LEVEL = re.compile(r"FL (\d+)")
FEET = re.compile(r"(\d+) ft (MSL|AGL)")

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "prohibited": "Prohibited area",
        "restricted": "Restricted area",
        "danger": "Danger area",
        "new": "NEW",
        "until": "in force until {when}",
        "until_further_notice": "in force until further notice",
        "starts": "starts {when}",
        "today": "{clock}",
        "heights": "Heights",
        "period": "Period",
        "schedule": "Schedule",
        "distance": "Distance",
        "further_notice": "until further notice",
        "estimated": "estimated",
        "approx_metres": "approx. {m} m",
        "metres": "{m} m",
        "km": "{km} km",
        "supplement_link": "{supplement} on ais.fi",
        "bulletin_link": "NOTAM bulletin on ais.fi",
        "by_distance": "Distance",
        "areas": "areas",
        "area": "area",
    },
    "fi": {
        "prohibited": "Kieltoalue",
        "restricted": "Rajoitusalue",
        "danger": "Vaara-alue",
        "new": "UUSI",
        "until": "voimassa {when} asti",
        "until_further_notice": "voimassa toistaiseksi",
        "starts": "alkaa {when}",
        "today": "klo {clock}",
        "heights": "Korkeus",
        "period": "Jakso",
        "schedule": "Aikataulu",
        "distance": "Etäisyys",
        "further_notice": "toistaiseksi",
        "estimated": "arvio",
        "approx_metres": "n. {m} m",
        "metres": "{m} m",
        "km": "{km} km",
        "supplement_link": "{supplement} ais.fi:ssä",
        "bulletin_link": "NOTAM-tiedote ais.fi:ssä",
        "by_distance": "Etäisyys",
        "areas": "aluetta",
        "area": "alue",
    },
}
WEEKDAYS = {"en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], "fi": ["ma", "ti", "ke", "to", "pe", "la", "su"]}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def language_of(config_language: str) -> str:
    """Finnish texts for Finnish, English ones for any other language."""
    return "fi" if config_language.split("-")[0] == "fi" else "en"


def texts_for(language: str) -> dict[str, str]:
    return TEXTS[language]


def feed_attributes(language: str) -> dict[str, Any]:
    texts = texts_for(language)
    return {
        "legend": [{"color": COLORS[area_type], "label": texts[area_type.value]} for area_type in COLORS],
        "list": {
            "sort": [{"key": "distance", "label": texts["by_distance"], "property": "distance_km"}],
            "default": "distance",
            "count": texts["areas"],
            "count_one": texts["area"],
        },
    }


def feature(item: Item, language: str, now: datetime, zone: tzinfo) -> dict[str, Any]:
    """An item as a map feed's feature, with its data for templates and automations beside what the card shows."""
    texts = texts_for(language)
    kind = texts[item.area_type.value]
    name = ", ".join(title_case(name) for name in item.names) or " ".join(filter(None, [kind, short_codes(item.codes)]))
    status = state_text(item, language, now, zone)
    properties = {
        "name": name,
        "kind": "air.area",
        "subtitle": kind,
        "color": COLORS[item.area_type],
        "opacity": None if item.active else LATER_OPACITY,
        "list": without_none(
            {
                "title": name,
                # The codes tell two items of one place apart. Without a place, the name has them already.
                "text": f"{short_codes(item.codes)} · {status}" if item.names else status,
                "value": texts["km"].format(km=number(item.distance_km, language, decimals=0 if item.distance_km >= 10 else 1))
                if item.distance_km is not None
                else None,
                # A restriction set up at short notice is what this is for. New danger areas, such as the weekly drone
                # circles, would teach the tag to be ignored.
                "tag": {"text": texts["new"], "tone": "warning"} if item.new_area and item.area_type != AreaType.DANGER else None,
            }
        ),
        "details": detail_rows(item, language, now, zone),
        "notices": list(dict.fromkeys(a.notam.text for a in item.activations)),
        "footer": " · ".join([*(f"NOTAM {a.notam.id}" for a in item.activations), *map(supplement_name, supplements(item))]),
        "link": link(item, language),
        "area_type": item.area_type.value,
        "codes": item.codes,
        "new_area": item.new_area,
        "active": item.active,
        "active_until": iso(item.active_until),
        "next_start": iso(item.next_start),
        "distance_km": item.distance_km,
        "notams": [notam_data(a) for a in item.activations],
    }
    return {
        "type": "Feature",
        "id": item.key,
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[round(lon, 5), round(lat, 5)] for lat, lon in ring]] for ring in item.rings],
        },
        "properties": without_none(properties),
    }


def notam_data(activation: Activation) -> dict[str, Any]:
    notam = activation.notam
    return without_none(
        {
            "id": notam.id,
            "text": notam.text,
            "start": iso(notam.start),
            "end": iso(notam.end),
            "estimated": notam.estimated or None,
            "schedule": notam.schedule,
            "lower": activation.lower,
            "upper": activation.upper,
            "windows": [[iso(opens), iso(closes)] for opens, closes in activation.windows] if activation.windows else None,
        }
    )


def detail_rows(item: Item, language: str, now: datetime, zone: tzinfo) -> list[dict[str, str]]:
    texts = texts_for(language)
    rows = []
    first = item.activations[0]
    if first.lower or first.upper:
        heights = f"{with_metres(first.lower, language)} – {with_metres(first.upper, language)}"
        rows.append({"label": texts["heights"], "value": heights})
    for activation in item.activations:
        notam = activation.notam
        # Closing as the windows do: a TO of 2359 at UTC midnight, local midnight as 24.00 of the day before.
        end = moment(to_midnight((notam.start, notam.end))[1], language, zone, closing=True) if notam.end else texts["further_notice"]
        estimated = f" ({texts['estimated']})" if notam.estimated else ""
        rows.append({"label": texts["period"], "value": f"{moment(notam.start, language, zone)} – {end}{estimated}"})
        schedule = schedule_text(activation, language, now, zone)
        if schedule:
            rows.append({"label": texts["schedule"], "value": schedule})
    if item.distance_km is not None:
        rows.append({"label": texts["distance"], "value": texts["km"].format(km=number(item.distance_km, language, decimals=1))})
    return rows


def state_text(item: Item, language: str, now: datetime, zone: tzinfo) -> str:
    texts = texts_for(language)
    if item.active:
        if item.active_until is None:
            return texts["until_further_notice"]
        return texts["until"].format(when=when(item.active_until, language, now, zone, closing=True))
    # An item in the feed is in force or starts within a day.
    return texts["starts"].format(when=when(item.next_start, language, now, zone)) if item.next_start else ""


def when(moment_: datetime, language: str, now: datetime, zone: tzinfo, closing: bool = False) -> str:
    """ "klo 22.00" today, "su 9.00" within the week, "30.10. 22.00" further. A closing midnight is 24.00 of the day before."""
    local, today = moment_.astimezone(zone), now.astimezone(zone).date()
    day, midnight = day_of(local, closing)
    clock = clock_text(local, language, midnight)
    if day == today:
        return texts_for(language)["today"].format(clock=clock)
    if day - today < timedelta(days=6):
        return f"{WEEKDAYS[language][day.weekday()]} {clock}"
    return f"{date_text(day, language)} {clock}"


def moment(value: datetime, language: str, zone: tzinfo, closing: bool = False) -> str:
    local = value.astimezone(zone)
    day, midnight = day_of(local, closing)
    return f"{date_text(day, language)} {clock_text(local, language, midnight)}"


def day_of(local: datetime, closing: bool) -> tuple[date, bool]:
    """The day a time belongs to, and whether it is written as 24.00: a closing midnight ends the day before."""
    if closing and (local.hour, local.minute) == (0, 0):
        return (local - timedelta(minutes=1)).date(), True
    return local.date(), False


def schedule_text(activation: Activation, language: str, now: datetime, zone: tzinfo) -> str | None:
    """The next windows of a schedule read, or the schedule as published when it wasn't. A window closing on a later
    day than it opens gets that day too: "ma 22.00 – ti 4.00".
    """
    if activation.windows is None:
        return activation.notam.schedule
    weekdays = WEEKDAYS[language]
    coming = [window for window in activation.windows if window[1] > now]
    shown = []
    for opens, closes in coming[:WINDOWS_SHOWN]:
        start, end = opens.astimezone(zone), closes.astimezone(zone)
        day, midnight = day_of(end, closing=True)
        opening = f"{weekdays[start.weekday()]} {clock_text(start, language)}"
        if day == start.date():
            shown.append(f"{opening}–{clock_text(end, language, midnight)}")
        else:
            shown.append(f"{opening} – {weekdays[day.weekday()]} {clock_text(end, language, midnight)}")
    return ", ".join(shown) + (", …" if len(coming) > WINDOWS_SHOWN else "") if shown else None


def clock_text(local: datetime, language: str, midnight: bool = False) -> str:
    """ "9.00" in Finnish, "09:00" in English. With `midnight`, 00:00 is written as the end of the day before."""
    hour = 24 if midnight and (local.hour, local.minute) == (0, 0) else local.hour
    return f"{hour}.{local.minute:02d}" if language == "fi" else f"{hour:02d}:{local.minute:02d}"


def date_text(day: date, language: str) -> str:
    return f"{day.day}.{day.month}." if language == "fi" else f"{day.day} {MONTHS[day.month - 1]}"


def with_metres(height: str | None, language: str) -> str:
    """Metres beside a flight level, approximate as it is a pressure altitude, and beside feet."""
    if height is None:
        return "?"
    texts = texts_for(language)
    if m := FLIGHT_LEVEL.fullmatch(height):
        return f"{height} ({texts['approx_metres'].format(m=number(round(int(m[1]) * 30.48, -2), language))})"
    if m := FEET.fullmatch(height):
        return f"{height} ({texts['metres'].format(m=number(round(int(m[1]) * 0.3048, -1), language))})"
    return height


def number(value: float, language: str, decimals: int = 0) -> str:
    """ "2 400" and "99,7" in Finnish, "2,400" and "99.7" otherwise."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", " ").replace(".", ",") if language == "fi" else text


def title_case(name: str) -> str:
    """The AIP's names are in capitals: "HIIENVAARA (KOITERE)" is "Hiienvaara (Koitere)"."""
    return re.sub(r"(^|[\s(/-])(\w)", lambda m: m[1] + m[2].upper(), name.lower())


def short_codes(codes: list[str]) -> str:
    """Three or more parts of one area as a range, in order: "EFD517B–T". Two are written out, and so is the area
    itself beside its parts.
    """
    groups: dict[str, list[str]] = {}
    for code in codes:
        m = re.fullmatch(r"(EF[PRD]\d+)([A-Z]*)", code)
        groups.setdefault(m[1] if m else code, []).append(m[2] if m else "")
    written = []
    for base, parts in groups.items():
        lettered = sorted(part for part in parts if part)
        if "" in parts:
            written.append(base)
        written.append(f"{base}{lettered[0]}–{lettered[-1]}" if len(lettered) > 2 else ", ".join(base + part for part in lettered))
    return ", ".join(text for text in written if text)


def supplements(item: Item) -> list[Supplement]:
    return list(dict.fromkeys(a.notam.supplement for a in item.activations if a.notam.supplement))


def supplement_name(supplement: Supplement) -> str:
    return f"{'AIRAC ' if supplement.airac else ''}AIP SUP {supplement.number:03d}/{supplement.year}"


def link(item: Item, language: str) -> dict[str, str]:
    texts = texts_for(language)
    named = supplements(item)
    if named:
        supplement = named[0]
        url = SUPPLEMENT_URL.format(year=supplement.year, airac="A_" if supplement.airac else "", number=supplement.number)
        return {"url": url, "label": texts["supplement_link"].format(supplement=supplement_name(supplement))}
    return {"url": BULLETIN_PAGE, "label": texts["bulletin_link"]}


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def without_none(values: dict[str, Any]) -> dict[str, Any]:
    """The feed format asks for a property without a value to be left out rather than null."""
    return {key: value for key, value in values.items() if value is not None}
