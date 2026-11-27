"""Delivery notes as PDF with reportlab, in the look of the invoices (ADR 0047, ADR 0038).

A4 after DIN 5008 form B like the invoice, so it fits the same window envelope: the
wordmark, the address field, the order's facts in a sand box, then the pieces with an
empty box to tick while packing, no prices. A mandarin band at the foot thanks the
customer and says whom to write when something is missing.
"""

from io import BytesIO
from typing import Final

from reportlab.lib.colors import white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from modellbahn.modules.sales.domain.delivery_notes import DeliveryLine, DeliveryNote
from modellbahn.modules.sales.infrastructure.invoices import (
    CONTENT,
    FOOTER_TOP,
    HEIGHT,
    INK,
    INK_SECONDARY,
    INK_TERTIARY,
    LEFT,
    LOGO_RED,
    MANDARIN,
    RIGHT,
    SAND,
    SAND_LINE,
)
from modellbahn.platform.pdf_fonts import MONO, SANS, SANS_MEDIUM, register_fonts

COL_CHECK: Final = LEFT + 2 * mm
COL_POS: Final = LEFT + 11 * mm
COL_ITEM: Final = LEFT + 21 * mm
COL_SKU: Final = LEFT + 118 * mm
COL_QTY_R: Final = RIGHT - 3 * mm
ITEM_WIDTH: Final = 92 * mm


class ReportLabDeliveryNoteRenderer:
    def __init__(self, *, shop_name: str) -> None:
        self._shop_name = shop_name

    def render(self, note: DeliveryNote) -> bytes:
        register_fonts()
        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=A4, pageCompression=1, invariant=True)
        canvas.setTitle(f"Lieferschein {note.order_number}")
        canvas.setAuthor(note.sender.name)
        canvas.setCreator(self._shop_name)
        _Page(canvas, note, self._shop_name).draw()
        canvas.save()
        return buffer.getvalue()


