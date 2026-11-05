"""Withdrawals without a database: what a declaration keeps, and what the e-mails say."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from modellbahn.modules.sales.application import mails
from modellbahn.modules.sales.domain.errors import InvalidFieldError
from modellbahn.modules.sales.domain.withdrawals import (
    WITHDRAWAL_SCOPE_MAX_LENGTH,
    Withdrawal,
)
from tests.unit.test_sales_domain import placed

# 15:42 in German winter time.
NOW = datetime(2026, 11, 4, 14, 42, tzinfo=UTC)


def declare(**changes: object) -> Withdrawal:
    values: dict[str, object] = {
        "name": "  Erika   Mustermann ",
        "order_reference": " mb-2026-00042 ",
        "email": "Erika@Example.DE",
        "scope": "",
        "order": None,
        "now": NOW,
    }
    values.update(changes)
    withdrawal, _ = Withdrawal.declare(**values)  # type: ignore[arg-type]
    return withdrawal


class TestDeclaration:
    def test_keeps_what_was_declared_and_when(self) -> None:
        withdrawal = declare()
        assert (withdrawal.name, withdrawal.order_reference, withdrawal.email) == (
            "Erika Mustermann",
            "MB-2026-00042",
            "Erika@example.de",
        )
        assert withdrawal.received_at == NOW
        assert withdrawal.whole_order
        assert withdrawal.order_id is None

    def test_names_the_order_only_when_number_and_address_fit(self) -> None:
        order, _ = placed()  # MB-2026-00042 for Erika@example.de
        fits, event = Withdrawal.declare(
            name="Erika Mustermann",
            order_reference="MB-2026-00042",
            email="erika@EXAMPLE.de",
            scope="",
            order=order,
            now=NOW,
        )
        assert fits.order_id == order.id
        assert (event.order_id, event.number) == (order.id, "MB-2026-00042")
        assert event.public_payload() == {
            "withdrawal_id": str(fits.id),
            "order_id": str(order.id),
            "number": "MB-2026-00042",
        }

        stranger, event = Withdrawal.declare(
            name="Max Muster",
            order_reference="MB-2026-00042",
            email="max@example.de",
            scope="",
            order=order,
            now=NOW,
        )
        # Taken all the same; staff judge it. The payload names no order and no person.
        assert stranger.order_id is None
        assert event.public_payload() == {
            "withdrawal_id": str(stranger.id),
            "order_id": None,
            "number": None,
        }

    def test_some_articles_only(self) -> None:
        withdrawal = declare(scope=" nur den   Kesselwagen ")
        assert withdrawal.scope == "nur den Kesselwagen"
        assert not withdrawal.whole_order

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"name": "  "}, "name"),
            ({"order_reference": ""}, "order_number"),
            ({"email": "keine-adresse"}, "email"),
            ({"scope": "x" * (WITHDRAWAL_SCOPE_MAX_LENGTH + 1)}, "scope"),
        ],
    )
    def test_refuses_what_cannot_be_confirmed(self, changes: dict[str, str], field: str) -> None:
        with pytest.raises(InvalidFieldError) as raised:
            declare(**changes)
        assert raised.value.field == field


class TestMails:
    def test_the_confirmation_repeats_what_came_in_and_when(self) -> None:
        content = mails.withdrawal_receipt_mail(declare(scope="nur den Kesselwagen"))
        assert content.subject == "Eingangsbestätigung: dein Widerruf zu Bestellung MB-2026-00042"
        assert content.greeting == "Hallo Erika Mustermann,"
        assert "am 04.11.2026 um 15:42 Uhr bei uns eingegangen" in content.paragraphs[0]
        assert "Widerrufen: nur den Kesselwagen" in content.paragraphs
        assert [(row.label, row.value) for row in content.rows] == [
            ("Name", "Erika Mustermann"),
            ("Bestellnummer", "MB-2026-00042"),
            ("E-Mail-Adresse", "Erika@example.de"),
            ("Eingegangen am", "04.11.2026 um 15:42 Uhr"),
        ]
        closing = " ".join(content.closing)
        assert "Die Kosten der Rücksendung trägst du." in closing
        assert "spätestens 14 Tage nach Eingang" in closing

    def test_the_shop_learns_whether_it_fits_an_order(self) -> None:
        unmatched = mails.withdrawal_notice_mail(declare(), base_url="https://shop.test")
        assert unmatched.subject == "Widerruf eingegangen: MB-2026-00042"
        assert "Widerrufen: die ganze Bestellung." in unmatched.paragraphs
        assert "passt keine Bestellung" in unmatched.closing[0]
        assert unmatched.action is not None
        assert unmatched.action.url == "https://shop.test/admin/bestellungen"

        order_id = uuid4()
        matched = declare()
        matched.order_id = order_id
        notice = mails.withdrawal_notice_mail(matched, base_url="https://shop.test")
        assert "passen zu einer Bestellung" in notice.closing[0]
        assert notice.action is not None
        assert notice.action.url == f"https://shop.test/admin/bestellungen/{order_id}"
