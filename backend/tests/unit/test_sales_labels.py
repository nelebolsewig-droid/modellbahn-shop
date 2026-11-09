"""Shipping labels without a database (ADR 0023): the label's rules, DHL's adapter against a
fake DHL API, the test carrier, the settings and the ``dhl-check`` command."""

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from typer.testing import CliRunner

from modellbahn import cli
from modellbahn.modules.sales.application.ports import LabelRequest
from modellbahn.modules.sales.domain.errors import (
    CarrierRejectedError,
    CarrierUnavailableError,
    InvalidFieldError,
    InvalidOrderStateError,
)
from modellbahn.modules.sales.domain.labels import (
    LabelAddress,
    LabelStatus,
    ShippingLabel,
    ShippingProduct,
    check_weight,
    iso3,
    product_for,
    split_street,
)
from modellbahn.modules.sales.domain.model import OrderStatus
from modellbahn.modules.sales.infrastructure.carriers import (
    DHL_PRODUCTION_URL,
    DHL_SANDBOX_URL,
    SANDBOX_EKP,
    TEST_SHIPPER,
    DhlCarrier,
    NoCarrier,
    TestCarrier,
    build_carrier,
    dhl_carrier,
    shipper_of,
)
from modellbahn.platform.config import CarrierMode, Environment, PaymentProvider, Settings
from tests.unit.test_platform_basics import IMPRINT, OWN_KEY

NOW = datetime(2026, 11, 9, 14, 0, tzinfo=UTC)
API_KEY = "dhl-test-key-0123456789"
EKP = "1234567890"
PDF = b"%PDF-1.4\n1 0 obj << /Type /Page /MediaBox [0 0 283.46 425.2] >> endobj\n%%EOF"

CONSIGNEE = LabelAddress(
    name="Erika Mustermann",
    street="Bahnhofstraße",
    house_number="12a",
    postal_code="38707",
    city="Altenau",
    country="DEU",
)

type Handler = Callable[[httpx.Request], httpx.Response]


def request(product: ShippingProduct = ShippingProduct.PARCEL) -> LabelRequest:
    return LabelRequest(
        reference="MB-2026-00042",
        product=product,
        shipper=TEST_SHIPPER,
        consignee=CONSIGNEE,
        weight_g=850,
    )


def carrier(
    handler: Handler, *, participations: dict[ShippingProduct, str] | None = None
) -> DhlCarrier:
    return DhlCarrier(
        api_key=API_KEY,
        username="gkp-user",
        password="gkp-secret",
        ekp=EKP,
        participations=participations
        or {ShippingProduct.PARCEL: "01", ShippingProduct.PARCEL_INTERNATIONAL: "02"},
        print_format="910-300-400",
        base_url="https://dhl.test/parcel/de/shipping/v2",
        transport=httpx.MockTransport(handler),
    )


def answer(body: object, status: int = 200) -> Handler:
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return handle


def label_answer(number: str = "340434310428091700", document: bytes = PDF) -> dict[str, Any]:
    return {
        "status": {"title": "OK", "statusCode": 200},
        "items": [
            {
                "shipmentNo": number,
                "sstatus": {"title": "OK", "statusCode": 200},
                "label": {"b64": base64.b64encode(document).decode(), "fileFormat": "PDF"},
            }
        ],
    }


REFUSAL: dict[str, Any] = {
    "status": {"title": "Bad Request", "statusCode": 400, "detail": "Weak validation error"},
    "items": [
        {
            "sstatus": {"title": "Bad Request", "statusCode": 400},
            "validationMessages": [
                {
                    "property": "shipments[0].consignee.postalCode",
                    "validationMessage": "Die Postleitzahl ist ungültig.",
                    "validationState": "Error",
                }
            ],
        }
    ],
}


