"""Parcel carriers behind the ``Carrier`` port (ADR 0023).

* :class:`DhlCarrier`: DHL's Parcel DE Shipping API (version 2), in DHL's sandbox or with
  the shop's business account.
* :class:`TestCarrier`: draws a label itself, marked as a test, for development.
* :class:`NoCarrier`: no carrier connected; the staff type the shipment number in.

DHL's model of shipments and errors stays in this file and never reaches the domain.
"""

import base64
import binascii
import secrets
from io import BytesIO
from typing import Any, Final

import httpx
import structlog
from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

from modellbahn.modules.sales.application.ports import BookedLabel, Carrier, LabelRequest
from modellbahn.modules.sales.domain.errors import (
    CarrierRejectedError,
    CarrierUnavailableError,
)
from modellbahn.modules.sales.domain.labels import (
    LabelAddress,
    ShippingProduct,
    iso3,
    split_street,
)
from modellbahn.platform.config import CarrierMode, Settings

DHL: Final = "DHL"
DHL_SANDBOX_URL: Final = "https://api-sandbox.dhl.com/parcel/de/shipping/v2"
DHL_PRODUCTION_URL: Final = "https://api-eu.dhl.com/parcel/de/shipping/v2"
# DHL's public test user and customer number of the sandbox.
SANDBOX_USER: Final = "user-valid"
SANDBOX_PASSWORD: Final = "SandboxPasswort2023!"  # noqa: S105 - DHL publishes it for everyone
SANDBOX_EKP: Final = "3333333333"
PROFILE: Final = "STANDARD_GRUPPENPROFIL"
# The procedure of each product: digits 11 and 12 of the billing number.
PROCEDURES: Final = {ShippingProduct.PARCEL: "01", ShippingProduct.PARCEL_INTERNATIONAL: "53"}
_REASON_MAX: Final = 400
_TEST_LABEL_SIZE: Final = (100 * mm, 150 * mm)

_logger = structlog.get_logger(__name__)


class NoCarrier:
    """``MB_DHL_MODE=off``: the shop books no labels."""

    @property
    def name(self) -> str:
        return DHL

    @property
    def books_labels(self) -> bool:
        return False

    async def book(self, request: LabelRequest) -> BookedLabel:
        raise CarrierUnavailableError

    async def cancel(self, shipment_number: str) -> None:
        raise CarrierUnavailableError

    async def aclose(self) -> None:
        return


class TestCarrier:
    """A label drawn by the shop, clearly marked as a test; nothing leaves the server."""

    def __init__(self, *, print_format: str = "100x150mm") -> None:
        self._print_format = print_format
        self.cancelled: list[str] = []

    @property
    def name(self) -> str:
        return DHL

    @property
    def books_labels(self) -> bool:
        return True

    async def book(self, request: LabelRequest) -> BookedLabel:
        # Twelve digits like a DHL Paket number, starting with 9 so it never is a real one.
        number = "9" + "".join(secrets.choice("0123456789") for _ in range(11))
        _logger.info("sales.test_label", order=request.reference, shipment=number)
        return BookedLabel(
            shipment_number=number,
            document=draw_test_label(request, number),
            print_format=self._print_format,
        )

    async def cancel(self, shipment_number: str) -> None:
        self.cancelled.append(shipment_number)

    async def aclose(self) -> None:
        return


def _address_lines(address: LabelAddress) -> list[str]:
    street = f"{address.street} {address.house_number}".strip()
    return [address.name, street, f"{address.postal_code} {address.city}", address.country]