class _Page:
    def __init__(self, canvas: Canvas, note: DeliveryNote, shop_name: str) -> None:
        self.c = canvas
        self.note = note
        self.shop_name = shop_name
        self.page = 1

    def draw(self) -> None:
        self._header()
        self._address()
        self._facts()
        y = self._title(HEIGHT - 102 * mm)
        y = self._table_head(y)
        for position, line in enumerate(self.note.lines, start=1):
            y = self._line(position, line, y)
        y = self._count(y)
        self._closing(y)
        self._footer()

    # --- page furniture -----------------------------------------------------------------

    def _header(self) -> None:
        c = self.c
        sender = self.note.sender
        top = HEIGHT - 22 * mm
        self._wordmark(LEFT, top, 22)
        c.setFillColor(INK_SECONDARY)
        c.setFont(SANS, 8)
        y = top + 4.5 * mm
        for line in (sender.street, sender.place, sender.email, sender.website):
            if line:
                c.drawRightString(RIGHT, y, line)
                y -= 3.6 * mm
        c.setFillColor(MANDARIN)
        c.rect(LEFT, top - 10 * mm, 18 * mm, 1.2 * mm, stroke=0, fill=1)
        c.setStrokeColor(SAND_LINE)
        c.setLineWidth(0.4)
        c.line(LEFT + 18 * mm, top - 9.4 * mm, RIGHT, top - 9.4 * mm)

    def _wordmark(self, x: float, y: float, size: float) -> None:
        """``adp`` red, Times bold italic, the rest in ink, Helvetica bold (ADR 0030)."""
        c = self.c
        name = self.shop_name
        cut = name.find("-")
        head, rest = (name[:cut].lower(), name[cut:]) if cut > 0 else ("", name)
        if head:
            head_size = size * 1.12
            c.setFillColor(LOGO_RED)
            c.setFont("Times-BoldItalic", head_size)
            c.drawString(x, y, head)
            x += stringWidth(head, "Times-BoldItalic", head_size) + size * 0.04
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", size)
        c.drawString(x, y, rest)

    def _footer(self) -> None:
        c = self.c
        sender = self.note.sender
        top = 22 * mm
        c.setStrokeColor(SAND_LINE)
        c.setLineWidth(0.4)
        c.line(LEFT, top + 4 * mm, RIGHT, top + 4 * mm)
        columns = (
            (sender.name, sender.street, sender.place),
            ("Kontakt", sender.email, sender.phone),
            ("Online", sender.website),
        )
        width = CONTENT / 3
        for index, column in enumerate(columns):
            parts = [part for part in column if part]
            if len(parts) < 2:  # noqa: PLR2004 - a heading alone says nothing
                continue
            y = top
            for row, text in enumerate(parts):
                c.setFillColor(INK if row == 0 else INK_SECONDARY)
                c.setFont(SANS_MEDIUM if row == 0 else SANS, 7.5)
                c.drawString(LEFT + index * width, y, text)
                y -= 3.4 * mm
        c.setFillColor(INK_TERTIARY)
        c.setFont(SANS, 7.5)
        c.drawRightString(
            RIGHT, 8 * mm, f"Lieferschein {self.note.order_number} · Seite {self.page}"
        )

    def _next_page(self) -> float:
        self._footer()
        self.c.showPage()
        self.page += 1
        self._wordmark(LEFT, HEIGHT - 22 * mm, 14)
        self.c.setFillColor(INK_SECONDARY)
        self.c.setFont(SANS, 8)
        self.c.drawRightString(
            RIGHT, HEIGHT - 22 * mm, f"Lieferschein {self.note.order_number} · Fortsetzung"
        )
        return self._table_head(HEIGHT - 36 * mm)

    # --- address field and facts --------------------------------------------------------

    def _address(self) -> None:
        c = self.c
        top = HEIGHT - 50 * mm
        sender = self.note.sender.sender_line()
        c.setFillColor(INK_TERTIARY)
        c.setFont(SANS, 6.5)
        c.drawString(LEFT, top, sender)
        c.setStrokeColor(SAND_LINE)
        c.setLineWidth(0.3)
        c.line(LEFT, top - 1.2 * mm, LEFT + stringWidth(sender, SANS, 6.5), top - 1.2 * mm)
        y = top - 7 * mm
        for index, line in enumerate(self.note.recipient):
            c.setFillColor(INK)
            c.setFont(SANS_MEDIUM if index == 0 else SANS, 10)
            c.drawString(LEFT, y, line)
            y -= 4.6 * mm

    def _facts(self) -> None:
        c = self.c
        note = self.note
        rows: list[tuple[str, str, bool]] = [
            ("Bestellung", note.order_number, True),
            ("Bestellt am", f"{note.ordered_on:%d.%m.%Y}", False),
            ("Lieferdatum", f"{note.delivered_on:%d.%m.%Y}", False),
        ]
        if note.marketplace_ref:
            rows.append(("eBay-Bestellung", note.marketplace_ref, True))
        if note.tracking_number:
            rows.append((note.carrier or "Sendung", note.tracking_number, True))
        left = LEFT + 105 * mm
        top = HEIGHT - 46 * mm
        height = (len(rows) * 6 + 5) * mm
        c.setFillColor(SAND)
        c.rect(left, top - height, RIGHT - left, height, stroke=0, fill=1)
        y = top - 6.5 * mm
        for label, value, mono in rows:
            c.setFillColor(INK_SECONDARY)
            c.setFont(SANS, 8)
            c.drawString(left + 5 * mm, y, label)
            c.setFillColor(INK)
            font = MONO if mono else SANS_MEDIUM
            size = 9.0
            while size > 6.75 and stringWidth(value, font, size) > RIGHT - left - 34 * mm:  # noqa: PLR2004
                size -= 0.25
            c.setFont(font, size)
            c.drawRightString(RIGHT - 5 * mm, y, value)
            y -= 6 * mm

    def _title(self, y: float) -> float:
        c = self.c
        c.setFillColor(INK)
        c.setFont(SANS_MEDIUM, 22)
        c.drawString(LEFT, y, "Lieferschein")
        c.setFont(SANS, 9.5)
        c.setFillColor(INK_SECONDARY)
        c.drawString(LEFT, y - 8 * mm, "In diesem Paket liegen für dich:")
        return y - 16 * mm

    # --- the pieces ---------------------------------------------------------------------

    def _table_head(self, y: float) -> float:
        c = self.c
        c.setFillColor(INK)
        c.rect(LEFT, y - 2.2 * mm, CONTENT, 7 * mm, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont(SANS_MEDIUM, 7.5)
        c.drawString(COL_CHECK, y, "OK")
        c.drawString(COL_POS, y, "POS.")
        c.drawString(COL_ITEM, y, "ARTIKEL")
        c.drawString(COL_SKU, y, "ART.-NR.")
        c.drawRightString(COL_QTY_R, y, "MENGE")
        return y - 9 * mm

    def _line(self, position: int, line: DeliveryLine, y: float) -> float:
        c = self.c
        title = simpleSplit(line.title, SANS_MEDIUM, 10, ITEM_WIDTH)
        height = (len(title) * 4.6 + 4) * mm
        if y - height < FOOTER_TOP + 24 * mm:
            y = self._next_page()
        # The box to tick while packing.
        c.setStrokeColor(INK_TERTIARY)
        c.setLineWidth(0.7)
        c.roundRect(COL_CHECK, y - 1.2 * mm, 4.2 * mm, 4.2 * mm, 0.6 * mm, stroke=1, fill=0)
        c.setFillColor(INK_TERTIARY)
        c.setFont(MONO, 8.5)
        c.drawString(COL_POS, y, f"{position:02d}")
        c.setFillColor(INK_SECONDARY)
        c.setFont(MONO, 8.5)
        c.drawString(COL_SKU, y, line.sku)
        c.setFillColor(INK)
        c.setFont(SANS_MEDIUM, 11)
        c.drawRightString(COL_QTY_R, y, f"{line.quantity}\u00d7")
        cursor = y
        for text in title:
            c.setFont(SANS_MEDIUM, 10)
            c.drawString(COL_ITEM, cursor, text)
            cursor -= 4.6 * mm
        bottom = cursor + 0.4 * mm
        c.setStrokeColor(SAND_LINE)
        c.setLineWidth(0.4)
        c.line(LEFT, bottom, RIGHT, bottom)
        return bottom - 5.6 * mm

    def _count(self, y: float) -> float:
        c = self.c
        if y < FOOTER_TOP + 50 * mm:  # the count and the closing card stay together
            y = self._next_page()
        pieces = self.note.pieces
        label = "1 Stück" if pieces == 1 else f"{pieces} Stück"
        left = LEFT + 118 * mm
        c.setFillColor(SAND)
        c.rect(left - 4 * mm, y - 6.5 * mm, RIGHT - left + 4 * mm, 10 * mm, stroke=0, fill=1)
        c.setFillColor(MANDARIN)
        c.rect(left - 4 * mm, y - 6.5 * mm, 1.2 * mm, 10 * mm, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont(SANS_MEDIUM, 10.5)
        c.drawString(left, y - 3 * mm, "Im Paket")
        c.setFont(SANS_MEDIUM, 12)
        c.drawRightString(COL_QTY_R, y - 3.2 * mm, label)
        return y - 20 * mm

    def _closing(self, y: float) -> None:
        """A sand card with the thanks and whom to write; above the footer."""
        c = self.c
        sender = self.note.sender
        top = max(min(y, FOOTER_TOP + 50 * mm), FOOTER_TOP + 30 * mm)
        height = 22 * mm
        c.setFillColor(SAND)
        c.roundRect(LEFT, top - height, CONTENT, height, 2 * mm, stroke=0, fill=1)
        c.setFillColor(MANDARIN)
        c.rect(LEFT, top - height, 1.6 * mm, height, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont(SANS_MEDIUM, 11)
        c.drawString(LEFT + 7 * mm, top - 7.5 * mm, "Vielen Dank für deine Bestellung!")
        contact = sender.email or sender.phone
        text = (
            "Jedes Modell ist bei uns in Handarbeit gedruckt, lackiert und montiert. "
            "Fehlt etwas oder kam etwas beschädigt an? "
            + (f"Schreib uns an {contact}, wir kümmern uns." if contact else "Melde dich bei uns.")
        )
        c.setFillColor(INK_SECONDARY)
        c.setFont(SANS, 8.5)
        cursor = top - 12.5 * mm
        for part in simpleSplit(text, SANS, 8.5, CONTENT - 14 * mm):
            c.drawString(LEFT + 7 * mm, cursor, part)
            cursor -= 4 * mm
