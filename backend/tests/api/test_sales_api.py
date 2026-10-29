"""Sales over HTTP: cart cookie, checkout with Idempotency-Key, payment, account, admin area."""

from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient, Response

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.api.deps import CHECKOUT_RATE_LIMITER
from modellbahn.platform.mail import InMemoryMailer
from modellbahn.platform.ratelimit import RateLimiter
from tests.api.helpers import (
    EMAIL,
    SHOP,
    STORE,
    ClientFactory,
    assert_problem,
    cookie_attributes,
)
from tests.conftest import Deliver
from tests.inventory_support import stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id
from tests.support import mails_to

ADMIN_ORDERS = "/api/v1/admin/orders"
EU_MEMBER_STATES: Final = 27
INVENTORY = "/api/v1/admin/inventory"
ADDRESS = {
    "recipient": "Erika Mustermann",
    "street": "Bahnhofstraße 12",
    "postal_code": "38707",
    "city": "Altenau",
    "country_code": "DE",
}


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    return await shop_product(catalog, media, media_storage, deliver)


@pytest.fixture
def painted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "painted")


async def pick_via_api(staff: AsyncClient, order_id: str) -> None:
    """Scan every reserved unit of the order in pick mode, as the packer's phone does."""
    pick_list = (await staff.get(f"{INVENTORY}/orders/{order_id}/pick-list")).json()
    for item in pick_list["items"]:
        if item["state"] == "reserved":
            answer = await staff.post(
                f"{INVENTORY}/scans",
                json={
                    "scan_id": str(uuid4()),
                    "raw": item["unit_code"],
                    "mode": "pick",
                    "source": "scanner",
                    "context": {"order_id": order_id},
                },
            )
            assert answer.json()["outcome"] == "applied", answer.text
    final = (await staff.get(f"{INVENTORY}/orders/{order_id}/pick-list")).json()
    assert final["complete"], str(final["items"])


async def put_line(client: AsyncClient, variant: UUID, quantity: int) -> Response:
    return await client.put(f"{SHOP}/cart/lines/{variant}", json={"quantity": quantity})


async def checkout(client: AsyncClient, *, key: str | None = None, **body: Any) -> Response:
    total = (await client.get(f"{SHOP}/cart")).json()["totals"]["total_cents"]
    payload = {
        "expected_total_cents": total,
        "email": "gast@example.de",
        "address": ADDRESS,
        **body,
    }
    return await client.post(
        f"{SHOP}/checkouts", json=payload, headers={"Idempotency-Key": key or str(uuid4())}
    )


async def pay(client: AsyncClient, token: str, method: str, key: str | None = None) -> Response:
    return await client.post(
        f"{SHOP}/orders/{token}/payments",
        json={"method": method},
        headers={"Idempotency-Key": key or str(uuid4())},
    )


async def paid_order(client: AsyncClient, painted: UUID) -> dict[str, Any]:
    await put_line(client, painted, 2)
    order = (await checkout(client)).json()
    response = await pay(client, order["public_token"], "succeeds")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


