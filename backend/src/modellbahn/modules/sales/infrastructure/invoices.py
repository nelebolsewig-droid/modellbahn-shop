"""Invoices as PDF with reportlab, in the shop's own look (ADR 0030, ADR 0038).

A4 after DIN 5008 form B, so the address shows in the window of a C5/6 or DL envelope:
the wordmark at the top, the sender line and the recipient in the address field, the
document's numbers and dates in a sand box beside it, then the lines, the totals with the
VAT and a footer with the operator, contact and tax number on every page.

Colours are the shop's tokens: espresso ink on white, sand for boxes, mandarin as the one
accent; the wordmark "adp" in the logo's red. Text is Geist, embedded; the wordmark in
Times and Helvetica, as the website sets it in Times New Roman and Arial.
"""

from io import BytesIO
from typing import Final

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from modellbahn.modules.sales.domain.invoices import (
    InvoiceDocument,
    InvoiceKind,
    InvoiceLine,
    Issuer,
)
from modellbahn.platform.config import Settings
from modellbahn.platform.pdf_fonts import MONO, SANS, SANS_MEDIUM, register_fonts

INK: Final = HexColor("#26211e")
INK_SECONDARY: Final = HexColor("#665b53")
INK_TERTIARY: Final = HexColor("#85786b")
SAND: Final = HexColor("#efe7dc")
SAND_LINE: Final = HexColor("#ddd0be")
MANDARIN: Final = HexColor("#e8632b")
LOGO_RED: Final = HexColor("#cc0000")

WIDTH, HEIGHT = A4
LEFT: Final = 20 * mm
RIGHT: Final = WIDTH - 15 * mm
CONTENT: Final = RIGHT - LEFT
FOOTER_TOP: Final = 30 * mm
"""Lines and notes stop above the footer."""

# Columns of the lines table, as their right edges (amounts align right).
COL_POS: Final = LEFT
COL_ITEM: Final = LEFT + 10 * mm
COL_QTY_R: Final = LEFT + 118 * mm
COL_UNIT_R: Final = LEFT + 146 * mm
COL_TOTAL_R: Final = RIGHT
ITEM_WIDTH: Final = 92 * mm


MINUS: Final = "\u2212"
NBSP: Final = "\u00a0"


def euro(cents: int) -> str:
    """``1.234,50 €``, negative with a true minus sign."""
    sign = MINUS if cents < 0 else ""
    euros, rest = divmod(abs(cents), 100)
    return f"{sign}{euros:,}".replace(",", ".") + f",{rest:02d}{NBSP}€"


class ReportLabInvoiceRenderer:
    """The :class:`~modellbahn.modules.sales.application.ports.InvoiceRenderer` for PDF."""

    def __init__(self, *, shop_name: str) -> None:
        self._shop_name = shop_name

    def render(self, document: InvoiceDocument) -> bytes:
        register_fonts()
        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=A4, pageCompression=1, invariant=True)
        canvas.setTitle(f"{document.title} {document.number}")
        canvas.setAuthor(document.issuer.name)
        canvas.setSubject(f"{document.title} zur Bestellung {document.order_number}")
        canvas.setCreator(self._shop_name)
        _Page(canvas, document, self._shop_name).draw()
        canvas.save()
        return buffer.getvalue()


