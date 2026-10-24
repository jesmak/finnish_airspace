"""The bulletin's NOTAMs, and what each says about airspace areas."""

from __future__ import annotations

import math
from datetime import UTC, datetime, time

import pytest

from custom_components.finnish_airspace.bulletin import AreaType, Kind, Notam, Supplement, parse_bulletin

FONT = """style='font-size:9.0pt; font-family:"Courier New"'"""
P = '<p class="x_MsoNormal" style="margin:0cm; margin-bottom:.0001pt">'


def table(lines: list[str], id: str, start: str, end: str, lower: str | None = None, upper: str | None = None, schedule=None) -> str:
    """One NOTAM in Word's markup, as the bulletin has it."""
    *paragraphs, last = lines
    text = "".join(f"{P}{line}</p>" for line in paragraphs) + last
    heights = (
        f"<div>{P}<b><span {FONT}>LOWER: </span></b><span {FONT}>{lower}</span><b><span {FONT}> UPPER: </span></b>"
        f"<span {FONT}>{upper}</span></p></div>"
        if lower
        else ""
    )
    period = (
        f'<div>{P}<span class="x_endgap"><b><span {FONT}>FROM: </span></b></span><span class="x_endgap"><span {FONT}>{start}'
        f"</span></span><span {FONT}><b> \n      TO:\n    </b>{end}\n        ({id})\n      </span></p></div>"
    )
    scheduled = (
        f'<div>{P}<span class="x_endgap"><b><span {FONT}>SCHEDULE: </span></b></span><span class="x_endgap"><span {FONT}>'
        f"{schedule}</span></span></p></div>"
        if schedule
        else ""
    )
    return (
        '<table class="x_MsoNormalTable" border="0" cellspacing="0" cellpadding="0" width="100%"><tbody><tr>'
        f'<td width="27" valign="top" style="width:20.4pt">{P}<span {FONT}>+</span></p></td>'
        f"""<td style="padding:.75pt"><span style='font-size:9.0pt; font-family:"Monospace"'>{text}</span>"""
        f"{heights}{period}{scheduled}</td></tr></tbody></table>"
    )


def heading(level: int, name: str) -> str:
    return f"""<h{level}><span style='font-size:13.5pt; font-family:"Courier New"'>{name}</span></h{level}>"""


def page(*parts: str, next_update: str = "1130") -> str:
    return (
        '<html><head><meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"></meta>'
        '<title>HELSINKI FIR (IFR)</title></head><body><table width="100%"><tr><td width="60%"><span class="sh1">'
        'Bulletin: HELSINKI FIR (IFR)</span></td></tr><tr><td width="60%"><span class="sh2">Next update at APRX '
        f"{next_update} UTC</span></td></tr></table>{''.join(parts)}<div><p><i><span>END OF PIB</span></i></p>"
        "YOU ARE KINDLY ASKED TO INFORM NOTAM OFFICE OF POSSIBLE FAULTS. TEL +358 29 000 0000.</div></body></html>"
    )


CLOSED = table(["EXAMPLE AFIS CLSD. OPENING REQUESTS", "TEL +358 40 000 0001"], "B0001/26", "06APR26 1130", "19NOV26 2359")
DANGER = table(
    ["TEMPO DANGER AREA EFD905A EFD905B KORPIVAARA ACT.", "CTC TEL +358 44 000 0002, +358 50 000 0003.", "REF AIP SUP 077/2026"],
    "A0002/26",
    "24OCT26 0725",
    "25OCT26 1400",
    "SFC",
    "4000FT AMSL",
    "24 0600-1900, 25 0700-1400",
)
NEW = table(
    ["TEMPO RESTRICTED AREA EFR1999 ESTABLISHED AND ACT.", "PSN 634500N 0263000E, RADIUS 1KM."],
    "A0003/26",
    "24OCT26 1200",
    "24OCT26 1900 EST",
    "SFC",
    "900FT AMSL",
)
CABLE = table(["OBST CABLE ERECTED", "PSN 653000N 0251500E"], "B0004/26", "01SEP26 0600", "PERM")
BULLETIN = page(
    heading(1, "EFIN - HELSINKI FIR"),
    heading(2, "AERODROMES"),
    heading(3, "EFXA - EXAMPLE"),
    CLOSED,
    DANGER,
    heading(3, "EFXB - SAMPLE"),
    DANGER,
    CABLE,
    heading(2, "EN-ROUTE"),
    NEW,
)