class TestCart:
    async def test_the_first_line_starts_a_cart_and_sets_its_cookie(
        self, client: AsyncClient, painted: UUID
    ) -> None:
        empty = await client.get(f"{SHOP}/cart")
        assert empty.status_code == 200
        assert empty.headers["cache-control"] == "no-store"
        assert empty.json()["lines"] == []
        countries = empty.json()["countries"]
        assert len(countries) == EU_MEMBER_STATES
        assert countries[0] == {
            "code": "DE",
            "name": "Deutschland",
            "rate_cents": 590,
            "free_from_cents": None,
        }
        assert {
            "code": "AT",
            "name": "Österreich",
            "rate_cents": 1690,
            "free_from_cents": None,
        } in (countries)

        response = await put_line(client, painted, 2)
        assert response.status_code == 200, response.text
        cookie = cookie_attributes(response, "mb_cart")
        assert {"httponly", "secure", "path"} <= set(cookie)
        assert cookie["samesite"].lower() == "lax"
        body = response.json()
        assert body["item_count"] == 2
        line = body["lines"][0]
        assert (line["title"] if "title" in line else line["product_name"]) == "Stellwerk Altenau"
        assert (line["scale_code"], line["finish_name"], line["line_total_cents"]) == (
            "H0",
            "Fertigmodell",
            9980,
        )
        assert line["image"]["renditions"]

        # The cookie of this client names the cart from now on; no new cookie is set.
        again = await put_line(client, painted, 3)
        assert "mb_cart" not in again.headers.get("set-cookie", "")
        assert (await client.get(f"{SHOP}/cart")).json()["item_count"] == 3
        removed = await client.delete(f"{SHOP}/cart/lines/{painted}")
        assert removed.json()["lines"] == []

    async def test_a_strange_cookie_is_no_cart(self, client: AsyncClient) -> None:
        client.cookies.set("mb_cart", "kein-warenkorb")
        assert (await client.get(f"{SHOP}/cart")).json()["lines"] == []

    async def test_what_cannot_be_bought_stays_out(
        self, client: AsyncClient, painted: UUID
    ) -> None:
        assert_problem(await put_line(client, uuid4(), 1), 409, "variant_unavailable")
        assert_problem(await put_line(client, painted, 100), 422, "validation_failed")