class TestLabelRules:
    @pytest.mark.parametrize(
        ("street", "expected"),
        [
            ("Bahnhofstraße 12a", ("Bahnhofstraße", "12a")),
            ("Am Hang 3-5", ("Am Hang", "3-5")),
            ("Hauptstr. 5 / 2", ("Hauptstr.", "5 / 2")),
            ("Rue de la Paix 10 bis", ("Rue de la Paix", "10 bis")),
            ("Straße des 17. Juni 135", ("Straße des 17. Juni", "135")),
            ("  Kurt-Schumacher-Str.   20 ", ("Kurt-Schumacher-Str.", "20")),
            ("Am Marktplatz", ("Am Marktplatz", "")),
            ("12 Main Street", ("12 Main Street", "")),
        ],
    )
    def test_splits_the_house_number_off(self, street: str, expected: tuple[str, str]) -> None:
        assert split_street(street) == expected

    def test_products_and_countries(self) -> None:
        assert product_for("DE") is ShippingProduct.PARCEL
        assert product_for("AT") is ShippingProduct.PARCEL_INTERNATIONAL
        assert (iso3("DE"), iso3("AT"), iso3("NL")) == ("DEU", "AUT", "NLD")
        with pytest.raises(InvalidFieldError):
            iso3("CH")

    @pytest.mark.parametrize("grams", [9, 31_501, 0, -5])
    def test_weights_dhl_does_not_carry(self, grams: int) -> None:
        with pytest.raises(InvalidFieldError):
            check_weight(grams)

    def test_a_label_is_cancelled_once(self, paid_order: Any) -> None:
        label = ShippingLabel.book(
            order=paid_order,
            carrier="DHL",
            product=ShippingProduct.PARCEL,
            shipment_number=" 340434310428091700 ",
            weight_g=850,
            print_format="910-300-400",
            document=PDF,
            now=NOW,
        )
        assert (label.shipment_number, label.status) == ("340434310428091700", LabelStatus.ACTIVE)
        label.cancel(NOW)
        assert (label.status, label.cancelled_at) == (LabelStatus.CANCELLED, NOW)
        with pytest.raises(InvalidOrderStateError):
            label.cancel(NOW)

    def test_a_label_needs_number_and_document(self, paid_order: Any) -> None:
        for number, document in (("  ", PDF), ("340434", b"")):
            with pytest.raises(InvalidOrderStateError):
                ShippingLabel.book(
                    order=paid_order,
                    carrier="DHL",
                    product=ShippingProduct.PARCEL,
                    shipment_number=number,
                    weight_g=850,
                    print_format="910-300-400",
                    document=document,
                    now=NOW,
                )


@pytest.fixture
def paid_order() -> Any:
    """Just what a label looks at: the order's id and status."""

    class _Order:
        id = "0193a1f2-7c4e-7d1a-9b2c-3d4e5f607182"
        status = OrderStatus.PAID

    return _Order()


