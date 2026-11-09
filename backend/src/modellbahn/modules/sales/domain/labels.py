"""Shipping labels booked with the carrier for a paid order (ADR 0023).

A label is booked once the order is paid and the parcel packed: the carrier answers with
its shipment number and the label as a PDF. The number goes into the dispatch (and with
it into the customer's e-mail); a label booked by mistake is cancelled at the carrier
while the parcel has not left. An order has at most one label in force.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.sales.domain.errors import InvalidFieldError, InvalidOrderStateError
from modellbahn.modules.sales.domain.model import Order, OrderStatus, PostalAddress
from modellbahn.platform.ids import new_id

LABEL_WEIGHT_MIN_G: Final = 10
LABEL_WEIGHT_MAX_G: Final = 31_500
"""DHL Paket carries up to 31.5 kg."""

# ISO 3166 alpha-3 codes of the countries the shop ships to; DHL's API wants these.
ISO3: Final = {
    "DE": "DEU",
    "AT": "AUT",
    "BE": "BEL",
    "BG": "BGR",
    "CY": "CYP",
    "CZ": "CZE",
    "DK": "DNK",
    "EE": "EST",
    "ES": "ESP",
    "FI": "FIN",
    "FR": "FRA",
    "GR": "GRC",
    "HR": "HRV",
    "HU": "HUN",
    "IE": "IRL",
    "IT": "ITA",
    "LT": "LTU",
    "LU": "LUX",
    "LV": "LVA",
    "MT": "MLT",
    "NL": "NLD",
    "PL": "POL",
    "PT": "PRT",
    "RO": "ROU",
    "SE": "SWE",
    "SI": "SVN",
    "SK": "SVK",
}

# "Bahnhofstraße 12a", "Am Hang 3-5", "Rue de la Paix 10 bis": the house number at the end.
_HOUSE_NUMBER: Final = re.compile(
    r"^(?P<street>.*?\D)\s*(?P<house>\d+\s*[a-zA-Z]?(?:\s*[-/]\s*\d+\s*[a-zA-Z]?)?(?:\s+bis)?)$"
)


class ShippingProduct(StrEnum):
    """What the carrier sells; the code is DHL's product key."""

    PARCEL = "V01PAK"
    """DHL Paket within Germany."""
    PARCEL_INTERNATIONAL = "V53WPAK"
    """DHL Paket International, for the other EU countries."""


def product_for(country_code: str) -> ShippingProduct:
    """DHL Paket at home, DHL Paket International abroad."""
    return ShippingProduct.PARCEL if country_code == "DE" else ShippingProduct.PARCEL_INTERNATIONAL


def iso3(country_code: str) -> str:
    try:
        return ISO3[country_code]
    except KeyError:
        raise InvalidFieldError(
            "country_code", "not_shipped", "no label for this country"
        ) from None


def split_street(street: str) -> tuple[str, str]:
    """Street and house number, as the carrier wants them; all in the street if unclear."""
    match = _HOUSE_NUMBER.match(" ".join(street.split()))
    if match is None:
        return " ".join(street.split()), ""
    return match["street"].strip(), " ".join(match["house"].split())


class LabelStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class LabelAddress:
    """An address as it goes on the label: one line each, the country as ISO alpha-3."""

    name: str
    street: str
    house_number: str
    postal_code: str
    city: str
    country: str
    """ISO 3166 alpha-3, e.g. ``DEU``."""

    @classmethod
    def of(cls, address: PostalAddress) -> "LabelAddress":
        street, house = split_street(address.street)
        return cls(
            name=address.recipient,
            street=street,
            house_number=house,
            postal_code=address.postal_code,
            city=address.city,
            country=iso3(address.country_code),
        )


def check_weight(weight_g: int) -> int:
    if not LABEL_WEIGHT_MIN_G <= weight_g <= LABEL_WEIGHT_MAX_G:
        raise InvalidFieldError(
            "weight_g",
            "out_of_range",
            f"between {LABEL_WEIGHT_MIN_G} g and {LABEL_WEIGHT_MAX_G} g",
        )
    return weight_g


def check_labelable(order: Order) -> None:
    """Labels are for paid orders that have not left yet."""
    if order.status is not OrderStatus.PAID:
        msg = f"an order that is {order.status} gets no shipping label"
        raise InvalidOrderStateError(msg)


@dataclass(eq=False)
class ShippingLabel:
    """A label the carrier booked for an order; ``document`` is the PDF to print."""

    id: UUID
    order_id: UUID
    carrier: str
    product: ShippingProduct
    shipment_number: str
    weight_g: int
    print_format: str
    document: bytes
    status: LabelStatus
    created_at: datetime
    cancelled_at: datetime | None = None

    @classmethod
    def book(
        cls,
        *,
        order: Order,
        carrier: str,
        product: ShippingProduct,
        shipment_number: str,
        weight_g: int,
        print_format: str,
        document: bytes,
        now: datetime,
    ) -> "ShippingLabel":
        check_labelable(order)
        if not shipment_number.strip() or not document:
            msg = "a label needs the carrier's shipment number and its document"
            raise InvalidOrderStateError(msg)
        return cls(
            id=new_id(),
            order_id=order.id,
            carrier=carrier,
            product=product,
            shipment_number=shipment_number.strip(),
            weight_g=check_weight(weight_g),
            print_format=print_format,
            document=document,
            status=LabelStatus.ACTIVE,
            created_at=now,
        )

    @property
    def is_active(self) -> bool:
        return self.status is LabelStatus.ACTIVE

    def cancel(self, now: datetime) -> None:
        """The carrier dropped the label: it is no longer in force."""
        if not self.is_active:
            msg = "the label was cancelled already"
            raise InvalidOrderStateError(msg)
        self.status = LabelStatus.CANCELLED
        self.cancelled_at = now