class TestCheckout:
    async def test_a_guest_orders_once_per_key(self, client: AsyncClient, painted: UUID) -> None:
        await put_line(client, painted, 1)
        key = str(uuid4())
        first = await checkout(client, key=key)
        assert first.status_code == 201, first.text
        order = first.json()
        assert order["status"] == "pending_payment"
        assert order["number"].startswith("MB-")
        assert order["totals"] == {
            "subtotal_cents": 4990,
            "shipping_cents": 590,
            "total_cents": 5580,
            "tax_cents": 891,
        }
        assert order["payment_due_at"] is not None
        assert "Idempotent-Replayed" not in first.headers
        assert (await client.get(f"{SHOP}/cart")).json()["lines"] == []

        payload = {"expected_total_cents": 5580, "email": "gast@example.de", "address": ADDRESS}
        replay = await client.post(
            f"{SHOP}/checkouts", json=payload, headers={"Idempotency-Key": key}
        )
        assert replay.status_code == 201
        assert replay.headers["idempotent-replayed"] == "true"
        assert replay.json()["number"] == order["number"]

    async def test_the_key_is_required(self, client: AsyncClient, painted: UUID) -> None:
        await put_line(client, painted, 1)
        response = await client.post(
            f"{SHOP}/checkouts",
            json={"expected_total_cents": 5580, "email": "a@b.de", "address": ADDRESS},
        )
        assert_problem(response, 422, "validation_failed")

    async def test_refusals(
        self, client: AsyncClient, catalog: CatalogService, painted: UUID
    ) -> None:
        assert_problem(await checkout(client), 409, "cart_empty")
        await put_line(client, painted, 1)
        await catalog.change_variant(painted, expected_version=None, price_cents=3990)
        stale = await client.post(
            f"{SHOP}/checkouts",
            json={"expected_total_cents": 5580, "email": "a@b.de", "address": ADDRESS},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert_problem(stale, 409, "price_changed")
        body = assert_problem(await checkout(client, email="kein-mail"), 422, "validation_failed")
        assert body["errors"][0]["field"] == "email"
        wrong_zip = {**ADDRESS, "postal_code": "123"}
        body = assert_problem(await checkout(client, address=wrong_zip), 422, "validation_failed")
        assert body["errors"][0]["field"] == "postal_code"

    async def test_checkouts_are_rate_limited(
        self, client: AsyncClient, app: Any, painted: UUID
    ) -> None:
        setattr(app.state, CHECKOUT_RATE_LIMITER, RateLimiter(limit=1, window_seconds=600))
        assert_problem(await checkout(client), 409, "cart_empty")
        response = await checkout(client)
        assert_problem(response, 429, "too_many_requests")
        assert int(response.headers["retry-after"]) > 0


class TestPayment:
    async def test_status_page_and_payment(
        self,
        client: AsyncClient,
        make_client: ClientFactory,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
    ) -> None:
        await put_line(client, painted, 1)
        order = (await checkout(client)).json()
        token = order["public_token"]
        # The status link works without any cookie: guests have nothing else.
        async with make_client() as stranger:
            status = await stranger.get(f"{SHOP}/orders/{token}")
            assert status.status_code == 200
            assert status.headers["cache-control"] == "no-store"
            assert status.json()["number"] == order["number"]
            assert_problem(await stranger.get(f"{SHOP}/orders/unbekannt"), 404, "order_not_found")

        declined = await pay(client, token, "declined")
        assert declined.status_code == 200
        assert declined.json()["status"] == "pending_payment"
        assert declined.json()["payments"][0]["failure_code"] == "declined"

        unavailable = await pay(client, token, "fails")
        assert_problem(unavailable, 503, "payment_unavailable")
        assert unavailable.headers["retry-after"] == "30"

        key = str(uuid4())
        paid = await pay(client, token, "succeeds", key)
        assert paid.json()["status"] == "paid"
        replay = await pay(client, token, "succeeds", key)
        assert replay.headers["idempotent-replayed"] == "true"
        assert_problem(await pay(client, token, "succeeds"), 409, "order_not_payable")
        assert_problem(await pay(client, token, "declined", key), 409, "idempotency_key_reused")
        assert_problem(await pay(client, token, "bar"), 422, "validation_failed")

        await deliver()
        assert [m.subject for m in mails_to(mailer, "gast@example.de")] == [
            f"Bestellung {order['number']} eingegangen",
            f"Zahlung eingegangen: Bestellung {order['number']}",
        ]


class TestAccount:
    async def test_orders_and_address_book_need_a_login(self, client: AsyncClient) -> None:
        for path in ("orders", "addresses"):
            assert_problem(await client.get(f"{STORE}/{path}"), 401, "not_authenticated")

    async def test_a_customer_orders_and_sees_the_history(
        self, client: AsyncClient, customer: dict[str, Any], painted: UUID
    ) -> None:
        book = await client.post(f"{STORE}/addresses", json={**ADDRESS, "label": "Zuhause"})
        assert book.status_code == 201, book.text
        (entry,) = book.json()
        assert (entry["label"], entry["is_default"], entry["country_name"]) == (
            "Zuhause",
            True,
            "Deutschland",
        )

        await put_line(client, painted, 1)
        response = await checkout(client, email=None, address=None, address_id=entry["id"])
        assert response.status_code == 201, response.text
        order = response.json()
        assert order["email"] == EMAIL

        history = await client.get(f"{STORE}/orders")
        assert history.status_code == 200
        (summary,) = history.json()["items"]
        assert (summary["number"], summary["guest"], summary["item_count"]) == (
            order["number"],
            False,
            1,
        )
        detail = await client.get(f"{STORE}/orders/{order['number']}")
        assert detail.json()["shipping_address"]["city"] == "Altenau"
        assert_problem(await client.get(f"{STORE}/orders/MB-2026-99999"), 404, "order_not_found")

    async def test_address_book(self, client: AsyncClient, customer: dict[str, Any]) -> None:
        first = (await client.post(f"{STORE}/addresses", json=ADDRESS)).json()[0]
        book = (
            await client.post(
                f"{STORE}/addresses",
                json={
                    **ADDRESS,
                    "city": "Innsbruck",
                    "postal_code": "6020",
                    "country_code": "AT",
                    "is_default": True,
                },
            )
        ).json()
        assert [(a["city"], a["is_default"]) for a in book] == [
            ("Innsbruck", True),
            ("Altenau", False),
        ]
        changed = await client.patch(
            f"{STORE}/addresses/{first['id']}", json={"label": "Werkstatt", "is_default": True}
        )
        assert [(a["label"], a["is_default"]) for a in changed.json()] == [
            ("Werkstatt", True),
            ("", False),
        ]
        moved = await client.patch(
            f"{STORE}/addresses/{first['id']}", json={"address": {**ADDRESS, "city": "Goslar"}}
        )
        assert moved.json()[0]["city"] == "Goslar"
        remaining = await client.delete(f"{STORE}/addresses/{first['id']}")
        assert [(a["city"], a["is_default"]) for a in remaining.json()] == [("Innsbruck", True)]
        assert_problem(
            await client.delete(f"{STORE}/addresses/{first['id']}"), 404, "address_not_found"
        )
        invalid = await client.post(f"{STORE}/addresses", json={**ADDRESS, "country_code": "CH"})
        assert (
            assert_problem(invalid, 422, "validation_failed")["errors"][0]["code"] == "not_shipped"
        )


class TestAdmin:
    async def test_staff_ship_and_cancel(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        deliver: Deliver,
        mailer: InMemoryMailer,
        painted: UUID,
        locations: LocationService,
        units: UnitService,
    ) -> None:
        await stock_up(locations, units, painted, quantity=2)
        order = await paid_order(client, painted)
        await put_line(client, painted, 1)
        open_order = (await checkout(client, email="otto@example.de")).json()

        listing = await staff_client.get(ADMIN_ORDERS)
        assert [o["number"] for o in listing.json()["items"]] == [
            open_order["number"],
            order["number"],
        ]
        paid_only = await staff_client.get(ADMIN_ORDERS, params={"status": ["paid"]})
        assert [o["number"] for o in paid_only.json()["items"]] == [order["number"]]
        found = await staff_client.get(ADMIN_ORDERS, params={"q": "otto"})
        (summary,) = found.json()["items"]
        assert summary["guest"] is True

        detail = (await staff_client.get(f"{ADMIN_ORDERS}/{summary['id']}")).json()
        assert detail["email"] == "otto@example.de"
        assert detail["customer_account_id"] is None

        paid_id = listing.json()["items"][1]["id"]
        assert_problem(
            await staff_client.post(f"{ADMIN_ORDERS}/{paid_id}/ship", json={}),
            409,
            "order_not_picked",
        )
        await deliver()
        await pick_via_api(staff_client, paid_id)
        shipped = await staff_client.post(
            f"{ADMIN_ORDERS}/{paid_id}/ship", json={"carrier": "DHL", "tracking_number": "0034"}
        )
        assert shipped.json()["status"] == "shipped"
        assert_problem(
            await staff_client.post(f"{ADMIN_ORDERS}/{paid_id}/cancel", json={}),
            409,
            "invalid_order_state",
        )
        cancelled = await staff_client.post(
            f"{ADMIN_ORDERS}/{summary['id']}/cancel", json={"note": "Testbestellung"}
        )
        assert (cancelled.json()["status"], cancelled.json()["cancel_note"]) == (
            "cancelled",
            "Testbestellung",
        )
        assert_problem(await staff_client.get(f"{ADMIN_ORDERS}/{uuid4()}"), 404, "order_not_found")

        await deliver()
        assert mails_to(mailer, "gast@example.de")[-1].subject.endswith("ist unterwegs")
        assert "storniert" in mails_to(mailer, "otto@example.de")[-1].subject

    async def test_packers_pick_and_ship_but_do_not_cancel(
        self,
        client: AsyncClient,
        packer_client: AsyncClient,
        painted: UUID,
        deliver: Deliver,
        locations: LocationService,
        units: UnitService,
    ) -> None:
        await stock_up(locations, units, painted, quantity=2)
        await paid_order(client, painted)
        await deliver()
        (summary,) = (await packer_client.get(ADMIN_ORDERS)).json()["items"]
        await pick_via_api(packer_client, summary["id"])
        assert_problem(
            await packer_client.post(f"{ADMIN_ORDERS}/{summary['id']}/cancel", json={}),
            403,
            "insufficient_role",
        )
        shipped = await packer_client.post(f"{ADMIN_ORDERS}/{summary['id']}/ship", json={})
        assert shipped.json()["status"] == "shipped"

    async def test_customers_do_not_get_in(
        self, client: AsyncClient, customer: dict[str, Any]
    ) -> None:
        assert_problem(await client.get(ADMIN_ORDERS), 401, "not_authenticated")