class TestDhlBooking:
    async def test_books_a_shipment_and_reads_the_label(self) -> None:
        seen: list[httpx.Request] = []

        def handle(sent: httpx.Request) -> httpx.Response:
            seen.append(sent)
            return httpx.Response(200, json=label_answer())

        booked = await carrier(handle).book(request())
        assert (booked.shipment_number, booked.document) == ("340434310428091700", PDF)
        assert booked.print_format == "910-300-400"
        sent = seen[0]
        assert (sent.method, sent.url.path) == ("POST", "/parcel/de/shipping/v2/orders")
        assert dict(sent.url.params) == {
            "docFormat": "PDF",
            "printFormat": "910-300-400",
            "includeDocs": "include",
            "mustEncode": "false",
        }
        assert sent.headers["dhl-api-key"] == API_KEY
        assert (
            sent.headers["Authorization"] == httpx.BasicAuth("gkp-user", "gkp-secret")._auth_header
        )
        body = json.loads(sent.content)
        assert body["profile"] == "STANDARD_GRUPPENPROFIL"
        shipment = body["shipments"][0]
        assert shipment["product"] == "V01PAK"
        assert shipment["billingNumber"] == f"{EKP}0101"
        assert shipment["refNo"] == "MB-2026-00042"
        assert shipment["details"] == {"weight": {"uom": "g", "value": 850}}
        assert shipment["consignee"] == {
            "name1": "Erika Mustermann",
            "addressStreet": "Bahnhofstraße",
            "addressHouse": "12a",
            "postalCode": "38707",
            "city": "Altenau",
            "country": "DEU",
        }

    def test_the_billing_number_of_each_product(self) -> None:
        dhl = carrier(answer({}))
        assert dhl.billing_number(ShippingProduct.PARCEL) == f"{EKP}0101"
        assert dhl.billing_number(ShippingProduct.PARCEL_INTERNATIONAL) == f"{EKP}5302"

    async def test_a_refusal_carries_dhls_words(self) -> None:
        with pytest.raises(CarrierRejectedError) as refused:
            await carrier(answer(REFUSAL, 400)).book(request())
        assert (
            refused.value.reason
            == "shipments[0].consignee.postalCode: Die Postleitzahl ist ungültig."
        )

    async def test_a_refusal_without_messages_names_the_status(self) -> None:
        unauthorized = {"title": "Unauthorized", "status": 401, "detail": "Invalid credentials"}
        with pytest.raises(CarrierRejectedError) as refused:
            await carrier(answer(unauthorized, 401)).book(request())
        assert refused.value.reason == "Invalid credentials"
        with pytest.raises(CarrierRejectedError) as bare:
            await carrier(lambda _: httpx.Response(403, text="<html>blocked</html>")).book(
                request()
            )
        assert bare.value.reason == "403"

    @pytest.mark.parametrize(
        "handle",
        [
            answer({"status": {"title": "Internal Server Error"}}, 500),
            answer({}, 503),
        ],
    )
    async def test_dhl_down(self, handle: Handler) -> None:
        with pytest.raises(CarrierUnavailableError):
            await carrier(handle).book(request())

    async def test_dhl_unreachable(self) -> None:
        def fail(sent: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out", request=sent)

        with pytest.raises(CarrierUnavailableError):
            await carrier(fail).book(request())

    @pytest.mark.parametrize(
        "body",
        [
            label_answer(number=""),
            label_answer(document=b""),
            {"items": [{"shipmentNo": "340434", "label": {"b64": "not base64!"}}]},
            {"items": []},
        ],
    )
    async def test_an_incomplete_label_is_refused(self, body: dict[str, Any]) -> None:
        with pytest.raises(CarrierRejectedError):
            await carrier(answer(body)).book(request())

    async def test_cancels_the_shipment(self) -> None:
        seen: list[httpx.Request] = []

        def handle(sent: httpx.Request) -> httpx.Response:
            seen.append(sent)
            return httpx.Response(200, json={"status": {"title": "OK", "statusCode": 200}})

        await carrier(handle).cancel("340434310428091700")
        assert seen[0].method == "DELETE"
        assert dict(seen[0].url.params) == {
            "profile": "STANDARD_GRUPPENPROFIL",
            "shipment": "340434310428091700",
        }
        with pytest.raises(CarrierRejectedError):
            await carrier(answer(REFUSAL, 400)).cancel("340434310428091700")

    async def test_validates_without_booking(self) -> None:
        seen: list[httpx.Request] = []

        def handle(sent: httpx.Request) -> httpx.Response:
            seen.append(sent)
            return httpx.Response(200, json={"status": {"title": "OK", "statusCode": 200}})

        dhl = carrier(handle)
        accepted = await dhl.validate(request(ShippingProduct.PARCEL_INTERNATIONAL))
        assert accepted.accepted
        assert dict(seen[0].url.params) == {"validate": "true"}
        assert json.loads(seen[0].content)["shipments"][0]["billingNumber"] == f"{EKP}5302"
        refused = await carrier(answer(REFUSAL, 400)).validate(request())
        assert not refused.accepted
        assert "Postleitzahl" in refused.reason
        await dhl.aclose()


class TestTestCarrier:
    async def test_draws_a_test_label_of_100_by_150_mm(self) -> None:
        test = TestCarrier()
        booked = await test.book(request())
        assert booked.shipment_number.startswith("9")
        assert len(booked.shipment_number) == 12
        assert booked.document.startswith(b"%PDF")
        assert cli._page_size(booked.document) == "Seite 100 x 150 mm"
        await test.cancel(booked.shipment_number)
        assert test.cancelled == [booked.shipment_number]

    async def test_no_carrier_books_nothing(self) -> None:
        none = NoCarrier()
        assert not none.books_labels
        with pytest.raises(CarrierUnavailableError):
            await none.book(request())
        with pytest.raises(CarrierUnavailableError):
            await none.cancel("1")


class TestSettings:
    def test_choose_the_carrier(self) -> None:
        assert isinstance(build_carrier(Settings()), NoCarrier)
        assert isinstance(build_carrier(Settings(dhl_mode=CarrierMode.TEST)), TestCarrier)
        sandbox = build_carrier(
            Settings(dhl_mode=CarrierMode.SANDBOX, dhl_api_key=SecretStr(API_KEY))
        )
        assert isinstance(sandbox, DhlCarrier)
        assert sandbox.base_url.startswith(DHL_SANDBOX_URL)
        # The sandbox is always DHL's test customer, whatever business account is set.
        assert sandbox.billing_number(ShippingProduct.PARCEL) == f"{SANDBOX_EKP}0101"

    def test_production_uses_the_business_account(self) -> None:
        settings = Settings(
            dhl_mode=CarrierMode.PRODUCTION,
            dhl_api_key=SecretStr(API_KEY),
            dhl_username="gkp-user",
            dhl_password=SecretStr("gkp-secret"),
            dhl_ekp="12345 67890",
            dhl_participation_international="02",
        )
        production = dhl_carrier(settings, sandbox=False)
        assert production.base_url.startswith(DHL_PRODUCTION_URL)
        assert production.billing_number(ShippingProduct.PARCEL_INTERNATIONAL) == f"{EKP}5302"
        assert "gkp-secret" not in repr(settings)
        assert API_KEY not in repr(settings)

    def test_dhl_needs_its_keys(self) -> None:
        with pytest.raises(ValidationError, match="MB_DHL_API_KEY"):
            Settings(dhl_mode=CarrierMode.SANDBOX)
        with pytest.raises(ValidationError, match="MB_DHL_USERNAME, MB_DHL_PASSWORD, MB_DHL_EKP"):
            Settings(dhl_mode=CarrierMode.PRODUCTION, dhl_api_key=SecretStr(API_KEY))

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("dhl_ekp", "12345"),
            ("dhl_ekp", "123456789X"),
            ("dhl_participation_national", "1"),
            ("dhl_participation_international", "AB"),
            ("dhl_default_weight_g", 40_000),
        ],
    )
    def test_refuses_malformed_values(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            Settings.model_validate({field: value})

    @pytest.mark.parametrize("mode", [CarrierMode.TEST, CarrierMode.SANDBOX])
    def test_production_refuses_test_labels(self, mode: CarrierMode) -> None:
        with pytest.raises(ValidationError, match="MB_DHL_MODE"):
            Settings(
                environment=Environment.PRODUCTION,
                s3_access_key_id=OWN_KEY,
                payment_provider=PaymentProvider.OFF,
                dhl_mode=mode,
                dhl_api_key=SecretStr(API_KEY),
                **IMPRINT,
            )

    def test_the_shop_is_the_sender(self) -> None:
        shop = shipper_of(Settings(**IMPRINT))
        assert shop == LabelAddress(
            name="Gleiswerk",
            street="Bahnhofstraße",
            house_number="1",
            postal_code="38707",
            city="Altenau",
            country="DEU",
        )
        # Without an imprint only test labels have a sender.
        assert shipper_of(Settings(dhl_mode=CarrierMode.TEST)) == TEST_SHIPPER
        assert shipper_of(Settings()) is None


class TestDhlCheck:
    @pytest.fixture(autouse=True)
    def _environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MB_DHL_API_KEY", API_KEY)
        for name, value in IMPRINT.items():
            monkeypatch.setenv(f"MB_{name.upper()}", value)

    def fake_dhl(self, monkeypatch: pytest.MonkeyPatch, handler: Handler) -> list[httpx.Request]:
        seen: list[httpx.Request] = []

        def handle(sent: httpx.Request) -> httpx.Response:
            seen.append(sent)
            return handler(sent)

        def build(settings: Settings, *, sandbox: bool) -> DhlCarrier:
            built = dhl_carrier(settings, sandbox=sandbox)
            return DhlCarrier(
                api_key=API_KEY,
                username="u",
                password="p",
                ekp=SANDBOX_EKP if sandbox else settings.dhl_ekp,
                participations=dict.fromkeys(ShippingProduct, "01"),
                print_format="910-300-400",
                base_url=built.base_url,
                transport=httpx.MockTransport(handle),
            )

        monkeypatch.setattr(cli, "dhl_carrier", build)
        return seen

    def test_the_sandbox_answers_and_a_test_label_is_measured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def handle(sent: httpx.Request) -> httpx.Response:
            if sent.url.params.get("validate") == "true":
                return httpx.Response(200, json={"status": {"title": "OK", "statusCode": 200}})
            if sent.method == "DELETE":
                return httpx.Response(200, json={"status": {"title": "OK"}})
            return httpx.Response(200, json=label_answer())

        seen = self.fake_dhl(monkeypatch, handle)
        result = CliRunner().invoke(cli.app, ["dhl-check", "--sandbox", "--buchen"])
        assert result.exit_code == 0, result.output
        assert "Sandbox (DHLs Testkunde)" in result.output
        assert "Inland (V01PAK)" in result.output
        assert "EU-Ausland (V53WPAK)" in result.output
        assert "Seite 100 x 150 mm" in result.output
        assert "Testlabel wieder storniert." in result.output
        assert "DHL nimmt beide Sendungen an." in result.output
        assert [r.method for r in seen] == ["POST", "POST", "POST", "DELETE"]
        # The customer number shows only its last digits.
        assert SANDBOX_EKP not in result.output

    def test_a_refusal_is_shown_in_dhls_words(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MB_DHL_USERNAME", "gkp-user")
        monkeypatch.setenv("MB_DHL_PASSWORD", "gkp-secret")
        monkeypatch.setenv("MB_DHL_EKP", EKP)
        self.fake_dhl(monkeypatch, answer(REFUSAL, 400))
        result = CliRunner().invoke(cli.app, ["dhl-check"])
        assert result.exit_code == 1
        assert "Geschäftskundenkonto" in result.output
        assert "DHL antwortet 400: abgelehnt" in result.output
        assert "Die Postleitzahl ist ungültig." in result.output
        assert "gkp-secret" not in result.output

    def test_names_what_is_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        result = CliRunner().invoke(cli.app, ["dhl-check"])
        assert result.exit_code == 1
        assert "MB_DHL_USERNAME, MB_DHL_PASSWORD, MB_DHL_EKP" in result.output
        monkeypatch.delenv("MB_DHL_API_KEY")
        result = CliRunner().invoke(cli.app, ["dhl-check", "--sandbox"])
        assert "MB_DHL_API_KEY" in result.output

    def test_books_only_in_the_sandbox(self) -> None:
        result = CliRunner().invoke(cli.app, ["dhl-check", "--buchen"])
        assert result.exit_code == 1
        assert "nur mit --sandbox" in result.output
