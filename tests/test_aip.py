"""The areas of ENR 5.1 and of a supplement: names, shapes and heights."""

from __future__ import annotations

import pytest

from custom_components.finnish_airspace.aip import make_area, parse_enr_5_1, parse_supplement
from custom_components.finnish_airspace.border import along, lines

from .pages import pdf, row

ENR_5_1 = (
    '<html><body><div class="P2_default">2.10. For a flight within EFR100 crossing the state border that has submitted a '
    "flight plan, no permission is required.</div><table>"
    + row(
        "EFR100",
        "660000N 0291000E - 661000N 0292000E then along Finland_Russia border up to 653000N 0294500E - 653000N 0290000E",
        "FL 280",
        "SFC",
    )
    + row("EFR901 HONKANIEMI (KORPI)", "634500N 0263000E - 634500N 0264000E - 634000N 0264000E", "FL 240", "SFC")
    + row("EFD905A ÄIJÄNSALO", "625000N 0255000E - 625000N 0260000E - 624500N 0260000E - 624500N 0255000E", "3000 FT MSL", "1300 FT MSL")
    + row(
        "EFR906AZ",
        "640000N 0240000E - 641000N 0241000E - 640000N 0242000E",
        "FL 660",
        "FL 95",
        "AUP/UUP AMC manageable area Only for FPL validation",
    )
    + row("EFD908 KAKSIPISTE", "650000N 0270000E - 651000N 0271000E", "FL 95", "SFC")
    + "</table></body></html>"
)


def test_enr_areas_with_names_shapes_and_heights() -> None:
    areas = parse_enr_5_1(ENR_5_1)

    # The one with two corner points is left out, so a NOTAM naming it shows as unmatched.
    assert list(areas) == ["EFR100", "EFR901", "EFD905A", "EFR906AZ"]
    honkaniemi = areas["EFR901"]
    assert honkaniemi.name == "HONKANIEMI (KORPI)"
    assert honkaniemi.ring == [pytest.approx(point) for point in [(63.75, 26.5), (63.75, 26.666667), (63.666667, 26.666667), (63.75, 26.5)]]
    assert (honkaniemi.upper, honkaniemi.lower, honkaniemi.along_border) == ("FL 240", "SFC", False)
    assert (areas["EFD905A"].name, areas["EFD905A"].upper, areas["EFD905A"].lower) == ("ÄIJÄNSALO", "3000 FT MSL", "1300 FT MSL")
    assert (areas["EFR906AZ"].name, areas["EFR906AZ"].upper, areas["EFR906AZ"].lower) == ("", "FL 660", "FL 95")


def test_efr100_without_a_name_along_the_border() -> None:
    efr100 = parse_enr_5_1(ENR_5_1)["EFR100"]

    assert efr100.name == ""
    assert efr100.along_border
    # The made-up end points are kilometres off the real border, so the stretch is left out rather than drawn wrong.
    assert efr100.incomplete
    assert len(efr100.ring) == 5
    assert (efr100.upper, efr100.lower) == ("FL 280", "SFC")


# EFR100's and EFD400's border stretches as ENR 5.1 gives them, with corner points of their own inland.
EFD400_STRETCHES = (
    "690935N 0284905E then along Finland_Norway border up to 690307N 0285545E then along Finland_Russia border up to "
    "601201N 0271735E - 601201N 0264549E - 650000N 0270000E"
)


def test_a_stretch_along_the_border_gets_the_border_s_points() -> None:
    area = make_area("EFD400", "ITÄINEN VAARA-ALUE", EFD400_STRETCHES, ["4000 FT MSL", "SFC"])

    assert area is not None
    assert (area.along_border, area.incomplete) == (True, False)
    # The AIP's own points at the ends of each stretch, in order, with the border's between them.
    assert area.ring[0] == pytest.approx((69.159722, 28.818056))
    assert area.ring[-4:-1] == [pytest.approx(point) for point in [(60.200278, 27.293056), (60.200278, 26.763611), (65.0, 27.0)]]
    assert len(area.ring) > 400
    # From the north down the eastern border: no step goes back up, apart from the inland points closing the ring.
    border = area.ring[:-3]
    assert all(later[0] <= earlier[0] + 0.05 for earlier, later in zip(border, border[1:], strict=False))


def test_a_stretch_against_the_line_s_direction_gets_the_same_points_reversed() -> None:
    north, south = (69.051944, 28.929167), (60.200278, 27.293056)
    down = along("Finland_Russia", north, south)
    up = along("Finland_Russia", south, north)

    assert down is not None and up is not None
    assert len(down) > 400
    assert up == down[::-1]
    # The line's own points at the ends are left out either way, as the AIP's are there already.
    assert up[0] != lines()["Finland_Russia"][-1] and up[-1] != lines()["Finland_Russia"][0]


