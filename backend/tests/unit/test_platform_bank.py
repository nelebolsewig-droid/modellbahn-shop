"""The shop's bank account for payment in advance: IBAN, BIC, GiroCode (ADR 0022)."""

from typing import Final

import pytest
from pydantic import ValidationError

from modellbahn.platform.bank import (
    BankAccount,
    bic_is_valid,
    girocode_svg,
    iban_is_valid,
    normalise_iban,
)
from modellbahn.platform.config import Environment, PaymentProvider, Settings
from tests.unit.test_platform_basics import IMPRINT, OWN_KEY

EXAMPLE_IBAN: Final = "DE89370400440532013000"
OWN_IBAN: Final = "DE02120300000000202051"


class TestIban:
    def test_normalises_and_checks_the_digits(self) -> None:
        assert normalise_iban(" de89 3704 0044 0532 0130 00 ") == EXAMPLE_IBAN
        assert iban_is_valid(EXAMPLE_IBAN)
        assert iban_is_valid(OWN_IBAN)
        assert not iban_is_valid("DE89370400440532013001")  # one digit off
        assert not iban_is_valid("DE8937040044")  # too short
        assert not iban_is_valid("89DE370400440532013000")

    def test_bic_has_eight_or_eleven_characters(self) -> None:
        assert bic_is_valid("COBADEFF")
        assert bic_is_valid("COBADEFFXXX")
        assert not bic_is_valid("COBADEFFX")
        assert not bic_is_valid("12BADEFF")


class TestGiroCode:
    def test_payload_follows_the_epc_layout(self) -> None:
        account = BankAccount(holder="adp-Modelle", iban=OWN_IBAN, bic="BYLADEM1001")
        lines = account.epc_payload(amount_cents=7990, reference="MB-2026-00042").split("\n")
        assert lines == [
            "BCD",
            "002",
            "1",
            "SCT",
            "BYLADEM1001",
            "adp-Modelle",
            OWN_IBAN,
            "EUR79.90",
            "",
            "",
            "MB-2026-00042",
        ]

    def test_long_names_are_cut_and_amounts_checked(self) -> None:
        account = BankAccount(holder="x" * 90, iban=OWN_IBAN)
        lines = account.epc_payload(amount_cents=5, reference="MB-1").split("\n")
        assert (lines[4], len(lines[5]), lines[7]) == ("", 70, "EUR0.05")
        with pytest.raises(ValueError, match="amount"):
            account.epc_payload(amount_cents=0, reference="MB-1")

    def test_the_svg_stands_alone(self) -> None:
        account = BankAccount(holder="adp-Modelle", iban=OWN_IBAN)
        svg = girocode_svg(account.epc_payload(amount_cents=7990, reference="MB-2026-00042"))
        assert svg.startswith(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox=')
        assert b"<title>GiroCode</title>" in svg

    def test_iban_is_grouped_for_people(self) -> None:
        assert BankAccount(holder="x", iban=EXAMPLE_IBAN).iban_grouped == (
            "DE89 3704 0044 0532 0130 00"
        )


class TestSettings:
    def test_payment_in_advance_is_off_without_an_account(self) -> None:
        assert Settings().bank_account is None

    def test_reads_and_cleans_the_account(self) -> None:
        settings = Settings(
            bank_account_holder=" adp-Modelle ",
            bank_iban="de02 1203 0000 0000 2020 51",
            bank_bic="byla dem1 001",
            bank_name="Testbank",
        )
        assert settings.bank_account == BankAccount(
            holder="adp-Modelle", iban=OWN_IBAN, bic="BYLADEM1001", bank_name="Testbank"
        )

    def test_refuses_a_wrong_iban_or_half_an_account(self) -> None:
        with pytest.raises(ValidationError, match="IBAN"):
            Settings(bank_account_holder="adp-Modelle", bank_iban="DE02120300000000202052")
        with pytest.raises(ValidationError, match="MB_BANK_ACCOUNT_HOLDER and MB_BANK_IBAN"):
            Settings(bank_iban=OWN_IBAN)
        with pytest.raises(ValidationError, match="MB_BANK_ACCOUNT_HOLDER and MB_BANK_IBAN"):
            Settings(bank_account_holder="adp-Modelle")
        with pytest.raises(ValidationError, match="BIC"):
            Settings(bank_account_holder="adp-Modelle", bank_iban=OWN_IBAN, bank_bic="XX")

    def test_production_refuses_the_example_account(self) -> None:
        production = {
            "environment": Environment.PRODUCTION,
            "s3_access_key_id": OWN_KEY,
            "payment_provider": PaymentProvider.OFF,
            "bank_account_holder": "adp-Modelle",
            **IMPRINT,
        }
        with pytest.raises(ValidationError, match="example account"):
            Settings(bank_iban=EXAMPLE_IBAN, **production)
        assert Settings(bank_iban=OWN_IBAN, **production).bank_account is not None