def draw_test_label(request: LabelRequest, number: str) -> bytes:
    """A 100 x 150 mm label in DHL's layout, crossed out as a test."""
    buffer = BytesIO()
    width, height = _TEST_LABEL_SIZE
    canvas = Canvas(buffer, pagesize=_TEST_LABEL_SIZE)
    canvas.setTitle(f"Testlabel {request.reference}")
    margin = 5 * mm
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(margin, height - 12 * mm, "TESTLABEL")
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(width - margin, height - 12 * mm, f"{request.product.value}")
    canvas.drawString(margin, height - 17 * mm, "Nicht versenden: kein echtes DHL-Label")
    canvas.setFont("Helvetica", 6.5)
    y = height - 26 * mm
    canvas.drawString(margin, y, "Absender")
    for line in _address_lines(request.shipper):
        y -= 3.2 * mm
        canvas.drawString(margin, y, line)
    canvas.setFont("Helvetica", 7)
    y -= 8 * mm
    canvas.drawString(margin, y, "Empfänger")
    canvas.setFont("Helvetica-Bold", 11)
    for line in _address_lines(request.consignee):
        y -= 5 * mm
        canvas.drawString(margin, y, line)
    barcode = Code128(number, barHeight=18 * mm, barWidth=0.38 * mm, humanReadable=True)
    barcode.drawOn(canvas, margin, 18 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(
        margin, 10 * mm, f"Bestellung {request.reference} · {request.weight_g / 1000:.2f} kg"
    )
    canvas.setStrokeColorRGB(0.8, 0, 0)
    canvas.setLineWidth(1.2)
    canvas.line(margin, margin, width - margin, height - margin)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _party(address: LabelAddress) -> dict[str, str]:
    party = {
        "name1": address.name[:50],
        "addressStreet": address.street[:50],
        "postalCode": address.postal_code,
        "city": address.city[:40],
        "country": address.country,
    }
    if address.house_number:
        party["addressHouse"] = address.house_number[:10]
    return party


class DhlCarrier:
    """DHL Parcel DE Shipping API v2: one shipment per label, the label as a PDF."""

    def __init__(
        self,
        *,
        api_key: str,
        username: str,
        password: str,
        ekp: str,
        participations: dict[ShippingProduct, str],
        print_format: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._ekp = ekp
        self._participations = participations
        self._print_format = print_format
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "dhl-api-key": api_key,
                "Accept": "application/json",
                "Accept-Language": "de-DE",
            },
            auth=httpx.BasicAuth(username, password),
            timeout=httpx.Timeout(30.0),
            transport=transport,
        )

    @property
    def name(self) -> str:
        return DHL

    @property
    def books_labels(self) -> bool:
        return True

    async def aclose(self) -> None:
        await self._client.aclose()

    def billing_number(self, product: ShippingProduct) -> str:
        """EKP, procedure of the product, participation: 14 digits."""
        return f"{self._ekp}{PROCEDURES[product]}{self._participations[product]}"

    async def book(self, request: LabelRequest) -> BookedLabel:
        shipment = {
            "product": request.product.value,
            "billingNumber": self.billing_number(request.product),
            "refNo": request.reference[:35],
            "shipper": _party(request.shipper),
            "consignee": _party(request.consignee),
            "details": {"weight": {"uom": "g", "value": request.weight_g}},
        }
        answer = await self._call(
            "POST",
            "/orders",
            params={
                "docFormat": "PDF",
                "printFormat": self._print_format,
                "includeDocs": "include",
                "mustEncode": "false",
            },
            json={"profile": PROFILE, "shipments": [shipment]},
        )
        item = _first_item(answer)
        number = str(item.get("shipmentNo") or "")
        label = item.get("label")
        encoded = str(label.get("b64") or "") if isinstance(label, dict) else ""
        try:
            document = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            document = b""
        if not number or not document:
            _logger.error("sales.dhl.label_incomplete", fields=sorted(item))
            raise CarrierRejectedError("DHL hat kein vollständiges Label geschickt.")
        _logger.info("sales.dhl.label", order=request.reference, shipment=number)
        return BookedLabel(
            shipment_number=number, document=document, print_format=self._print_format
        )

    async def cancel(self, shipment_number: str) -> None:
        try:
            await self._call(
                "DELETE", "/orders", params={"profile": PROFILE, "shipment": shipment_number}
            )
        except CarrierRejectedError as error:
            # A label DHL no longer knows (cancelled before, or past) is gone all the same.
            _logger.warning(
                "sales.dhl.cancel_refused", shipment=shipment_number, reason=error.reason
            )
            raise
        _logger.info("sales.dhl.cancelled", shipment=shipment_number)

    async def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            _logger.warning("sales.dhl.unreachable", path=path, error=type(exc).__name__)
            raise CarrierUnavailableError from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        data: dict[str, Any] = body if isinstance(body, dict) else {}
        if response.status_code >= 500:  # noqa: PLR2004
            _logger.error("sales.dhl.error", path=path, status=response.status_code)
            raise CarrierUnavailableError
        if response.status_code >= 400:  # noqa: PLR2004
            reason = _reason(data) or f"{response.status_code}"
            _logger.error(
                "sales.dhl.refused", path=path, status=response.status_code, reason=reason
            )
            raise CarrierRejectedError(reason)
        return data


