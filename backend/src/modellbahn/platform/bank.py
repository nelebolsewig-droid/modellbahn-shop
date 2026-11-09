"""The shop's bank account for payment in advance (ADR 0022), from the settings.

Customers who pay by bank transfer see it on the payment page, in an e-mail and as a
GiroCode (the EPC QR code that banking apps read).
"""

import io
import re
from dataclasses import dataclass
from typing import Final

import segno

_IBAN: Final = re.compile(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}")
_BIC: Final = re.compile(r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?")
_EPC_NAME_MAX: Final = 70
_EPC_TEXT_MAX: Final = 140
_EPC_AMOUNT_MAX_CENTS: Final = 99_999_999_999
_IBAN_CHECK: Final = 97


def normalise_iban(value: str) -> str:
    """``de89 3704 0044 0532 0130 00`` → ``DE89370400440532013000``."""
    return "".join(value.split()).upper()


def iban_is_valid(iban: str) -> bool:
    """Format and check digits (ISO 13616, modulo 97) of a normalised IBAN."""
    if not _IBAN.fullmatch(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(char, 36)) for char in rearranged)
    return int(digits) % _IBAN_CHECK == 1


def bic_is_valid(bic: str) -> bool:
    return bool(_BIC.fullmatch(bic))


@dataclass(frozen=True, slots=True)
class BankAccount:
    """Who receives the transfer, and where. ``bic`` and ``bank_name`` may be empty."""

    holder: str
    iban: str
    bic: str = ""
    bank_name: str = ""

    @property
    def iban_grouped(self) -> str:
        """The IBAN in groups of four, as people read and type it."""
        return " ".join(self.iban[i : i + 4] for i in range(0, len(self.iban), 4))

    def epc_payload(self, *, amount_cents: int, reference: str) -> str:
        """The text of a GiroCode (EPC069-12, version 002, UTF-8) for a credit transfer."""
        if not 0 < amount_cents <= _EPC_AMOUNT_MAX_CENTS:
            msg = "a GiroCode needs an amount between 0.01 and 999999999.99"
            raise ValueError(msg)
        euros, cents = divmod(amount_cents, 100)
        return "\n".join(
            (
                "BCD",
                "002",
                "1",
                "SCT",
                self.bic,
                self.holder[:_EPC_NAME_MAX],
                self.iban,
                f"EUR{euros}.{cents:02d}",
                "",
                "",
                reference[:_EPC_TEXT_MAX],
            )
        )


def girocode_svg(payload: str) -> bytes:
    """The GiroCode as a standalone SVG: black on white, error correction M as EPC asks."""
    code = segno.make(payload, error="m", micro=False, boost_error=False)
    buffer = io.BytesIO()
    code.save(
        buffer,
        kind="svg",
        scale=4,
        border=4,
        dark="#000",
        light="#fff",
        xmldecl=False,
        omitsize=True,
        svgclass=None,
        lineclass=None,
        title="GiroCode",
    )
    return buffer.getvalue()
