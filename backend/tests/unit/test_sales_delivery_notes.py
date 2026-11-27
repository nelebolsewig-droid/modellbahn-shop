"""The delivery note for the parcel: what it shows, and that it has no prices (ADR 0047)."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pypdfium2 as pdfium
import pytest

from modellbahn.modules.sales.domain.delivery_notes import Sender, delivery_note
from modellbahn.modules.sales.domain.errors import InvalidOrderStateError
from modellbahn.modules.sales.domain.model import Order, OrderStatus, SalesChannel
from modellbahn.modules.sales.infrastructure.delivery_notes import ReportLabDeliveryNoteRenderer
from modellbahn.platform.config import Settings
from tests.unit.test_sales_domain import item, placed

SENDER = Sender(
    name="adp-Modelle",
    street="Glambecker Straße 2",
    postal_code="17235",
    city="Neustrelitz",
    email="info@adp-modelle.de",
    website="www.adp-modelle.de",
)
PRINTED = datetime(2026, 11, 24, 16, 0, tzinfo=UTC)


def order(*, status: OrderStatus = OrderStatus.PAID, country: str = "DE") -> Order:
    made, _ = placed(item(4990, 2), replace(item(1290), sku="MB-000007-H0-B"), country=country)
    made.status = status
    return made


def text_of(pdf: bytes) -> tuple[int, str]:
    pages = pdfium.PdfDocument(pdf)
    try:
        return len(pages), "".join(page.get_textpage().get_text_range() for page in pages)
    finally:
        pages.close()


class TestNote:
    def test_lines_and_pieces_without_prices(self) -> None:
        note = delivery_note(order(), sender=SENDER, printed_at=PRINTED)
        assert [(line.sku, line.quantity) for line in note.lines] == [
            ("MB-000001-H0-F", 2),
            ("MB-000007-H0-B", 1),
        ]
        assert note.pieces == 3
        assert note.recipient == ("Erika Mustermann", "Bahnhofstraße 12", "38707 Altenau")
        assert (note.ordered_on, note.delivered_on) == (date(2026, 10, 25), date(2026, 11, 24))
        assert note.filename == "Lieferschein-MB-2026-00042.pdf"

    def test_abroad_with_the_country_and_dated_the_dispatch(self) -> None:
        shipped = order(status=OrderStatus.SHIPPED, country="AT")
        shipped.shipped_at = datetime(2026, 11, 20, 23, 30, tzinfo=UTC)
        note = delivery_note(shipped, sender=SENDER, printed_at=PRINTED)
        assert note.recipient[-1] == "Österreich"
        assert note.delivered_on == date(2026, 11, 21)  # already the 21st in Neustrelitz

    def test_the_marketplace_number_for_ebay_orders(self) -> None:
        sold = replace(order(), channel=SalesChannel.EBAY, external_ref="12-34567-89012")
        assert delivery_note(sold, sender=SENDER, printed_at=PRINTED).marketplace_ref == (
            "12-34567-89012"
        )
        assert delivery_note(order(), sender=SENDER, printed_at=PRINTED).marketplace_ref == ""

    @pytest.mark.parametrize("status", [OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED])
    def test_only_for_orders_that_are_packed(self, status: OrderStatus) -> None:
        with pytest.raises(InvalidOrderStateError):
            delivery_note(order(status=status), sender=SENDER, printed_at=PRINTED)

    def test_the_sender_from_the_settings(self) -> None:
        settings = Settings(
            imprint_company="adp-Modelle",
            imprint_street="Glambecker Straße 2",
            imprint_postal_code="17235",
            imprint_city="Neustrelitz",
            public_base_url="https://www.adp-modelle.de/",
        )
        sender = Sender.of(settings.imprint, website=settings.public_base_url)
        assert sender.website == "www.adp-modelle.de"
        assert sender.sender_line() == "adp-Modelle · Glambecker Straße 2 · 17235 Neustrelitz"
        # Without an imprint the shop's name still signs it: no tax number needed.
        assert Sender.of(Settings().imprint).name == Settings().shop_name


class TestPdf:
    def test_one_page_with_everything_and_no_euro(self) -> None:
        note = delivery_note(order(), sender=SENDER, printed_at=PRINTED)
        pdf = ReportLabDeliveryNoteRenderer(shop_name="adp-Modelle").render(note)
        assert pdf.startswith(b"%PDF")
        pages, text = text_of(pdf)
        assert pages == 1
        for expected in ("Lieferschein", "MB-2026-00042", "Erika Mustermann", "3 Stück"):
            assert expected in text
        assert "€" not in text

    def test_many_lines_continue_on_the_next_page(self) -> None:
        many = order()
        many.lines = [replace(many.lines[0], position=index) for index in range(40)]
        note = delivery_note(many, sender=SENDER, printed_at=PRINTED)
        pages, text = text_of(ReportLabDeliveryNoteRenderer(shop_name="adp-Modelle").render(note))
        assert pages > 1
        assert "Fortsetzung" in text
        assert "80 Stück" in text