def notam(text: str) -> Notam:
    return Notam("A0001/26", text, None, None, datetime(2026, 10, 24, 6, tzinfo=UTC), None, False, None)


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def test_every_notam_once_with_its_fields() -> None:
    bulletin = parse_bulletin(BULLETIN)

    # The danger area is under both aerodromes.
    assert [n.id for n in bulletin.notams] == ["B0001/26", "A0002/26", "B0004/26", "A0003/26"]
    assert bulletin.failed == []
    assert bulletin.missed == []
    assert bulletin.next_update == time(11, 30)
    danger = bulletin.notams[1]
    # The phone numbers stay in the text without splitting the NOTAM.
    assert (
        danger.text == "TEMPO DANGER AREA EFD905A EFD905B KORPIVAARA ACT. CTC TEL +358 44 000 0002, +358 50 000 0003. REF AIP SUP 077/2026"
    )
    assert (danger.lower, danger.upper) == ("SFC", "4000FT AMSL")
    assert danger.start == datetime(2026, 10, 24, 7, 25, tzinfo=UTC)
    assert danger.end == datetime(2026, 10, 25, 14, tzinfo=UTC)
    assert not danger.estimated
    assert danger.schedule == "24 0600-1900, 25 0700-1400"


def test_an_estimated_end_permanent_and_no_heights() -> None:
    closed, _, cable, new = parse_bulletin(BULLETIN).notams

    assert new.end == datetime(2026, 10, 24, 19, tzinfo=UTC)
    assert new.estimated
    assert cable.end is None
    assert (closed.lower, closed.upper, closed.schedule) == (None, None, None)
    assert closed.text == "EXAMPLE AFIS CLSD. OPENING REQUESTS TEL +358 40 000 0001"


def test_a_phone_number_starting_a_line_is_not_a_notam() -> None:
    phone = table(["UAV ACTIVITY.", "+358 40 000 0005"], "B0005/26", "24OCT26 0600", "24OCT26 1800")
    bulletin = parse_bulletin(page(phone, CLOSED))

    assert [n.id for n in bulletin.notams] == ["B0005/26", "B0001/26"]
    assert bulletin.notams[0].text == "UAV ACTIVITY. +358 40 000 0005"


def test_a_notam_that_doesnt_parse_is_listed() -> None:
    no_period = table(["SOMETHING NEW", "(B0006/26)"], "B0006/26", "", "")
    no_such_day = table(["RWY 12/30 CLSD"], "B0007/26", "31FEB26 0600", "PERM")
    bulletin = parse_bulletin(page(CLOSED, no_period, no_such_day))

    assert [n.id for n in bulletin.notams] == ["B0001/26"]
    assert len(bulletin.failed) == 2
    assert "SOMETHING NEW" in bulletin.failed[0]
    assert "RWY 12/30 CLSD" in bulletin.failed[1]
    assert bulletin.missed == []


def test_a_notam_in_markup_the_parser_doesnt_know_is_listed_as_missed() -> None:
    other_markup = table(["RWY 12/30 CLSD"], "B0008/26", "24OCT26 0600", "PERM").replace(f"{P}<span {FONT}>+</span></p>", "<b>+</b>")
    bulletin = parse_bulletin(page(CLOSED, other_markup))

    assert [n.id for n in bulletin.notams] == ["B0001/26"]
    assert bulletin.missed == ["B0008/26"]


