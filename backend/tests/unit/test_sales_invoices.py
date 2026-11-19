"""Invoice numbers, the issuer from the settings and the PDF (ADR 0038)."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pypdfium2 as pdfium
import pytest

from modellbahn.modules.sales.domain.invoices import (
    InvoiceDocument,
    InvoiceKind,
    InvoiceLine,
    invoice_number,
    local_date,
)
from modellbahn.modules.sales.infrastructure.invoices import (
    ReportLabInvoiceRenderer,
    euro,
    issuer_of,
)
from modellbahn.platform.config import Settings
from tests.conftest import TEST_ISSUER


def document(**changes: object) -> InvoiceDocument:
    base = InvoiceDocument(
        kind=InvoiceKind.INVOICE,
        number="RE-2026-00001",
        issued_on=date(2026, 11, 19),
        delivered_on=date(2026, 11, 19),
        order_number="MB-2026-00002",
        issuer=TEST_ISSUER,
        recipient=("Erika Mustermann", "Hauptstraße 5", "10115 Berlin"),
        email="erika@example.de",
        lines=(
            InvoiceLine(
                description="EDK 6 Kranwagen, H0, lackiert",
                detail="Art.-Nr. MB-000006-H0-B",
                quantity=1,
                unit_cents=4990,
                total_cents=4990,
            ),
            InvoiceLine(description="Versand", quantity=1, unit_cents=590, total_cents=590),
        ),
        total_cents=5580,
        tax_cents=891,
        vat_percent=19,
        notes=("Bezahlt per Karte (SumUp) am 19.11.2026.",),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def text_of(pdf: bytes) -> tuple[int, str]:
    pages = pdfium.PdfDocument(pdf)
    try:
        return len(pages), "".join(page.get_textpage().get_text_range() for page in pages)
    finally:
        pages.close()


class TestNumbers:
    def test_series_year_and_serial(self) -> None:
        assert invoice_number(InvoiceKind.INVOICE, 2026, 1) == "RE-2026-00001"
        assert invoice_number(InvoiceKind.CORRECTION, 2027, 123456) == "RK-2027-123456"
        with pytest.raises(ValueError, match="start at 1"):
            invoice_number(InvoiceKind.INVOICE, 2026, 0)

    def test_the_year_is_the_shops_not_utcs(self) -> None:
        # New Year's Eve, 23:30 UTC, is already the new year in Neustrelitz.
        assert local_date(datetime(2026, 12, 31, 23, 30, tzinfo=UTC)) == date(2027, 1, 1)

    def test_euro_amounts(self) -> None:
        assert euro(123450) == "1.234,50\u00a0€"
        assert euro(-590) == "\u22125,90\u00a0€"


class TestIssuer:
    def test_none_without_a_tax_reference(self, settings: Settings) -> None:
        assert issuer_of(settings) is None

    def test_the_tax_number_until_there_is_a_vat_id(self, settings: Settings) -> None:
        with_number = settings.model_copy(update={"imprint_tax_number": "075 / 123 / 45678"})
        issuer = issuer_of(with_number)
        assert issuer is not None
        assert (issuer.tax_label, issuer.name) == ("Steuernummer", "adp-Modelle")
        with_vat_id = with_number.model_copy(update={"imprint_vat_id": "DE123456789"})
        issuer = issuer_of(with_vat_id)
        assert issuer is not None
        assert (issuer.tax_label, issuer.tax_id) == ("USt-IdNr.", "DE123456789")

    def test_none_while_the_imprint_is_incomplete(self, settings: Settings) -> None:
        incomplete = settings.model_copy(
            update={"imprint_tax_number": "075/123/45678", "imprint_street": ""}
        )
        assert issuer_of(incomplete) is None

    def test_the_address_leaves_out_germany(self) -> None:
        assert TEST_ISSUER.address_lines()[-1] == "17235 Neustrelitz"
        abroad = replace(TEST_ISSUER, country="Österreich")
        assert abroad.address_lines()[-1] == "Österreich"


class TestPdf:
    renderer = ReportLabInvoiceRenderer(shop_name="adp-Modelle")

    def test_an_invoice_names_everything_paragraph_14_asks_for(self) -> None:
        pages, text = text_of(self.renderer.render(document()))
        assert pages == 1
        for expected in (
            "Rechnung",
            "RE-2026-00001",
            "MB-2026-00002",
            "Erika Mustermann",
            "Glambecker Straße 2",
            "075/123/45678",
            "EDK 6 Kranwagen",
            "Versand",
            "55,80",
            "8,91",
            "19 %",
        ):
            assert expected in text, expected

    def test_a_correction_names_its_invoice(self) -> None:
        correction = document(
            kind=InvoiceKind.CORRECTION,
            number="RK-2026-00001",
            lines=(
                InvoiceLine(
                    description="Erstattung", quantity=1, unit_cents=-1190, total_cents=-1190
                ),
            ),
            total_cents=-1190,
            tax_cents=-190,
            corrects=("RE-2026-00001", date(2026, 11, 19)),
        )
        _, text = text_of(self.renderer.render(correction))
        assert "Rechnungskorrektur" in text
        assert "RK-2026-00001" in text
        assert "RE-2026-00001" in text
        assert "\u221211,90" in text

    def test_many_lines_run_onto_further_pages(self) -> None:
        line = InvoiceLine(description="Prellbock", quantity=2, unit_cents=500, total_cents=1000)
        long = document(lines=(line,) * 60, total_cents=60_000, tax_cents=9580)
        pages, text = text_of(self.renderer.render(long))
        assert pages > 1
        assert text.count("Prellbock") == 60
        assert "600,00" in text

    def test_the_same_document_gives_the_same_bytes(self) -> None:
        assert self.renderer.render(document()) == self.renderer.render(document())
