"""The areas of ENR 5.1 and of a supplement: names, shapes and heights."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from custom_components.finnish_airspace.aip import parse_enr_5_1, parse_supplement


def row(title: str, points: str, upper: str, lower: str, remarks: str = "AMC manageable area") -> str:
    """An area's row in ENR 5.1, its heights in a table of their own inside the row."""
    span = '<span space="preserve" style="font-family: Arial ,PMingLiU;"><span space="preserve" style="font-size:12px;">'
    return (
        f'<tr><td style="text-align: left" valign="top"><a id="1tab2"></a>{span}<span class="bold"><strong>{title}</strong></span>'
        f"</span></span><br>{span}Area bounded by lines joining points <br> {points} to point of origin.</span></span><br></td>"
        '<td style="text-align: center"><div class="dynamic"><table class="IndSubTable" border="0" width="100%"><tbody>'
        "<tr><td></td><td></td><td></td></tr>"
        f"<tr><td></td><td>{span}{upper}</span></span><br>{span}<hr></hr></span></span><br></td><td></td></tr>"
        f"<tr><td></td><td>{span}{lower}</span></span><br></td><td></td></tr>"
        "<tr><td></td><td></td><td></td></tr></tbody></table></div></td>"
        f"<td>{span}MILOPS</span></span></td><td>{span}NOTAM</span></span></td><td>{span}{remarks}</span></span></td></tr>"
    )


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
    assert len(efr100.ring) == 5
    assert (efr100.upper, efr100.lower) == ("FL 280", "SFC")


def test_a_page_without_areas_is_an_error() -> None:
    with pytest.raises(ValueError):
        parse_enr_5_1("<html><body>Page not found</body></html>")


def pdf(*pages: list[str]) -> bytes:
    """A PDF of lines of text, a page for each list."""
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    for lines in pages:
        page = writer.add_blank_page(595, 842)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        escaped = (line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines)
        content = DecodedStreamObject()
        content.set_data(("BT /F1 10 Tf 12 TL 50 800 Td " + " ".join(f"({line}) Tj T*" for line in escaped) + " ET").encode("cp1252"))
        page.replace_contents(content)
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


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
