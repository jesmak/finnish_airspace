"""Pages as ais.fi serves them, made up: the bulletin's Word markup, ENR 5.1's rows and a supplement's PDF."""

from __future__ import annotations

import io

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

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
