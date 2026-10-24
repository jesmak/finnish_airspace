"""The bulletin's NOTAMs matched with the AIP's areas: the items, their activity, heights and distance, and the news."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

import pytest

from custom_components.finnish_airspace.aip import Area, height
from custom_components.finnish_airspace.bulletin import AreaType, Bulletin, Notam, Supplement
from custom_components.finnish_airspace.coordinator import next_poll
from custom_components.finnish_airspace.feed import Item, airspace, event_data, feature, news
from custom_components.finnish_airspace.geometry import distance_km

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
HOME = (65.0, 25.5)
SUP = Supplement(77, 2026, False)


def square(lat: float, lon: float) -> list[tuple[float, float]]:
    return [(lat, lon), (lat, lon + 0.2), (lat - 0.1, lon + 0.2), (lat - 0.1, lon), (lat, lon)]


ENR = {
    "EFR901": Area("EFR901", "HONKANIEMI", square(65.5, 26.0), False, "FL 240", "SFC"),
    "EFR902": Area("EFR902", "LEHTOVAARA", square(65.3, 26.0), False, "FL 240", "SFC"),
    "EFR903": Area("EFR903", "SALOKANGAS", square(65.1, 26.5), False, "FL 95", "SFC"),
    "EFD905A": Area("EFD905A", "ÄIJÄNSALO", square(64.0, 25.0), False, "3000 FT MSL", "SFC"),
    "EFR100": Area("EFR100", "", square(66.0, 29.0), True, "FL 280", "SFC"),
}
SUPPLEMENTS = {
    SUP: {
        "EFD905A": Area("EFD905A", "KORPIVAARA", square(63.0, 27.0), False, "FL 70", "1600 FT MSL"),
        "EFD905B": Area("EFD905B", "KORPIVAARA", square(63.2, 27.0), False, "FL 70", "1600 FT MSL"),
    },
    Supplement(79, 2026, False): {"EFD907A": Area("EFD907A", "PITKÄSALO", square(62.5, 28.0), False, "FL 50", "SFC")},
}


def notam(
    text: str,
    id: str = "A9001/26",
    start: datetime = NOW - timedelta(hours=1),
    end: datetime | None = NOW + timedelta(hours=5),
    lower: str | None = "SFC",
    upper: str | None = "FL095",
    schedule: str | None = None,
) -> Notam:
    return Notam(id=id, text=text, lower=lower, upper=upper, start=start, end=end, estimated=False, schedule=schedule)


def items(*notams: Notam, now: datetime = NOW) -> list[Item]:
    return airspace(Bulletin(time(10, 30), list(notams), [], []), ENR, SUPPLEMENTS, HOME, now).items


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("FL070", "FL 70"),
        ("FL 70", "FL 70"),
        ("FL 095", "FL 95"),
        ("1600FT AMSL", "1600 ft MSL"),
        ("1600 FT MSL", "1600 ft MSL"),
        ("500FT AGL", "500 ft AGL"),
        ("150M AGL", "150 m AGL"),
        ("150 M AMSL", "150 m MSL"),
        ("SFC", "SFC"),
        ("GND", "GND"),
        ("UNL", "UNL"),
        # A form not known stays as given, its spaces evened out.
        ("2000FT  BELOW CLOUD", "2000FT BELOW CLOUD"),
    ],
)
def test_heights_in_one_form(given: str, expected: str) -> None:
    assert height(given) == expected


def test_distance_inside_and_outside() -> None:
    ring = square(65.0, 25.0)
    assert distance_km((64.95, 25.1), [ring]) == 0
    # 0.1° of latitude south of the southern edge.
    assert distance_km((64.8, 25.1), [ring]) == pytest.approx(11.13, abs=0.01)
    # The nearest of two.
    assert distance_km((64.8, 25.1), [square(66.0, 25.0), ring]) == pytest.approx(11.13, abs=0.01)


def test_an_area_from_the_supplement_the_notam_names_before_enr_5_1() -> None:
    (item,) = items(notam("TEMPO DANGER AREA EFD905A EFD905B KORPIVAARA ACT. REF AIP SUP 077/2026"))

    assert item.key == "area:EFD905A,EFD905B"
    assert item.rings == [SUPPLEMENTS[SUP]["EFD905A"].ring, SUPPLEMENTS[SUP]["EFD905B"].ring]
    assert item.names == ["KORPIVAARA"]
    assert (item.area_type, item.new_area, item.missing) == (AreaType.DANGER, False, [])


def test_an_area_not_in_the_supplement_comes_from_enr_5_1() -> None:
    (item,) = items(notam("EFR901 HONKANIEMI ACT. REF AIP SUP 077/2026"))

    assert item.rings == [ENR["EFR901"].ring]


@pytest.mark.parametrize(
    ("text", "missing"),
    [
        ("EFR999 ACT", ["EFR999"]),
        # Its corner points alone would make a wedge over much of the east.
        ("EFR100 ACT", ["EFR100"]),
        ("EFR901 EFR999 ACT", ["EFR999"]),
        # In neither the supplement nor ENR 5.1.
        ("EFD905C ACT. REF AIP SUP 077/2026", ["EFD905C"]),
        # A supplement not read.
        ("EFD906A ACT. REF AIP SUP 078/2026", ["EFD906A"]),
    ],
)
def test_an_area_found_nowhere_is_listed(text: str, missing: list[str]) -> None:
    activation = notam(text)
    result = airspace(Bulletin(None, [activation], [], []), ENR, SUPPLEMENTS, HOME, NOW)

    (item,) = result.items
    assert item.missing == missing
    assert result.not_found == [(activation, missing)]
    # Drawn only with a shape.
    assert item.in_feed == (len(item.rings) > 0)


def test_notams_naming_the_same_areas_are_one_item() -> None:
    first = notam("EFR901 EFR902 ACT", id="A9001/26", end=NOW + timedelta(days=1))
    second = notam("EFR902 EFR901 ACT. FLARES IN USE", id="A9002/26", start=NOW + timedelta(days=1), end=NOW + timedelta(days=2))
    other = notam("EFR902 ACT", id="A9003/26", upper="FL050")

    merged, alone = items(first, second, other)

    assert merged.key == "area:EFR901,EFR902"
    assert [a.notam for a in merged.activations] == [first, second]
    assert merged.rings == [ENR["EFR901"].ring, ENR["EFR902"].ring]
    # The two periods touch, so it is in force until the second ends.
    assert merged.active_until == NOW + timedelta(days=2)
    assert alone.key == "area:EFR902"
    assert alone.activations[0].upper == "FL 50"


def test_a_code_with_its_own_circle_is_a_new_area() -> None:
    (item,) = items(notam("TEMPO RESTRICTED AREA EFR901 ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 2KM"))

    assert item.new_area
    assert item.key == "area:EFR901"
    assert len(item.rings) == 1
    assert item.rings[0] != ENR["EFR901"].ring
    assert item.distance_km == 0


def test_an_activation_of_an_area_a_notam_sets_up_is_not_listed() -> None:
    established = notam("TEMPO RESTRICTED AREA EFR1880 ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 2KM", id="A9001/26")
    activated = notam("TEMPO RESTRICTED AREA EFR1880 ACT", id="A9002/26")

    result = airspace(Bulletin(None, [established, activated], [], []), ENR, SUPPLEMENTS, HOME, NOW)

    (item,) = result.items
    assert (item.missing, result.not_found, len(item.rings)) == ([], [], 1)


def test_a_new_area_without_a_code_is_keyed_on_its_notam() -> None:
    (item,) = items(notam("TEMPO RESTRICTED AREA ESTABLISHED AND ACT. PSN 650000N 0253000E, RADIUS 1NM", id="A9005/26"))

    assert item.key == "notam:A9005/26"
    assert item.codes == []
    assert feature(item)["properties"]["name"] == "A9005/26"


@pytest.mark.parametrize(
    ("text", "lower", "upper", "expected"),
    [
        # The NOTAM's own, in one form.
        ("EFR901 ACT", "GND", "FL070", ("GND", "FL 70")),
        # Left out: from the AIP.
        ("EFR901 ACT", None, None, ("SFC", "FL 240")),
        ("EFR901 EFR902 ACT", None, None, ("SFC", "FL 240")),
        # The areas don't agree on the upper limit.
        ("EFR901 EFR903 ACT", None, None, ("SFC", None)),
        # A supplement's area.
        ("EFD905A ACT. REF AIP SUP 077/2026", None, None, ("1600 ft MSL", "FL 70")),
        # One code found nowhere: the AIP doesn't say for it.
        ("EFR901 EFR999 ACT", None, None, ("SFC", "FL 240")),
    ],
)
def test_heights(text: str, lower: str | None, upper: str | None, expected: tuple[str | None, str | None]) -> None:
    (item,) = items(notam(text, lower=lower, upper=upper))

    activation = item.activations[0]
    assert (activation.lower, activation.upper) == expected


@pytest.mark.parametrize(
    ("start", "end", "schedule", "active", "active_until", "next_start", "in_feed"),
    [
        (NOW - timedelta(hours=1), NOW + timedelta(hours=5), None, True, NOW + timedelta(hours=5), None, True),
        # Permanent.
        (NOW - timedelta(days=30), None, None, True, None, None, True),
        (NOW + timedelta(hours=23), NOW + timedelta(hours=30), None, False, None, NOW + timedelta(hours=23), True),
        (NOW + timedelta(hours=25), NOW + timedelta(hours=30), None, False, None, NOW + timedelta(hours=25), False),
        # Between two windows of its schedule.
        (
            datetime(2026, 11, 2, 6, tzinfo=UTC),
            datetime(2026, 11, 2, 15, tzinfo=UTC),
            "0600-0900 1200-1500",
            False,
            None,
            datetime(2026, 11, 2, 12, tzinfo=UTC),
            True,
        ),
        # In a window.
        (
            datetime(2026, 11, 2, 6, tzinfo=UTC),
            datetime(2026, 11, 3, 15, tzinfo=UTC),
            "0600-1500",
            True,
            datetime(2026, 11, 2, 15, tzinfo=UTC),
            None,
            True,
        ),
        # A schedule not read: the whole period.
        (
            datetime(2026, 11, 2, 6, tzinfo=UTC),
            datetime(2026, 11, 2, 15, tzinfo=UTC),
            "SR-SS",
            True,
            datetime(2026, 11, 2, 15, tzinfo=UTC),
            None,
            True,
        ),
    ],
)
def test_activity(
    start: datetime,
    end: datetime | None,
    schedule: str | None,
    active: bool,
    active_until: datetime | None,
    next_start: datetime | None,
    in_feed: bool,
) -> None:
    (item,) = items(notam("EFR901 ACT", start=start, end=end, schedule=schedule))

    assert (item.active, item.active_until, item.next_start, item.in_feed) == (active, active_until, next_start, in_feed)


def nov(day: int, hhmm: str, second: int = 0, microsecond: int = 0) -> datetime:
    return datetime(2026, 11, day, int(hhmm[:2]), int(hhmm[2:]), second, microsecond, tzinfo=UTC)


@pytest.mark.parametrize(
    ("periods", "now", "active", "active_until", "next_start"),
    [
        # Two NOTAMs without a schedule, the first ending at 23:59 and the next starting at 00:00.
        ([(nov(2, "0600"), nov(2, "2359"), None), (nov(3, "0000"), nov(3, "1500"), None)], nov(2, "1200"), True, nov(3, "1500"), None),
        # In the minute from 23:59.
        ([(nov(2, "0600"), nov(2, "2359"), None), (nov(3, "0000"), nov(3, "1500"), None)], nov(2, "2359", 30), True, nov(3, "1500"), None),
        # The first scheduled, its last window cut at TO 23:59.
        (
            [(nov(2, "0600"), nov(2, "2359"), "0600-1200 1800-2359"), (nov(3, "0000"), nov(3, "1500"), None)],
            nov(2, "1900"),
            True,
            nov(3, "1500"),
            None,
        ),
        # Alone: in force until midnight, the minute from 23:59 included.
        ([(nov(2, "0600"), nov(2, "2359"), None)], nov(2, "2359", 30), True, nov(3, "0000"), None),
        # A minute earlier is a minute earlier.
        (
            [(nov(2, "0600"), nov(2, "2358"), None), (nov(3, "0000"), nov(3, "1500"), None)],
            nov(2, "1200"),
            True,
            nov(2, "2358"),
            None,
        ),
        ([(nov(2, "0600"), nov(2, "2358"), None), (nov(3, "0000"), nov(3, "1500"), None)], nov(2, "2358", 30), False, None, nov(3, "0000")),
        # A schedule not read: the whole period, until midnight.
        ([(nov(2, "0600"), nov(2, "2359"), "SR-SS")], nov(2, "2359", 30), True, nov(3, "0000"), None),
        # Without an end, in the second from 23:59 too: the rule is for ends that are published.
        ([(nov(2, "0600"), None, None)], nov(2, "2359", 0, 400000), True, None, None),
        ([(nov(2, "0600"), None, "0600-2359")], nov(2, "2359", 0, 400000), True, None, None),
    ],
)
def test_a_period_ending_at_2359_ends_at_midnight(
    periods: list[tuple[datetime, datetime | None, str | None]],
    now: datetime,
    active: bool,
    active_until: datetime | None,
    next_start: datetime | None,
) -> None:
    notams = [
        notam("EFR901 ACT", id=f"A900{i}/26", start=start, end=end, schedule=schedule) for i, (start, end, schedule) in enumerate(periods)
    ]
    (item,) = items(*notams, now=now)

    assert (item.active, item.active_until, item.next_start) == (active, active_until, next_start)
    listed = feature(item)["properties"]["notams"]
    # The NOTAMs' own times stay as published, for those not yet ended.
    assert {notam.get("end") for notam in listed} <= {end.isoformat() if end else None for _, end, _ in periods}
    # The windows in one form, whether a span or TO closes at 23:59.
    assert not [closes for notam in listed for _, closes in notam.get("windows", []) if "T23:59" in closes]


def test_a_notam_until_2359_has_ended_at_midnight() -> None:
    assert items(notam("EFR901 ACT", start=nov(2, "0600"), end=nov(2, "2359")), now=nov(3, "0000")) == []


@pytest.mark.parametrize(
    ("texts", "not_found", "missing", "rings"),
    [
        # Found in the supplement one names, not in ENR 5.1 for the other.
        (["EFD905B ACT. REF AIP SUP 077/2026", "EFD905B ACT"], [("A9001/26", ["EFD905B"])], ["EFD905B"], 1),
        (["EFD905B ACT", "EFD905B ACT. REF AIP SUP 077/2026"], [("A9000/26", ["EFD905B"])], ["EFD905B"], 1),
        # Found for both.
        (["EFD905B ACT. REF AIP SUP 077/2026", "EFD905B ACT. FLARES. REF AIP SUP 077/2026"], [], [], 1),
        # Found for neither.
        (["EFD905B ACT", "EFD905B ACT. FLARES"], [("A9000/26", ["EFD905B"]), ("A9001/26", ["EFD905B"])], ["EFD905B"], 0),
        # Each misses a different code, in the order the NOTAMs come.
        (
            # The first NOTAM lists the codes in the other order, so the item's codes are in the other order too.
            ["EFD905B EFD907A ACT. REF AIP SUP 077/2026", "EFD907A EFD905B ACT. REF AIP SUP 079/2026"],
            [("A9000/26", ["EFD907A"]), ("A9001/26", ["EFD905B"])],
            ["EFD907A", "EFD905B"],
            2,
        ),
    ],
)
def test_not_found_is_each_notams_own(texts: list[str], not_found: list[tuple[str, list[str]]], missing: list[str], rings: int) -> None:
    notams = [notam(text, id=f"A900{i}/26") for i, text in enumerate(texts)]
    result = airspace(Bulletin(None, notams, [], []), ENR, SUPPLEMENTS, HOME, NOW)

    (item,) = result.items
    assert [(n.id, codes) for n, codes in result.not_found] == not_found
    assert item.missing == missing
    assert len(item.rings) == rings


def test_an_ended_notam_is_no_item() -> None:
    assert items(notam("EFR901 ACT", start=NOW - timedelta(hours=5), end=NOW)) == []


def test_notams_naming_an_area_without_act() -> None:
    without = notam("AD CLSD WHEN TEMPO DANGER AREA EFD905A ÄIJÄNSALO IS ACTIVE", id="B9001/26")
    result = airspace(
        Bulletin(
            None,
            [
                without,
                notam("TRIGGER NOTAM - AIRAC AIP SUP 109/2026 EFR904 WILL BE ACT", id="A9002/26"),
                notam("CHANGE AREA EFR901 UPPER LIMIT FL250", id="A9003/26"),
                notam("RWY 12/30 CLSD", id="B9004/26"),
            ],
            ["NOT A NOTAM"],
            ["B9005/26"],
        ),
        ENR,
        SUPPLEMENTS,
        HOME,
        NOW,
    )

    assert result.items == []
    assert result.without_act == [without]
    assert (result.failed, result.missed) == (["NOT A NOTAM"], ["B9005/26"])


def test_restricted_and_prohibited_areas_are_news_once() -> None:
    seen: dict[str, str] = {}
    restricted = items(notam("EFR901 ACT", id="A9001/26"), notam("EFD905A ACT", id="A9002/26"), notam("EFP951 ACT", id="A9003/26"))

    assert [item.key for item in news(restricted, seen, NOW)] == ["area:EFR901", "area:EFP951"]
    assert news(restricted, seen, NOW) == []
    # Issued again under a new id.
    assert news(items(notam("EFR901 ACT", id="A9101/26")), seen, NOW + timedelta(hours=2)) == []


def test_an_area_is_forgotten_a_week_after_its_end() -> None:
    seen: dict[str, str] = {}
    end = NOW + timedelta(hours=5)
    news(items(notam("EFR901 ACT", end=end)), seen, NOW)
    week = end + timedelta(days=7)
    again = items(notam("EFR901 ACT", id="A9101/26", start=week, end=week + timedelta(days=1)), now=week)

    # Each poll with the area in the bulletin remembers it again, so each moment gets its own copy.
    assert news(again, dict(seen), week) == []
    assert [item.key for item in news(again, dict(seen), week + timedelta(minutes=1))] == ["area:EFR901"]


def test_an_item_is_remembered_a_week_after_its_last_notam_ends() -> None:
    seen: dict[str, str] = {}
    later = NOW + timedelta(days=3)
    # The one ending last is neither the first nor the last.
    item = items(
        notam("EFR901 ACT", id="A9001/26"),
        notam("EFR901 ACT", id="A9002/26", end=later),
        notam("EFR901 ACT", id="A9003/26", end=NOW + timedelta(days=1)),
    )

    news(item, seen, NOW)

    assert seen == {"area:EFR901": (later + timedelta(days=7)).isoformat()}


def test_a_permanent_area_is_remembered_while_it_is_in_the_bulletin() -> None:
    seen: dict[str, str] = {}
    permanent = items(notam("EFR901 ACT", end=None))
    news(permanent, seen, NOW)

    assert news(permanent, seen, NOW + timedelta(days=6)) == []
    assert news(permanent, seen, NOW + timedelta(days=12)) == []


def test_the_event_from_the_first_notam() -> None:
    later = notam("EFR901 ACT. FLARES", id="A9002/26", start=NOW + timedelta(days=1), end=NOW + timedelta(days=2), upper="FL120")
    first = notam("EFR901 ACT", id="A9001/26", upper="FL100")
    (item,) = items(later, first)

    assert event_data(item) == {
        "notam": "A9001/26",
        "codes": ["EFR901"],
        "names": ["HONKANIEMI"],
        "area_type": "restricted",
        "new_area": False,
        "text": "EFR901 ACT",
        "start": "2026-11-02T09:00:00+00:00",
        "end": "2026-11-02T15:00:00+00:00",
        "estimated": False,
        "schedule": None,
        "lower": "SFC",
        "upper": "FL 100",
        "active": True,
        "distance_km": item.distance_km,
    }


def test_a_feature() -> None:
    (item,) = items(notam("EFR901 EFR902 ACT", schedule="0900-1500", start=NOW - timedelta(hours=1)))

    result = feature(item)

    assert result["id"] == "area:EFR901,EFR902"
    assert result["geometry"]["type"] == "MultiPolygon"
    assert result["geometry"]["coordinates"][0] == [[[26.0, 65.5], [26.2, 65.5], [26.2, 65.4], [26.0, 65.4], [26.0, 65.5]]]
    properties = result["properties"]
    assert properties["name"] == "EFR901 EFR902 HONKANIEMI LEHTOVAARA"
    assert properties["kind"] == "air.area"
    assert properties["active_until"] == "2026-11-02T15:00:00+00:00"
    # No nulls: a property without a value is left out.
    assert "next_start" not in properties
    assert properties["notams"] == [
        {
            "id": "A9001/26",
            "text": "EFR901 EFR902 ACT",
            "start": "2026-11-02T09:00:00+00:00",
            "end": "2026-11-02T15:00:00+00:00",
            "schedule": "0900-1500",
            "lower": "SFC",
            "upper": "FL 95",
            "windows": [["2026-11-02T09:00:00+00:00", "2026-11-02T15:00:00+00:00"]],
        }
    ]


def at(hhmm: str, day: int = 2) -> datetime:
    return datetime(2026, 11, day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC)


@pytest.mark.parametrize(
    ("fetched", "next_update", "expected"),
    [
        (at("1105"), time(11, 30), at("1133")),
        # Across midnight.
        (at("2340"), time(0, 0), at("0003", 3)),
        # Passed: the page is late to update, or came from a node of the CDN still behind.
        (at("1140"), time(11, 30), at("1145")),
        (at("1130"), time(11, 30), at("1135")),
        (at("0005", 3), time(0, 0), at("0010", 3)),
        (at("0010", 3), time(23, 50), at("0015", 3)),
        # Passed more than half an hour ago: the page has stopped updating, so every half hour.
        (at("1200"), time(11, 30), at("1230")),
        (at("1201"), time(11, 30), at("1231")),
        # Further than half an hour.
        (at("1055"), time(11, 30), at("1125")),
        # The page doesn't say.
        (at("1105"), None, at("1135")),
    ],
)
def test_next_poll(fetched: datetime, next_update: time | None, expected: datetime) -> None:
    assert next_poll(fetched, next_update) == expected