class _Page:
    """Draws the document page by page; the lines continue on the next page if needed."""

    def __init__(self, canvas: Canvas, document: InvoiceDocument, shop_name: str) -> None:
        self.c = canvas
        self.doc = document
        self.shop_name = shop_name
        self.page = 1

    # --- the whole document -------------------------------------------------------------

    def draw(self) -> None:
        self._header()
        self._address()
        self._facts()
        y = self._title(HEIGHT - 102 * mm)
        y = self._table_head(y)
        for position, line in enumerate(self.doc.lines, start=1):
            y = self._line(position, line, y)
        y = self._totals(y)
        self._notes(y)
        self._footer()

    # --- page furniture -----------------------------------------------------------------

    def _header(self) -> None:
        c = self.c
        top = HEIGHT - 22 * mm
        self._wordmark(LEFT, top, 22)
        # The operator's address at the top right, small, as a letterhead.
        c.setFillColor(INK_SECONDARY)
        c.setFont(SANS, 8)
        lines = [*self.doc.issuer.address_lines()[1:], self.doc.issuer.email]
        y = top + 4.5 * mm
        for line in lines:
            if line:
                c.drawRightString(RIGHT, y, line)
                y -= 3.6 * mm
        # A mandarin rule under the head: the one accent of the page.
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
        issuer = self.doc.issuer
        top = 22 * mm
        c.setStrokeColor(SAND_LINE)
        c.setLineWidth(0.4)
        c.line(LEFT, top + 4 * mm, RIGHT, top + 4 * mm)
        columns = (
            (issuer.name, issuer.owner, issuer.street, f"{issuer.postal_code} {issuer.city}"),
            ("Kontakt", issuer.email, issuer.phone),
            ("Steuer", f"{issuer.tax_label} {issuer.tax_id}"),
        )
        width = CONTENT / 3
        for index, column in enumerate(columns):
            x = LEFT + index * width
            y = top
            for row, text in enumerate(part for part in column if part):
                c.setFillColor(INK if row == 0 else INK_SECONDARY)
                c.setFont(SANS_MEDIUM if row == 0 else SANS, 7.5)
                c.drawString(x, y, text)
                y -= 3.4 * mm
        c.setFillColor(INK_TERTIARY)
        c.setFont(SANS, 7.5)
        c.drawRightString(RIGHT, 8 * mm, f"{self.doc.number} · Seite {self.page}")

    def _next_page(self) -> float:
        self._footer()
        self.c.showPage()
        self.page += 1
        self._wordmark(LEFT, HEIGHT - 22 * mm, 14)
        self.c.setFillColor(INK_SECONDARY)
        self.c.setFont(SANS, 8)
        self.c.drawRightString(
            RIGHT, HEIGHT - 22 * mm, f"{self.doc.title} {self.doc.number} · Fortsetzung"
        )
        return self._table_head(HEIGHT - 36 * mm)

    # --- address field and facts --------------------------------------------------------

    def _address(self) -> None:
        """DIN 5008 form B: the field starts 45 mm from the top, 20 mm from the left."""
        c = self.c
        top = HEIGHT - 50 * mm
        c.setFillColor(INK_TERTIARY)
        c.setFont(SANS, 6.5)
        sender = self.doc.issuer.sender_line()
        c.drawString(LEFT, top, sender)
        c.setStrokeColor(SAND_LINE)
        c.setLineWidth(0.3)
        c.line(LEFT, top - 1.2 * mm, LEFT + stringWidth(sender, SANS, 6.5), top - 1.2 * mm)
        y = top - 7 * mm
        for index, line in enumerate(self.doc.recipient):
            c.setFillColor(INK)
            c.setFont(SANS_MEDIUM if index == 0 else SANS, 10)
            c.drawString(LEFT, y, line)
            y -= 4.6 * mm

    def _facts(self) -> None:
        c = self.c
        doc = self.doc
        number_label = "Rechnungsnr." if doc.kind is InvoiceKind.INVOICE else "Korrekturnr."
        rows: list[tuple[str, str, bool]] = [
            (number_label, doc.number, True),
            ("Datum", f"{doc.issued_on:%d.%m.%Y}", False),
            ("Lieferdatum", f"{doc.delivered_on:%d.%m.%Y}", False),
            ("Bestellung", doc.order_number, True),
        ]
        if doc.corrects is not None:
            number, issued_on = doc.corrects
            rows.append(("zu Rechnung", number, True))
            rows.append(("vom", f"{issued_on:%d.%m.%Y}", False))
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
            size = _fit(value, font, 9, RIGHT - left - 34 * mm)
            c.setFont(font, size)
            c.drawRightString(RIGHT - 5 * mm, y, value)
            y -= 6 * mm

    def _title(self, y: float) -> float:
        c = self.c
        c.setFillColor(INK)
        c.setFont(SANS_MEDIUM, 22)
        c.drawString(LEFT, y, self.doc.title)
        c.setFont(SANS, 9.5)
        c.setFillColor(INK_SECONDARY)
        if self.doc.kind is InvoiceKind.INVOICE:
            intro = "Wir berechnen dir folgende Lieferung:"
        else:
            intro = "Wir korrigieren die oben genannte Rechnung wie folgt:"
        c.drawString(LEFT, y - 8 * mm, intro)
        return y - 16 * mm

    # --- the lines ----------------------------------------------------------------------

    def _table_head(self, y: float) -> float:
        c = self.c
        c.setFillColor(INK)
        c.rect(LEFT, y - 2.2 * mm, CONTENT, 7 * mm, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont(SANS_MEDIUM, 7.5)
        base = y
        c.drawString(COL_POS + 2 * mm, base, "POS.")
        c.drawString(COL_ITEM, base, "ARTIKEL")
        c.drawRightString(COL_QTY_R, base, "MENGE")
        c.drawRightString(COL_UNIT_R, base, "EINZELPREIS")
        c.drawRightString(COL_TOTAL_R - 2 * mm, base, "GESAMT")
        return y - 9 * mm

    def _line(self, position: int, line: InvoiceLine, y: float) -> float:
        c = self.c
        title = simpleSplit(line.description, SANS_MEDIUM, 9.5, ITEM_WIDTH)
        detail = simpleSplit(line.detail, SANS, 8, ITEM_WIDTH) if line.detail else []
        height = (len(title) * 4.4 + len(detail) * 3.8 + 3.2) * mm
        if y - height < FOOTER_TOP + 10 * mm:
            y = self._next_page()
        c.setFillColor(INK_TERTIARY)
        c.setFont(MONO, 8.5)
        c.drawString(COL_POS + 2 * mm, y, f"{position:02d}")
        c.setFillColor(INK)
        c.setFont(SANS, 9.5)
        c.drawRightString(COL_QTY_R, y, f"{line.quantity}")
        c.drawRightString(COL_UNIT_R, y, euro(line.unit_cents))
        c.setFont(SANS_MEDIUM, 9.5)
        c.drawRightString(COL_TOTAL_R - 2 * mm, y, euro(line.total_cents))
        cursor = y
        for text in title:
            c.setFont(SANS_MEDIUM, 9.5)
            c.setFillColor(INK)
            c.drawString(COL_ITEM, cursor, text)
            cursor -= 4.4 * mm
        for text in detail:
            c.setFont(SANS, 8)
            c.setFillColor(INK_SECONDARY)
            c.drawString(COL_ITEM, cursor + 0.6 * mm, text)
            cursor -= 3.8 * mm
        bottom = cursor + 1.2 * mm
        c.setStrokeColor(SAND_LINE)
        c.setLineWidth(0.4)
        c.line(LEFT, bottom, RIGHT, bottom)
        return bottom - 5.2 * mm

    # --- totals and notes ---------------------------------------------------------------

    def _totals(self, y: float) -> float:
        c = self.c
        doc = self.doc
        needed = 34 * mm
        if y - needed < FOOTER_TOP:
            y = self._next_page()
        label_x = LEFT + 100 * mm
        rows = (
            ("Nettobetrag", euro(doc.net_cents)),
            (f"Umsatzsteuer {doc.vat_percent} %", euro(doc.tax_cents)),
        )
        y -= 1 * mm
        for label, value in rows:
            c.setFillColor(INK_SECONDARY)
            c.setFont(SANS, 9)
            c.drawString(label_x, y, label)
            c.setFillColor(INK)
            c.drawRightString(COL_TOTAL_R - 2 * mm, y, value)
            y -= 5.5 * mm
        # The total in a sand box with a mandarin edge: the one figure that counts.
        box_top = y + 2.5 * mm
        c.setFillColor(SAND)
        c.rect(label_x - 4 * mm, box_top - 10 * mm, RIGHT - label_x + 4 * mm, 10 * mm, 0, 1)
        c.setFillColor(MANDARIN)
        c.rect(label_x - 4 * mm, box_top - 10 * mm, 1.2 * mm, 10 * mm, stroke=0, fill=1)
        c.setFillColor(INK)
        c.setFont(SANS_MEDIUM, 10.5)
        label = "Gesamtbetrag" if doc.kind is InvoiceKind.INVOICE else "Korrekturbetrag"
        c.drawString(label_x, box_top - 6.4 * mm, label)
        c.setFont(SANS_MEDIUM, 12)
        c.drawRightString(COL_TOTAL_R - 2 * mm, box_top - 6.6 * mm, euro(doc.total_cents))
        return box_top - 20 * mm

    def _notes(self, y: float) -> None:
        c = self.c
        for note in self.doc.notes:
            lines = simpleSplit(note, SANS, 9, CONTENT)
            if y - len(lines) * 4.6 * mm < FOOTER_TOP:
                y = self._next_page() - 4 * mm
            c.setFillColor(INK_SECONDARY)
            c.setFont(SANS, 9)
            for text in lines:
                c.drawString(LEFT, y, text)
                y -= 4.6 * mm
            y -= 1.4 * mm


def _fit(text: str, font: str, size: float, width: float) -> float:
    """The size at which ``text`` fits ``width``, down to 75 %."""
    fitted = size
    while fitted > size * 0.75 and stringWidth(text, font, fitted) > width:
        fitted -= 0.25
    return fitted


def issuer_of(settings: Settings) -> Issuer | None:
    """The shop's operator as the issuer of its invoices.

    None while the imprint is incomplete or neither a VAT ID nor a tax number is set:
    an invoice without them is no proper invoice (§ 14 Abs. 4 UStG), so none is written.
    """
    imprint = settings.imprint
    tax = imprint.tax_reference
    if not imprint.is_complete or tax is None:
        return None
    label, tax_id = tax
    return Issuer(
        name=imprint.company,
        owner=imprint.owner,
        street=imprint.street,
        postal_code=imprint.postal_code,
        city=imprint.city,
        country=imprint.country,
        email=imprint.email,
        phone=imprint.phone,
        tax_label=label,
        tax_id=tax_id,
    )
