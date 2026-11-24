"""Invoices over HTTP (ADR 0038): listed with the order, downloaded as PDF by staff and customer.

The worker issues the invoice when the order ships; here the test dispatcher does it.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.media.application.services import MediaService
from tests.api.helpers import SHOP, assert_problem
from tests.api.test_sales_api import ADMIN_ORDERS, paid_order
from tests.conftest import Deliver
from tests.inventory_support import stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id


@pytest.fixture
async def painted(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> UUID:
    product: ProductDetails = await shop_product(catalog, media, media_storage, deliver)
    return variant_id(product, "H0", "painted")


async def shipped_order(
    client: AsyncClient,
    staff_client: AsyncClient,
    deliver: Deliver,
    locations: LocationService,
    units: UnitService,
    painted: UUID,
) -> dict[str, Any]:
    await stock_up(locations, units, painted, quantity=2)
    order = await paid_order(client, painted)
    await deliver()
    (listed,) = (await staff_client.get(ADMIN_ORDERS)).json()["items"]
    shipped = await staff_client.post(
        f"{ADMIN_ORDERS}/{listed['id']}/ship", json={"carrier": "DHL", "tracking_number": "0034"}
    )
    assert shipped.status_code == 200, shipped.text
    await deliver()
    return {**order, "id": listed["id"]}


class TestInvoices:
    async def test_staff_and_customer_download_the_invoice(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        deliver: Deliver,
        locations: LocationService,
        units: UnitService,
        painted: UUID,
    ) -> None:
        order = await shipped_order(client, staff_client, deliver, locations, units, painted)

        detail = (await staff_client.get(f"{ADMIN_ORDERS}/{order['id']}")).json()
        (invoice,) = detail["invoices"]
        assert invoice["kind"] == "invoice"
        assert invoice["number"] == "RE-2026-00001"
        assert invoice["filename"] == "Rechnung-RE-2026-00001.pdf"
        assert invoice["total_cents"] == detail["totals"]["total_cents"]

        admin_pdf = await staff_client.get(
            f"{ADMIN_ORDERS}/{order['id']}/invoices/{invoice['id']}/document.pdf"
        )
        assert admin_pdf.status_code == 200
        assert admin_pdf.headers["content-type"] == "application/pdf"
        assert "Rechnung-RE-2026-00001.pdf" in admin_pdf.headers["content-disposition"]
        assert admin_pdf.content.startswith(b"%PDF")

        token = order["public_token"]
        status = (await client.get(f"{SHOP}/orders/{token}")).json()
        assert [i["number"] for i in status["invoices"]] == ["RE-2026-00001"]
        store_pdf = await client.get(f"{SHOP}/orders/{token}/invoices/{invoice['id']}/document.pdf")
        assert store_pdf.status_code == 200
        assert store_pdf.content == admin_pdf.content

    async def test_an_invoice_only_with_its_own_order(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        deliver: Deliver,
        locations: LocationService,
        units: UnitService,
        painted: UUID,
    ) -> None:
        order = await shipped_order(client, staff_client, deliver, locations, units, painted)
        (invoice,) = (await staff_client.get(f"{ADMIN_ORDERS}/{order['id']}")).json()["invoices"]

        assert_problem(
            await staff_client.get(
                f"{ADMIN_ORDERS}/{uuid4()}/invoices/{invoice['id']}/document.pdf"
            ),
            404,
            "invoice_not_found",
        )
        assert_problem(
            await client.get(
                f"{SHOP}/orders/{order['public_token']}/invoices/{uuid4()}/document.pdf"
            ),
            404,
            "invoice_not_found",
        )
        assert_problem(
            await client.get(f"{SHOP}/orders/unbekannt/invoices/{invoice['id']}/document.pdf"),
            404,
            "order_not_found",
        )

    async def test_strangers_do_not_get_in(self, client: AsyncClient) -> None:
        assert_problem(
            await client.get(f"{ADMIN_ORDERS}/{uuid4()}/invoices/{uuid4()}/document.pdf"),
            401,
            "not_authenticated",
        )


class TestDeliveryNotes:
    """The delivery note for the parcel (ADR 0047): any time from payment on, no prices."""

    async def test_staff_print_it_for_a_paid_and_a_shipped_order(
        self,
        client: AsyncClient,
        staff_client: AsyncClient,
        deliver: Deliver,
        locations: LocationService,
        units: UnitService,
        painted: UUID,
    ) -> None:
        order = await shipped_order(client, staff_client, deliver, locations, units, painted)
        note = await staff_client.get(f"{ADMIN_ORDERS}/{order['id']}/delivery-note.pdf")
        assert note.status_code == 200, note.text
        assert note.headers["content-type"] == "application/pdf"
        assert note.content.startswith(b"%PDF")
        assert 'filename="Lieferschein-MB-' in note.headers["content-disposition"]

    async def test_not_for_an_unknown_order_nor_strangers(
        self, client: AsyncClient, staff_client: AsyncClient
    ) -> None:
        assert_problem(
            await staff_client.get(f"{ADMIN_ORDERS}/{uuid4()}/delivery-note.pdf"),
            404,
            "order_not_found",
        )
        assert_problem(
            await client.get(f"{ADMIN_ORDERS}/{uuid4()}/delivery-note.pdf"),
            401,
            "not_authenticated",
        )