def test_a_page_without_notams_is_an_error() -> None:
    with pytest.raises(ValueError):
        parse_bulletin("<html><body>Service unavailable</body></html>")


def test_a_page_without_the_next_update() -> None:
    assert parse_bulletin(page(CLOSED).replace("Next update at APRX 1130 UTC", "")).next_update is None


@pytest.mark.parametrize(
    ("text", "kind", "area_type", "codes"),
    [
        (
            "TEMPO RESTRICTED AREA EFR1999 ESTABLISHED AND ACT. PSN 634500N 0263000E, RADIUS 1KM.",
            Kind.NEW_AREA,
            AreaType.RESTRICTED,
            ["EFR1999"],
        ),
        (
            "TEMPO PROHIBITED AREA ESTABLISHED. LATERAL LIMITS: 634500N0263000E - 634500N0264000E - 634000N0264000E.",
            Kind.NEW_AREA,
            AreaType.PROHIBITED,
            [],
        ),
        (
            "TEMPO DANGER AREA EFD905A EFD905B KORPIVAARA ACT. CTC TEL +358 44 000 0002. REF AIP SUP 077/2026",
            Kind.ACTIVATION,
            AreaType.DANGER,
            ["EFD905A", "EFD905B"],
        ),
        # The type from the code's letter when the text doesn't name it.
        ("EFR901 HONKANIEMI ACT. FLARES IN USE.", Kind.ACTIVATION, AreaType.RESTRICTED, ["EFR901"]),
        ("EFP902 ACT, SECURITY OPS", Kind.ACTIVATION, AreaType.PROHIBITED, ["EFP902"]),
        ("EFD903 HONKALAMPI ACT", Kind.ACTIVATION, AreaType.DANGER, ["EFD903"]),
        ("EFD1999 ESTABLISHED AND ACT. PSN 634500N 0263000E, RADIUS 1KM.", Kind.NEW_AREA, AreaType.DANGER, ["EFD1999"]),
        ("EFR906AZ EFR906AZ ACT.", Kind.ACTIVATION, AreaType.RESTRICTED, ["EFR906AZ"]),
        # Naming an area is not switching it on.
        (
            "THE ACCESSIBILITY OF INSTR APCH PROC CANNOT BE GUARANTEED WHEN THE TEMPO DANGER AREA EFD905A KORPIVAARA IS ACTIVE. "
            "REF AIP SUP 077/2026",
            Kind.OTHER,
            AreaType.DANGER,
            ["EFD905A"],
        ),
        ("EFR901 HONKANIEMI ACTIVATED.", Kind.OTHER, AreaType.RESTRICTED, ["EFR901"]),
        ("EFR901 HONKANIEMI FLARES ACTIVITY.", Kind.OTHER, AreaType.RESTRICTED, ["EFR901"]),
        ("EFR901 HONKANIEMI WILL ACTIVATE FOR EXERCISE.", Kind.OTHER, AreaType.RESTRICTED, ["EFR901"]),
        ("EFR901 HONKANIEMI", Kind.OTHER, AreaType.RESTRICTED, ["EFR901"]),
        ("OCCASIONAL UAV ACT. PSN 634500N 0263000E, RADIUS 3 KM.", Kind.OTHER, None, []),
        # A shape of its own needs no ACT.
        ("EFD1999 PSN 634500N 0263000E, RADIUS 1KM.", Kind.NEW_AREA, AreaType.DANGER, ["EFD1999"]),
        # The type and ACT without a code or a shape.
        ("TEMPO DANGER AREA KORPELA ACT.", Kind.OTHER, AreaType.DANGER, []),
        # A trigger or a change stays one, shape and ACT or not.
        (
            "CHANGE AREA EFR901 HONKANIEMI LATERAL LIMITS TO READ 634500N 0263000E - 634500N 0264000E - 634000N 0264000E. ACT.",
            Kind.CHANGE,
            AreaType.RESTRICTED,
            ["EFR901"],
        ),
        (
            "TRIGGER NOTAM - TEMPO DANGER AREA EFD907 KORPELA ACT. PSN 634500N 0263000E, RADIUS 1KM.",
            Kind.TRIGGER,
            AreaType.DANGER,
            ["EFD907"],
        ),
        (
            "TRIGGER NOTAM - AIP SUP 140/2026 WEF 26 NOV 2026. TEMPO DANGER AREA EFD907 KORPELA. "
            "A SEPARATE NOTAM WILL BE ISSUED TO ACTIVATE THE AREA",
            Kind.TRIGGER,
            AreaType.DANGER,
            ["EFD907"],
        ),
        (
            "CHANGE AREA EFR901 HONKANIEMI VERTICAL LIMITS TO READ SFC-FL95. REF AIP ENR 5.1.",
            Kind.CHANGE,
            AreaType.RESTRICTED,
            ["EFR901"],
        ),
        # A drone's circle without an area type stays off the map.
        (
            "OCCASIONAL UAV ACTIVITY BEYOND VISUAL LINE OF SIGHT (BVLOS). PSN 634500N 0263000E, RADIUS 3 KM. PILOT TEL +358 40 000 0003",
            Kind.OTHER,
            None,
            [],
        ),
        ("GNSS SIGNAL INTERFERENCE CAN BE EXPECTED IN HELSINKI FIR.", Kind.OTHER, None, []),
        # An aerodrome's code is not an area's.
        ("EFXA AD CLSD. EFPO RWY 12 CLSD.", Kind.OTHER, None, []),
    ],
)
def test_kinds(text: str, kind: Kind, area_type: AreaType | None, codes: list[str]) -> None:
    parsed = notam(text)
    assert (parsed.kind, parsed.area_type, parsed.codes) == (kind, area_type, codes)


