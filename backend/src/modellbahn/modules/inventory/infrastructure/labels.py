"""Labels as PDF with reportlab: QR code as vector graphic, text set in Geist like the shop.

Two stocks:

* **A4 sheet, 3 x 8 labels of 70 x 37 mm** (e.g. Avery Zweckform 3474). The labels touch
  each other and the sheet's sides; a started sheet can be used up by skipping labels.
* **Brother QL, 62 mm endless roll** (DK-22205): one page of 62 x 29 mm per label, which
  the printer driver cuts after each page.

The QR code is drawn module by module as one path, so it stays sharp at any printer
resolution. Geist (SIL Open Font License, see ``fonts/OFL.txt``) is embedded.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import files
from io import BytesIO
from typing import Final

import segno
from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from modellbahn.modules.inventory.application.ports import Label, LabelSheet

_SANS: Final = "Geist"
_SANS_MEDIUM: Final = "Geist-Medium"
_MONO: Final = "GeistMono-Medium"
_FONT_FILES: Final = {
    _SANS: "Geist-Regular.ttf",
    _SANS_MEDIUM: "Geist-Medium.ttf",
    _MONO: "GeistMono-Medium.ttf",
}
_GREY: Final = Color(0.42, 0.44, 0.47)
_RULE: Final = Color(0.78, 0.79, 0.81)
_ELLIPSIS: Final = "…"
_QR_BORDER: Final = 2
"""Quiet zone in modules; the label's white margin adds to it."""


@dataclass(frozen=True, slots=True)
class _Layout:
    width: float
    height: float
    padding: float
    qr_size: float
    gap: float
    caption_size: float
    code_size: float
    title_size: float
    detail_size: float


_A4_LAYOUT: Final = _Layout(
    width=70 * mm,
    height=37 * mm,
    padding=3.5 * mm,
    qr_size=30 * mm,
    gap=3 * mm,
    caption_size=5.5,
    code_size=10.5,
    title_size=7.5,
    detail_size=6,
)
_QL_LAYOUT: Final = _Layout(
    width=62 * mm,
    height=29 * mm,
    padding=2.5 * mm,
    qr_size=24 * mm,
    gap=2.5 * mm,
    caption_size=5,
    code_size=10,
    title_size=7,
    detail_size=5.5,
)
_A4_COLUMNS: Final = 3
_A4_ROWS: Final = 8
# 8 x 37 mm leave half a millimetre at the top and bottom of the sheet.
_A4_TOP_MARGIN: Final = (A4[1] - _A4_ROWS * _A4_LAYOUT.height) / 2

_fonts_registered = False


def _register_fonts() -> None:
    global _fonts_registered  # noqa: PLW0603 - registering with reportlab is process-wide
    if _fonts_registered:
        return
    folder = files("modellbahn.modules.inventory.infrastructure") / "fonts"
    for name, filename in _FONT_FILES.items():
        with (folder / filename).open("rb") as font_file:
            pdfmetrics.registerFont(TTFont(name, BytesIO(font_file.read())))
    _fonts_registered = True


class ReportLabLabelRenderer:
    """The :class:`~modellbahn.modules.inventory.application.ports.LabelRenderer` for PDF."""

    def render(self, labels: Sequence[Label], *, sheet: LabelSheet, skip: int) -> bytes:
        _register_fonts()
        buffer = BytesIO()
        if sheet is LabelSheet.A4_70X37:
            canvas = Canvas(buffer, pagesize=A4)
            _start(canvas, len(labels))
            per_sheet = _A4_COLUMNS * _A4_ROWS
            for index, label in enumerate(labels, start=skip):
                if index and index % per_sheet == 0:
                    canvas.showPage()
                slot = index % per_sheet
                row, column = divmod(slot, _A4_COLUMNS)
                x = column * _A4_LAYOUT.width
                y = A4[1] - _A4_TOP_MARGIN - (row + 1) * _A4_LAYOUT.height
                _draw(canvas, label, x, y, _A4_LAYOUT)
        else:
            canvas = Canvas(buffer, pagesize=(_QL_LAYOUT.width, _QL_LAYOUT.height))
            _start(canvas, len(labels))
            for index, label in enumerate(labels):
                if index:
                    canvas.showPage()
                _draw(canvas, label, 0, 0, _QL_LAYOUT)
        canvas.showPage()
        canvas.save()
        return buffer.getvalue()


def _start(canvas: Canvas, count: int) -> None:
    canvas.setTitle(f"{count} Etikett" + ("en" if count != 1 else ""))
    canvas.setCreator("Modellbahn-Shop · Stellwerk")


