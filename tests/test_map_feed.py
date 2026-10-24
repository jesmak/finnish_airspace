"""The items as map-feed-card shows them: names, list rows, details, colours and the legend, in English and Finnish."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.finnish_airspace.map_feed import (
    LATER_OPACITY,
    feature,
    feed_attributes,
    language_of,
    short_codes,
    title_case,
    when,
    with_metres,
)

from .test_feed import NOW, items, notam

# NOW is Monday 2 November, 10:00 UTC, which is 12:00 in Helsinki.
HELSINKI = ZoneInfo("Europe/Helsinki")


def utc(day: int, hhmm: str) -> datetime:
    return datetime(2026, 11, day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("KYYVESI", "Kyyvesi"),
        ("HIIENVAARA (KOITERE)", "Hiienvaara (Koitere)"),
        ("KELLUU ITÄ-SUOMI", "Kelluu Itä-Suomi"),
        ("ÄIJÄNSALO", "Äijänsalo"),
    ],
)
def test_names_in_title_case(name: str, expected: str) -> None:
    assert title_case(name) == expected


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        (["EFR901"], "EFR901"),
        (["EFD532B", "EFD532C"], "EFD532B, EFD532C"),
        (["EFD190A", "EFD190B", "EFD190C", "EFD190D"], "EFD190A–D"),
        ([f"EFD517{part}" for part in "BCDEFGHJKLMNOPQRST"], "EFD517B–T"),
        # Different areas, not parts of one.
        (["EFR56", "EFR57", "EFR58"], "EFR56, EFR57, EFR58"),
        (["EFD117A", "EFD117C", "EFR901"], "EFD117A, EFD117C, EFR901"),
        ([], ""),
        # In whatever order the NOTAM lists them.
        (["EFD190C", "EFD190A", "EFD190B"], "EFD190A–C"),
        # The area itself beside its parts is no part of the range.
        (["EFD190", "EFD190A", "EFD190B"], "EFD190, EFD190A, EFD190B"),
        (["EFD190", "EFD190A", "EFD190B", "EFD190C"], "EFD190, EFD190A–C"),
    ],
)
def test_codes_shortened(codes: list[str], expected: str) -> None:
    assert short_codes(codes) == expected


@pytest.mark.parametrize(
    ("moment", "closing", "fi", "en"),
    [
        (utc(2, "2000"), False, "klo 22.00", "22:00"),
        # Midnight closing a day is 24.00 of that day, and opening one 0.00 of the next.
        (utc(2, "2200"), True, "klo 24.00", "24:00"),
        (utc(2, "2200"), False, "ti 0.00", "Tue 00:00"),
        (utc(3, "0700"), False, "ti 9.00", "Tue 09:00"),
        (utc(3, "2200"), True, "ti 24.00", "Tue 24:00"),
        # Within the week by weekday, further by date.
        (utc(7, "1000"), False, "la 12.00", "Sat 12:00"),
        (utc(8, "1000"), False, "8.11. 12.00", "8 Nov 12:00"),
        (utc(8, "2200"), True, "8.11. 24.00", "8 Nov 24:00"),
    ],
)
def test_when(moment: datetime, closing: bool, fi: str, en: str) -> None:
    assert when(moment, "fi", NOW, HELSINKI, closing=closing) == fi
    assert when(moment, "en", NOW, HELSINKI, closing=closing) == en


@pytest.mark.parametrize(
    ("height", "fi", "en"),
    [
        ("FL 80", "FL 80 (n. 2 400 m)", "FL 80 (approx. 2,400 m)"),
        ("FL 95", "FL 95 (n. 2 900 m)", "FL 95 (approx. 2,900 m)"),
        ("4000 ft MSL", "4000 ft MSL (1 220 m)", "4000 ft MSL (1,220 m)"),
        ("500 ft AGL", "500 ft AGL (150 m)", "500 ft AGL (150 m)"),
        ("150 m AGL", "150 m AGL", "150 m AGL"),
        ("SFC", "SFC", "SFC"),
        ("UNL", "UNL", "UNL"),
        (None, "?", "?"),
    ],
)
def test_heights_with_metres(height: str | None, fi: str, en: str) -> None:
    assert with_metres(height, "fi") == fi
    assert with_metres(height, "en") == en


@pytest.mark.parametrize(
    ("start", "end", "fi", "en"),
    [
        (NOW - timedelta(hours=1), NOW + timedelta(hours=5), "EFR901 · voimassa klo 17.00 asti", "EFR901 · in force until 17:00"),
        (NOW - timedelta(days=3), None, "EFR901 · voimassa toistaiseksi", "EFR901 · in force until further notice"),
        (NOW + timedelta(hours=23), NOW + timedelta(hours=30), "EFR901 · alkaa ti 11.00", "EFR901 · starts Tue 11:00"),
        # Until midnight in Helsinki, 2200 UTC in winter.
        (NOW - timedelta(hours=1), utc(2, "2200"), "EFR901 · voimassa klo 24.00 asti", "EFR901 · in force until 24:00"),
        # A TO of 2359 is UTC, and closes at 00:00 UTC, 2.00 in Helsinki.
        (NOW - timedelta(hours=1), utc(2, "2359"), "EFR901 · voimassa ti 2.00 asti", "EFR901 · in force until Tue 02:00"),
    ],
)
def test_the_state_on_the_list_row(start: datetime, end: datetime | None, fi: str, en: str) -> None:
    (item,) = items(notam("EFR901 ACT", start=start, end=end))

    assert feature(item, "fi", NOW, HELSINKI)["properties"]["list"]["text"] == fi
    assert feature(item, "en", NOW, HELSINKI)["properties"]["list"]["text"] == en


@pytest.mark.parametrize(
    ("text", "tagged"),
    [
        ("TEMPO RESTRICTED AREA EFR1880 ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 2KM", True),
        ("TEMPO PROHIBITED AREA EFP1881 ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 2KM", True),
        # The weekly drone circles.
        ("TEMPO DANGER AREA EFD1882 ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 2KM", False),
        # An area of the AIP switched on.
        ("EFR901 ACT", False),
    ],
)
def test_the_new_tag_is_for_restrictions_set_up_by_notam(text: str, tagged: bool) -> None:
    (item,) = items(notam(text))

    row = feature(item, "fi", NOW, HELSINKI)["properties"]["list"]
    assert (row.get("tag") == {"text": "UUSI", "tone": "warning"}) == tagged
    assert ("tag" in row) == tagged


def test_the_codes_are_on_the_list_row_only_beside_a_place_name() -> None:
    (named,) = items(notam("EFR901 ACT"))
    (unnamed,) = items(notam("TEMPO RESTRICTED AREA EFR1880 ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 2KM"))

    named_row = feature(named, "fi", NOW, HELSINKI)["properties"]["list"]
    unnamed_row = feature(unnamed, "fi", NOW, HELSINKI)["properties"]["list"]
    assert (named_row["title"], named_row["text"]) == ("Honkaniemi", "EFR901 · voimassa klo 17.00 asti")
    assert (unnamed_row["title"], unnamed_row["text"]) == ("Rajoitusalue EFR1880", "voimassa klo 17.00 asti")


def test_an_area_not_in_force_now_stands_back() -> None:
    (active,) = items(notam("EFR901 ACT"))
    (later,) = items(notam("EFR901 ACT", start=NOW + timedelta(hours=2)))

    assert "opacity" not in feature(active, "fi", NOW, HELSINKI)["properties"]
    assert feature(later, "fi", NOW, HELSINKI)["properties"]["opacity"] == LATER_OPACITY


@pytest.mark.parametrize(("area_type", "color"), [("EFP951", "#e03131"), ("EFR901", "#d4603f"), ("EFD905A", "#8f9aab")])
def test_colours_by_type(area_type: str, color: str) -> None:
    (item,) = items(notam(f"{area_type} ACT"))

    assert feature(item, "fi", NOW, HELSINKI)["properties"]["color"] == color


def test_a_feature_in_finnish() -> None:
    (item,) = items(
        notam(
            "TEMPO DANGER AREA EFD905A EFD905B KORPIVAARA ACT. REF AIP SUP 077/2026",
            start=utc(2, "0600"),
            end=utc(5, "1500"),
            schedule="0600-1500",
            upper="FL070",
        )
    )

    result = feature(item, "fi", NOW, HELSINKI)

    assert result["id"] == "area:EFD905A,EFD905B"
    assert result["geometry"]["type"] == "MultiPolygon"
    assert result["geometry"]["coordinates"][0] == [[[27.0, 63.0], [27.2, 63.0], [27.2, 62.9], [27.0, 62.9], [27.0, 63.0]]]
    properties = result["properties"]
    assert (properties["name"], properties["subtitle"], properties["kind"]) == ("Korpivaara", "Vaara-alue", "air.area")
    assert properties["list"] == {
        "title": "Korpivaara",
        "text": "EFD905A, EFD905B · voimassa klo 17.00 asti",
        "value": f"{item.distance_km:.0f} km",
    }
    assert properties["details"] == [
        {"label": "Korkeus", "value": "SFC – FL 70 (n. 2 100 m)"},
        {"label": "Jakso", "value": "2.11. 8.00 – 5.11. 17.00"},
        {"label": "Aikataulu", "value": "ma 8.00–17.00, ti 8.00–17.00, ke 8.00–17.00, …"},
        {"label": "Etäisyys", "value": f"{item.distance_km:.1f} km".replace(".", ",")},
    ]
    assert properties["notices"] == ["TEMPO DANGER AREA EFD905A EFD905B KORPIVAARA ACT. REF AIP SUP 077/2026"]
    assert properties["footer"] == "NOTAM A9001/26 · AIP SUP 077/2026"
    assert properties["link"] == {
        "url": "https://www.ais.fi/aipsup/Sup/S2026/EF_SUP_2026_077_en.pdf",
        "label": "AIP SUP 077/2026 ais.fi:ssä",
    }
    # The data stays beside what the card shows.
    assert (properties["area_type"], properties["active"], properties["notams"][0]["upper"]) == ("danger", True, "FL 70")


def test_a_feature_in_english_without_a_place_name() -> None:
    (item,) = items(
        notam(
            "TEMPO RESTRICTED AREA ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 1NM",
            id="A9005/26",
            end=None,
            lower=None,
            upper=None,
            schedule="SR-SS",
        )
    )

    properties = feature(item, "en", NOW, HELSINKI)["properties"]

    assert properties["name"] == "Restricted area"
    assert properties["list"]["text"] == "in force until further notice"
    assert properties["list"]["value"] == "0.0 km"
    assert properties["details"] == [
        {"label": "Period", "value": "2 Nov 11:00 – until further notice"},
        # Not read: as published.
        {"label": "Schedule", "value": "SR-SS"},
        {"label": "Distance", "value": "0.0 km"},
    ]
    assert properties["link"] == {"url": "https://www.ais.fi/en/pre-flight-information-bulletins", "label": "NOTAM bulletin on ais.fi"}


def test_an_estimated_end_and_an_airac_supplement() -> None:
    estimated = notam("EFD907A ACT. REF AIRAC AIP SUP 109/2026", start=utc(2, "0600"), end=utc(2, "1500"))
    (item,) = items(replace(estimated, estimated=True))

    properties = feature(item, "en", NOW, HELSINKI)["properties"]

    assert {"label": "Period", "value": "2 Nov 08:00 – 2 Nov 17:00 (estimated)"} in properties["details"]
    assert properties["footer"] == "NOTAM A9001/26 · AIRAC AIP SUP 109/2026"
    assert properties["link"]["url"] == "https://www.ais.fi/aipsup/Sup/S2026/EF_SUP_A_2026_109_en.pdf"


@pytest.mark.parametrize(
    ("start", "end", "schedule", "now", "fi", "en"),
    [
        # Within a day.
        (utc(2, "0600"), utc(2, "1500"), "0600-1500", NOW, "ma 8.00–17.00", "Mon 08:00–17:00"),
        # Closing at local midnight, which is 24.00 of the day it opened.
        (utc(2, "0600"), utc(2, "2200"), "0600-2200", NOW, "ma 8.00–24.00", "Mon 08:00–24:00"),
        # Across midnight.
        (utc(2, "2000"), utc(3, "0200"), "2000-0200", NOW, "ma 22.00 – ti 4.00", "Mon 22:00 – Tue 04:00"),
        # Windows that touch are one, over three days.
        (utc(2, "0600"), utc(4, "1500"), "2 0600-2359, 3 0000-2359, 4 0000-1500", NOW, "ma 8.00 – ke 17.00", "Mon 08:00 – Wed 17:00"),
        (utc(2, "0000"), utc(4, "2359"), "0000-2359", NOW, "ma 2.00 – to 2.00", "Mon 02:00 – Thu 02:00"),
        # Only the windows not yet ended: Monday's closed at 09:00 UTC.
        (utc(2, "0600"), utc(4, "0900"), "0600-0900", NOW, "ti 8.00–11.00, ke 8.00–11.00", "Tue 08:00–11:00, Wed 08:00–11:00"),
    ],
)
def test_schedule_windows(start: datetime, end: datetime, schedule: str, now: datetime, fi: str, en: str) -> None:
    (item,) = items(notam("EFR901 ACT", start=start, end=end, schedule=schedule), now=now)

    assert {"label": "Aikataulu", "value": fi} in feature(item, "fi", now, HELSINKI)["properties"]["details"]
    assert {"label": "Schedule", "value": en} in feature(item, "en", now, HELSINKI)["properties"]["details"]


@pytest.mark.parametrize(
    ("start", "end", "fi", "en"),
    [
        (utc(2, "0900"), utc(2, "1500"), "2.11. 11.00 – 2.11. 17.00", "2 Nov 11:00 – 2 Nov 17:00"),
        # Local midnight closes the day before.
        (utc(2, "0900"), utc(2, "2200"), "2.11. 11.00 – 2.11. 24.00", "2 Nov 11:00 – 2 Nov 24:00"),
        # A TO of 2359 UTC closes at UTC midnight, 2.00 in Helsinki, as the list row says.
        (utc(2, "0900"), utc(2, "2359"), "2.11. 11.00 – 3.11. 2.00", "2 Nov 11:00 – 3 Nov 02:00"),
        # Opening at local midnight opens the day.
        (utc(1, "2200"), utc(2, "1500"), "2.11. 0.00 – 2.11. 17.00", "2 Nov 00:00 – 2 Nov 17:00"),
        (utc(2, "0900"), None, "2.11. 11.00 – toistaiseksi", "2 Nov 11:00 – until further notice"),
    ],
)
def test_the_period(start: datetime, end: datetime | None, fi: str, en: str) -> None:
    (item,) = items(notam("EFR901 ACT", start=start, end=end))

    assert {"label": "Jakso", "value": fi} in feature(item, "fi", NOW, HELSINKI)["properties"]["details"]
    assert {"label": "Period", "value": en} in feature(item, "en", NOW, HELSINKI)["properties"]["details"]


def test_an_item_of_several_notams() -> None:
    first = notam("EFR901 EFR902 ACT. FLARES IN USE", id="A9001/26", start=utc(2, "0600"), end=utc(2, "1500"))
    second = notam("EFR902 EFR901 ACT. FLARES IN USE", id="A9002/26", start=utc(3, "0600"), end=utc(3, "1500"))
    third = notam("EFR901 EFR902 ACT. REF AIP SUP 077/2026", id="A9003/26", start=utc(4, "0600"), end=utc(4, "1500"))
    fourth = notam("EFR901 EFR902 ACT. REF AIP SUP 077/2026", id="A9004/26", start=utc(5, "0600"), end=utc(5, "1500"))

    (item,) = items(first, second, third, fourth)
    properties = feature(item, "fi", NOW, HELSINKI)["properties"]

    assert properties["name"] == "Honkaniemi, Lehtovaara"
    assert properties["notices"] == [
        "EFR901 EFR902 ACT. FLARES IN USE",
        "EFR902 EFR901 ACT. FLARES IN USE",
        "EFR901 EFR902 ACT. REF AIP SUP 077/2026",
    ]
    assert properties["footer"] == "NOTAM A9001/26 · NOTAM A9002/26 · NOTAM A9003/26 · NOTAM A9004/26 · AIP SUP 077/2026"
    assert [row["value"] for row in properties["details"] if row["label"] == "Jakso"] == [
        "2.11. 8.00 – 2.11. 17.00",
        "3.11. 8.00 – 3.11. 17.00",
        "4.11. 8.00 – 4.11. 17.00",
        "5.11. 8.00 – 5.11. 17.00",
    ]


def test_a_window_closing_at_midnight_in_the_schedule() -> None:
    (item,) = items(notam("EFR901 ACT", start=utc(2, "0600"), end=utc(3, "2200"), schedule="0600-2200"))

    details = feature(item, "fi", NOW, HELSINKI)["properties"]["details"]

    assert {"label": "Aikataulu", "value": "ma 8.00–24.00, ti 8.00–24.00"} in details


def test_the_legend_and_the_list() -> None:
    assert feed_attributes("fi") == {
        "legend": [
            {"color": "#e03131", "label": "Kieltoalue"},
            {"color": "#d4603f", "label": "Rajoitusalue"},
            {"color": "#8f9aab", "label": "Vaara-alue"},
        ],
        "list": {
            "sort": [{"key": "distance", "label": "Etäisyys", "property": "distance_km"}],
            "default": "distance",
            "count": "aluetta",
            "count_one": "alue",
        },
    }
    # A language without texts of its own gets English.
    assert (language_of("sv"), language_of("fi"), language_of("en-GB")) == ("en", "fi", "en")
    assert [entry["color"] for entry in feed_attributes("en")["legend"]] == [feed_attributes("fi")["legend"][i]["color"] for i in range(3)]


def test_no_property_is_null() -> None:
    (item,) = items(notam("TEMPO RESTRICTED AREA ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 1NM", end=None, lower=None, upper=None))

    def nulls(value: object) -> list[object]:
        if isinstance(value, dict):
            return [key for key, inner in value.items() if inner is None] + [n for inner in value.values() for n in nulls(inner)]
        if isinstance(value, list):
            return [n for inner in value for n in nulls(inner)]
        return []

    assert nulls(feature(item, "fi", NOW, HELSINKI)) == []