@pytest.mark.parametrize(
    ("radius", "expected_km"),
    [("RADIUS 1KM", 1), ("RADIUS 2,5 KM", 2.5), ("RADIUS 500M", 0.5), ("RADIUS 0.5NM", 0.926)],
)
def test_a_circle(radius: str, expected_km: float) -> None:
    shape = notam(f"TEMPO DANGER AREA EFD1999 ESTABLISHED. PSN 634500N 0263000E, {radius}.").shape

    assert len(shape) == 65
    assert shape[0] == shape[-1]
    for point in shape:
        assert km((63.75, 26.5), point) == pytest.approx(expected_km, rel=0.01)


def test_corner_points() -> None:
    shape = notam("TEMPO DANGER AREA EFD1999 ESTABLISHED. 634500N 0263000E - 634500.5N 0264000E - 634000N 0264000E.").shape

    assert shape == [pytest.approx(point) for point in [(63.75, 26.5), (63.750139, 26.666667), (63.666667, 26.666667), (63.75, 26.5)]]


@pytest.mark.parametrize(
    "text",
    ["DANGER AREA EFD1999 ACT. PSN 634500N 0263000E.", "DANGER AREA EFD1999 ACT. BTN 634500N 0263000E AND 634000N 0264000E."],
)
def test_too_few_points_make_no_shape(text: str) -> None:
    parsed = notam(text)
    assert parsed.shape is None
    # So it is taken as an activation, and shows as unmatched if the AIP doesn't know the code.
    assert parsed.kind == Kind.ACTIVATION


@pytest.mark.parametrize(
    ("text", "supplement"),
    [
        ("TEMPO DANGER AREA EFD905A ACT. REF AIP SUP 077/2026", Supplement(77, 2026, False)),
        ("TRIGGER NOTAM - AIRAC AIP SUP 109/2026 WEF 02 AUG 2026.", Supplement(109, 2026, True)),
        ("EFR901 HONKANIEMI ACT.", None),
    ],
)
def test_the_supplement_referred_to(text: str, supplement: Supplement | None) -> None:
    assert notam(text).supplement == supplement