def _draw(canvas: Canvas, label: Label, x: float, y: float, layout: _Layout) -> None:
    qr_y = y + (layout.height - layout.qr_size) / 2
    _draw_qr(canvas, label.qr_payload, x + layout.padding, qr_y, layout.qr_size)

    left = x + layout.padding + layout.qr_size + layout.gap
    width = x + layout.width - layout.padding - left
    top = y + layout.height - layout.padding

    # Caption: small, spaced capitals. Character spacing belongs to the PDF's text
    # state and would outlive the text object, so the state is saved around it.
    cursor = top - layout.caption_size
    canvas.saveState()
    canvas.setFillColor(_GREY)
    text = canvas.beginText(left, cursor)
    text.setFont(_SANS_MEDIUM, layout.caption_size)
    text.setCharSpace(0.08 * layout.caption_size)
    text.textOut(label.caption.upper())
    canvas.drawText(text)
    canvas.restoreState()

    # The code, as large as fits.
    code_size = _fitting_size(label.code_text, _MONO, layout.code_size, width)
    cursor -= layout.code_size * 0.45 + code_size
    canvas.setFillColor(black)
    canvas.setFont(_MONO, code_size)
    canvas.drawString(left, cursor, label.code_text)

    cursor -= 1.6 * mm
    canvas.setStrokeColor(_RULE)
    canvas.setLineWidth(0.35)
    canvas.line(left, cursor, left + width, cursor)

    # Title in up to two lines, a little smaller if a single word is too long.
    longest = max(label.title.split(), key=len, default="")
    title_size = _fitting_size(longest, _SANS_MEDIUM, layout.title_size, width, floor=0.8)
    cursor -= title_size * 1.3
    canvas.setFont(_SANS_MEDIUM, title_size)
    for line in _lines(label.title, _SANS_MEDIUM, title_size, width, 2):
        canvas.drawString(left, cursor, line)
        cursor -= title_size * 1.2

    # At the bottom: the detail, and under it the reference in monospace.
    bottom = y + layout.padding
    reference_size = _fitting_size(label.reference, _MONO, layout.detail_size, width)
    canvas.setFillColor(_GREY)
    canvas.setFont(_MONO, reference_size)
    canvas.drawString(left, bottom, _truncated(label.reference, _MONO, reference_size, width))
    canvas.setFont(_SANS, layout.detail_size)
    canvas.drawString(
        left,
        bottom + layout.detail_size * 1.35,
        _truncated(label.detail, _SANS, layout.detail_size, width),
    )


def _draw_qr(canvas: Canvas, payload: str, x: float, y: float, size: float) -> None:
    matrix = segno.make(payload, error="m", micro=False).matrix
    modules = len(matrix) + 2 * _QR_BORDER
    module = size / modules
    path = canvas.beginPath()
    for row_index, row in enumerate(matrix):
        top = y + size - (_QR_BORDER + row_index + 1) * module
        column = 0
        while column < len(row):
            if not row[column]:
                column += 1
                continue
            start = column
            while column < len(row) and row[column]:
                column += 1
            # A run of dark modules as one rectangle, so no seams appear between them.
            path.rect(x + (_QR_BORDER + start) * module, top, (column - start) * module, module)
    canvas.setFillColor(black)
    canvas.drawPath(path, stroke=0, fill=1)


def _fitting_size(text: str, font: str, size: float, width: float, *, floor: float = 0.6) -> float:
    """``size``, or smaller (down to ``floor`` of it) until ``text`` fits ``width``."""
    smallest = size * floor
    while size > smallest and pdfmetrics.stringWidth(text, font, size) > width:
        size -= 0.25
    return size


def _lines(text: str, font: str, size: float, width: float, limit: int) -> list[str]:
    """``text`` wrapped to ``width``; beyond ``limit`` lines the last one ends in an ellipsis."""
    if not text:
        return []
    lines: list[str] = simpleSplit(text, font, size, width)
    if len(lines) > limit:
        lines = [*lines[: limit - 1], " ".join(lines[limit - 1 :]) + _ELLIPSIS]
    return [_truncated(line, font, size, width) for line in lines]


def _truncated(text: str, font: str, size: float, width: float) -> str:
    if pdfmetrics.stringWidth(text, font, size) <= width:
        return text
    body = text.removesuffix(_ELLIPSIS)
    while body and pdfmetrics.stringWidth(body + _ELLIPSIS, font, size) > width:
        body = body[:-1]
    return body.rstrip() + _ELLIPSIS