def test_a_border_or_an_end_point_the_line_doesnt_have_leaves_the_area_incomplete() -> None:
    unknown = make_area("EFR990", "", "690935N 0284905E then along Finland_Sweden border up to 690307N 0285545E - 650000N 0270000E", [])
    # 5 km west of the AIP's end point at the Gulf of Finland.
    moved = make_area("EFR991", "", "690307N 0285545E then along Finland_Russia border up to 601201N 0270800E - 650000N 0270000E", [])

    assert unknown is not None and moved is not None
    assert (unknown.incomplete, len(unknown.ring)) == (True, 4)
    assert (moved.incomplete, len(moved.ring)) == (True, 4)


def test_the_activity_column_says_when_an_area_is_in_force_without_a_notam() -> None:
    square = "{lat}0000N 0260000E - {lat}0100N 0260000E - {lat}0100N 0260100E"
    page = (
        "<html><body><table>"
        + row("EFP901 KALLIONIEMI", square.format(lat=60), "500 FT MSL", "SFC", "", types="VIP", activity="H24")
        + row(
            "EFR902 SORAKUOPPA",
            square.format(lat=61),
            "2700 FT MSL",
            "SFC",
            types="BLAST",
            activity="MON-FRI 1100-1300 UTC (1000-1200 UTC)",
        )
        + row("EFD903 HARJU", square.format(lat=62), "FL 95", "SFC", types="MILOPS, UAV")
        + row(
            "EFR904AZ",
            square.format(lat=63),
            "FL 660",
            "FL 95",
            "AMC manageable area Only for FPL validation",
            types="",
            activity="AUP/UUP",
        )
        # The last area of a section runs into the next section's heading.
        + row("EFR905 RANTA", square.format(lat=64), "2000 FT MSL", "SFC", "3 Flight plan buffer zones (FBZ)", activity="H24")
        + "</table></body></html>"
    )
    areas = parse_enr_5_1(page)

    assert {code: area.activity for code, area in areas.items()} == {
        "EFP901": "H24",
        "EFR902": "MON-FRI 1100-1300 UTC (1000-1200 UTC)",
        "EFD903": None,
        "EFR904AZ": None,
        "EFR905": "H24",
    }


def test_a_page_without_areas_is_an_error() -> None:
    with pytest.raises(ValueError):
        parse_enr_5_1("<html><body>Page not found</body></html>")


SUPPLEMENT = pdf(
    [
        "AIP SUPPLEMENT - SUOMI / FINLAND AIP SUP NR",
        "Aihe HELSINKI FIR, TILAPÄINEN VAARA-ALUE EFD910 KORPIVAARA",
        "Subject HELSINKI FIR, TEMPORARY DANGER AREA EFD910 KORPIVAARA",
        " Alueet / Areas",
        "Designation",
        " Lateral limits Vertical limits Activity type Remarks",
        "EFD910A KORPIVAARA ITÄ",
        "634500N 0263000E - 634500N 0264000E - 634000N 0264000E -",
        "634000N 0263000E - 634500N 0263000E",
        "FL 70",
        "3000 FT MSL UAV AMC manageable area",
        "EFD910B KORPIVAARA ITÄ",
        "633000N 0263000E - 633000N 0264000E - 632500N 0264000E",
        "4000 FT MSL",
        "SFC UAV AMC manageable area",
        " Aktivointi",
        " Activation",
        " WILL BE ACTIVATED BY NOTAM:",
    ],
    # The map's labels, a code on a line of its own.
    ["SFC", "4000", "EFD910B", "TEMPO", "FL 70", "EFD910A", "TEMPO"],
)


def test_supplement_areas() -> None:
    areas = parse_supplement(SUPPLEMENT)

    assert list(areas) == ["EFD910A", "EFD910B"]
    east = areas["EFD910A"]
    assert east.name == "KORPIVAARA ITÄ"
    assert len(east.ring) == 5
    assert (east.upper, east.lower, east.along_border) == ("FL 70", "3000 FT MSL", False)
    second = areas["EFD910B"]
    assert second.ring[0] == second.ring[-1]
    assert (second.upper, second.lower) == ("4000 FT MSL", "SFC")


def test_a_supplement_about_something_else() -> None:
    assert parse_supplement(pdf(["EXAMPLE AERODROME (EFXA), TEMPORARY ARRANGEMENTS IN MANOEUVRING AREA"])) == {}


def test_a_broken_supplement_is_an_error() -> None:
    with pytest.raises(ValueError):
        parse_supplement(b"<html>Not found</html>")