def _first_item(answer: dict[str, Any]) -> dict[str, Any]:
    items = answer.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}


def _reason(data: dict[str, Any]) -> str:
    """DHL's words: the validation messages of the shipment, else the status detail."""
    messages: list[str] = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        for message in item.get("validationMessages") or []:
            if isinstance(message, dict):
                field = message.get("property")
                text = str(message.get("validationMessage") or "").strip()
                if text:
                    messages.append(f"{field}: {text}" if field else text)
        status = item.get("sstatus")
        if not messages and isinstance(status, dict) and status.get("detail"):
            messages.append(str(status["detail"]))
    if not messages:
        status = data.get("status")
        detail = data.get("detail") or (status.get("detail") if isinstance(status, dict) else "")
        title = data.get("title") or (status.get("title") if isinstance(status, dict) else "")
        messages.append(str(detail or title or ""))
    return " · ".join(m for m in messages if m)[:_REASON_MAX]


def build_carrier(settings: Settings) -> Carrier:
    """The configured carrier (``MB_DHL_MODE``)."""
    participations = {
        ShippingProduct.PARCEL: settings.dhl_participation_national,
        ShippingProduct.PARCEL_INTERNATIONAL: settings.dhl_participation_international,
    }
    match settings.dhl_mode:
        case CarrierMode.OFF:
            return NoCarrier()
        case CarrierMode.TEST:
            return TestCarrier()
        case CarrierMode.SANDBOX:
            return DhlCarrier(
                api_key=settings.dhl_api_key.get_secret_value(),
                username=settings.dhl_username or SANDBOX_USER,
                password=settings.dhl_password.get_secret_value() or SANDBOX_PASSWORD,
                ekp=settings.dhl_ekp or SANDBOX_EKP,
                participations=participations,
                print_format=settings.dhl_print_format,
                base_url=settings.dhl_api_url or DHL_SANDBOX_URL,
            )
        case CarrierMode.PRODUCTION:
            return DhlCarrier(
                api_key=settings.dhl_api_key.get_secret_value(),
                username=settings.dhl_username,
                password=settings.dhl_password.get_secret_value(),
                ekp=settings.dhl_ekp,
                participations=participations,
                print_format=settings.dhl_print_format,
                base_url=settings.dhl_api_url or DHL_PRODUCTION_URL,
            )


TEST_SHIPPER: Final = LabelAddress(
    name="Testabsender",
    street="Musterstraße",
    house_number="1",
    postal_code="12345",
    city="Musterstadt",
    country="DEU",
)
"""Who sends test labels while the imprint is still empty (development only)."""


def shipper_of(settings: Settings) -> LabelAddress | None:
    """The shop as the sender: the provider of the imprint, in Germany.

    None without a complete imprint, except for test labels: a real label needs the real
    sender.
    """
    imprint = settings.imprint
    if not imprint.is_complete:
        return TEST_SHIPPER if settings.dhl_mode is CarrierMode.TEST else None
    street, house = split_street(imprint.street)
    return LabelAddress(
        name=imprint.company or imprint.owner,
        street=street,
        house_number=house,
        postal_code=imprint.postal_code,
        city=imprint.city,
        country=iso3("DE"),
    )
