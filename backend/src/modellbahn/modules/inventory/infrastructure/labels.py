"""Labels as PDF with reportlab: barcodes as vector graphics, text set in Geist like the shop.

Johann's till (SumUp) reads barcodes, not QR codes:

* **Unit:** the variant's EAN-13 at the top left (the till rings up the article by
  it), product and article number beside it, and across the bottom a Code 128 with the
  unit's own code for the workshop's scanner.
* **Location:** the code in large type and a wide Code 128 with it.

Two stocks:

* **A4 sheet, 3 x 8 labels of 70 x 37 mm** (e.g. Avery Zweckform 3474). The labels touch
  each other and the sheet's sides; a started sheet can be used up by skipping labels.
* **Brother QL, 62 mm endless roll** (DK-22205): one page of 62 x 29 mm per label, which
  the printer driver cuts after each page.

Bars are drawn as vector shapes, so they stay sharp at any printer resolution; the
bar widths stay at or above 0.25 mm, which 300 dpi printers render cleanly. Geist (SIL
Open Font License, see ``fonts/OFL.txt``) is embedded.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import files
from io import BytesIO
from typing import Final

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.code128 import Code128
from reportlab.graphics.barcode.eanbc import Ean13BarcodeWidget
from reportlab.graphics.shapes import Drawing
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
_ELLIPSIS: Final = "…"
# EAN-13 is 95 modules wide, plus 11 and 7 modules of quiet zone.
_EAN_MODULES: Final = 113


@dataclass(frozen=True, slots=True)
class _Layout:
    width: float
    height: float
    padding: float
    ean_module: float
    """Width of one EAN-13 bar module (0.33 mm is 100 %)."""
    ean_height: float
    code128_module: float
    code128_height: float
    location_code128_height: float
    gap: float
    caption_size: float
    title_size: float
    detail_size: float
    code_size: float
    location_code_size: float


_A4_LAYOUT: Final = _Layout(
    width=70 * mm,
    height=37 * mm,
    padding=3 * mm,
    ean_module=0.29 * mm,
    ean_height=16 * mm,
    code128_module=0.3 * mm,
    code128_height=6 * mm,
    location_code128_height=11 * mm,
    gap=2 * mm,
    caption_size=5.5,
    title_size=7.5,
    detail_size=6,
    code_size=7,
    location_code_size=17,
)
_QL_LAYOUT: Final = _Layout(
    width=62 * mm,
    height=29 * mm,
    padding=2.2 * mm,
    ean_module=0.25 * mm,
    ean_height=12 * mm,
    code128_module=0.26 * mm,
    code128_height=5 * mm,
    location_code128_height=9 * mm,
    gap=1.6 * mm,
    caption_size=5,
    title_size=6.8,
    detail_size=5.5,
    code_size=6.5,
    location_code_size=15,
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
                row, column = divmod(index % per_sheet, _A4_COLUMNS)
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
    if label.ean13 is not None:
        _draw_unit(canvas, label, label.ean13, (x, y), layout)
    else:
        _draw_location(canvas, label, x, y, layout)


def _draw_unit(
    canvas: Canvas, label: Label, ean13: str, origin: tuple[float, float], layout: _Layout
) -> None:
    x, y = origin
    left = x + layout.padding
    right = x + layout.width - layout.padding
    top = y + layout.height - layout.padding
    bottom = y + layout.padding

    # EAN-13 at the top left; its quiet zone, where the first digit stands, reaches a
    # little into the padding.
    ean_width = _EAN_MODULES * layout.ean_module
    ean_left = left - 11 * layout.ean_module * 0.25
    _draw_ean13(canvas, ean13, ean_left, top - layout.ean_height, layout)

    # Beside it: what the unit is.
    text_left = ean_left + ean_width + layout.gap * 0.5
    width = right - text_left
    cursor = top - layout.caption_size
    _caption(canvas, label.caption, text_left, cursor, layout.caption_size)
    longest = max(label.title.split(), key=len, default="")
    title_size = _fitting_size(longest, _SANS_MEDIUM, layout.title_size, width, floor=0.8)
    cursor -= title_size * 1.55
    canvas.setFillColor(black)
    canvas.setFont(_SANS_MEDIUM, title_size)
    for line in _lines(label.title, _SANS_MEDIUM, title_size, width, 2):
        canvas.drawString(text_left, cursor, line)
        cursor -= title_size * 1.2
    canvas.setFillColor(_GREY)
    canvas.setFont(_SANS, layout.detail_size)
    canvas.drawString(
        text_left, cursor - 0.2 * mm, _truncated(label.detail, _SANS, layout.detail_size, width)
    )
    reference_size = _fitting_size(label.reference, _MONO, layout.detail_size, width)
    canvas.setFont(_MONO, reference_size)
    canvas.drawString(
        text_left,
        top - layout.ean_height + 0.4 * mm,
        _truncated(label.reference, _MONO, reference_size, width),
    )

    # Across the bottom: the unit's own code for the workshop's scanner.
    canvas.setFillColor(black)
    canvas.setFont(_MONO, layout.code_size)
    canvas.drawString(left, bottom, label.code_text)
    code128_y = bottom + layout.code_size + 0.6 * mm
    _draw_code128(
        canvas, label.code128, (left, code128_y), layout.code128_module, layout.code128_height
    )


def _draw_location(canvas: Canvas, label: Label, x: float, y: float, layout: _Layout) -> None:
    left = x + layout.padding
    right = x + layout.width - layout.padding
    top = y + layout.height - layout.padding
    bottom = y + layout.padding
    width = right - left

    cursor = top - layout.caption_size
    _caption(canvas, label.caption, left, cursor, layout.caption_size)
    canvas.setFillColor(_GREY)
    canvas.setFont(_MONO, layout.detail_size)
    reference = _truncated(label.reference, _MONO, layout.detail_size, width * 0.55)
    canvas.drawRightString(right, cursor, reference)

    code_size = _fitting_size(label.code_text, _MONO, layout.location_code_size, width * 0.62)
    cursor -= code_size * 1.05
    canvas.setFillColor(black)
    canvas.setFont(_MONO, code_size)
    canvas.drawString(left, cursor, label.code_text)
    name_left = left + pdfmetrics.stringWidth(label.code_text, _MONO, code_size) + layout.gap
    name_width = right - name_left
    canvas.setFont(_SANS_MEDIUM, layout.title_size)
    names = _lines(label.title, _SANS_MEDIUM, layout.title_size, name_width, 2)
    name_y = cursor + code_size * 0.55 - layout.title_size * 0.2
    for line in names:
        canvas.drawRightString(right, name_y, line)
        name_y -= layout.title_size * 1.2

    # The module grows with the space: short codes get bold bars.
    module = min(
        layout.code128_module * 1.4,
        width / _code128_modules(label.code128, quiet=True),
    )
    _draw_code128(canvas, label.code128, (left, bottom), module, layout.location_code128_height)


def _caption(canvas: Canvas, text: str, x: float, y: float, size: float) -> None:
    # Character spacing belongs to the PDF's text state and would outlive the text
    # object, so the state is saved around it.
    canvas.saveState()
    canvas.setFillColor(_GREY)
    caption = canvas.beginText(x, y)
    caption.setFont(_SANS_MEDIUM, size)
    caption.setCharSpace(0.08 * size)
    caption.textOut(text.upper())
    canvas.drawText(caption)
    canvas.restoreState()


def _draw_ean13(canvas: Canvas, digits: str, x: float, y: float, layout: _Layout) -> None:
    widget = Ean13BarcodeWidget(digits[:12])
    widget.barWidth = layout.ean_module
    widget.barHeight = layout.ean_height
    widget.fontName = _MONO
    widget.fontSize = round(layout.ean_height * 0.17)
    widget.barFillColor = black
    widget.textColor = black
    width = _EAN_MODULES * layout.ean_module
    drawing = Drawing(width, layout.ean_height)
    drawing.add(widget)
    renderPDF.draw(drawing, canvas, x, y)


def _code128_modules(data: str, *, quiet: bool) -> float:
    """Width of ``data`` as Code 128 in modules (with a quiet zone of 10 on each side)."""
    width = Code128(data, barWidth=1, quiet=quiet).width
    return float(width)


def _draw_code128(
    canvas: Canvas, data: str, origin: tuple[float, float], module: float, height: float
) -> None:
    # The quiet zone lies to the right; the label's padding is the one on the left.
    barcode = Code128(data, barWidth=module, barHeight=height, lquiet=0, rquiet=10 * module)
    canvas.setFillColor(black)
    barcode.drawOn(canvas, *origin)


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
