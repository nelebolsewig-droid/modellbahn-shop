"""CSRF guard, problem details, request ids, health probes and the OpenAPI document."""

from typing import Any

import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from modellbahn.main import create_app
from modellbahn.platform.config import Settings
from tests.api.helpers import EMAIL, PASSWORD, STORE, ClientFactory, assert_problem
from tests.conftest import PUBLIC_BASE_URL


class TestCsrfGuard:
    async def test_unsafe_requests_need_the_header(self, make_client: ClientFactory) -> None:
        async with make_client(csrf=False) as client:
            for method, path in [("POST", "/session"), ("PATCH", "/me"), ("DELETE", "/session")]:
                response = await client.request(method, f"{STORE}{path}", json={})
                assert_problem(response, 403, "csrf_header_missing")
            wrong_value = await client.post(
                f"{STORE}/register", json={}, headers={"X-Modellbahn-Client": "evil"}
            )
            assert_problem(wrong_value, 403, "csrf_header_missing")
            # Safe methods pass.
            assert_problem(await client.get(f"{STORE}/me"), 401, "not_authenticated")

    async def test_bodies_must_be_json(self, client: AsyncClient) -> None:
        form = await client.post(f"{STORE}/session", data={"email": EMAIL, "password": PASSWORD})
        assert_problem(form, 415, "unsupported_media_type")
        text = await client.post(
            f"{STORE}/session",
            content=b'{"email": "a@example.com"}',
            headers={"content-type": "text/plain"},
        )
        assert_problem(text, 415, "unsupported_media_type")
        # Structured JSON media types are JSON, too.
        merge_patch = await client.post(
            f"{STORE}/session",
            content=b'{"email": "a@example.com", "password": "x"}',
            headers={"content-type": "application/merge-patch+json"},
        )
        assert_problem(merge_patch, 401, "invalid_credentials")


class TestProblems:
    async def test_framework_errors_are_problems(self, client: AsyncClient) -> None:
        assert_problem(await client.get("/api/v1/nothing-here"), 404, "not_found")
        assert_problem(await client.put(f"{STORE}/me", json={}), 405, "method_not_allowed")
        broken = await client.post(
            f"{STORE}/session", content=b"{not json", headers={"content-type": "application/json"}
        )
        body = assert_problem(broken, 422, "validation_failed")
        assert body["errors"][0]["code"] == "invalid_json"

    async def test_unexpected_errors_reveal_nothing(self, settings: Settings) -> None:
        app = create_app(settings)

        @app.get("/api/v1/boom")
        async def boom() -> None:
            raise RuntimeError("secret internals")

        async with (
            LifespanManager(app),
            AsyncClient(transport=ASGITransport(app=app), base_url=PUBLIC_BASE_URL) as client,
        ):
            response = await client.get("/api/v1/boom")
        body = assert_problem(response, 500, "internal_error")
        assert "secret" not in response.text
        assert body["detail"] == "An unexpected error occurred."
        assert response.headers["x-request-id"]

    async def test_request_ids(self, client: AsyncClient) -> None:
        echoed = await client.get("/healthz", headers={"X-Request-ID": "abc-123"})
        assert echoed.headers["x-request-id"] == "abc-123"
        replaced = await client.get("/healthz", headers={"X-Request-ID": "not <allowed>"})
        assert replaced.headers["x-request-id"] != "not <allowed>"
        assert len(replaced.headers["x-request-id"]) == 32


class TestHealth:
    async def test_probes(self, client: AsyncClient) -> None:
        assert (await client.get("/healthz")).json() == {"status": "ok"}
        assert (await client.get("/readyz")).json() == {"status": "ok"}

    async def test_not_ready_without_database(self, settings: Settings) -> None:
        unreachable = settings.model_copy(
            update={"database_url": "postgresql+asyncpg://nobody:secret@127.0.0.1:1/nothing"}
        )
        app = create_app(unreachable)
        # Startup waits a few seconds for the realtime listener, then goes on without it.
        async with (
            LifespanManager(app, startup_timeout=15),
            AsyncClient(transport=ASGITransport(app=app), base_url=PUBLIC_BASE_URL) as client,
        ):
            assert (await client.get("/healthz")).status_code == 200
            assert_problem(await client.get("/readyz"), 503, "database_unavailable")


EXPECTED_OPERATIONS = {
    ("POST", "/api/v1/store/account/register"): ("registerCustomer", "store-account"),
    ("POST", "/api/v1/store/account/email-verification"): ("verifyCustomerEmail", "store-account"),
    ("POST", "/api/v1/store/account/email-verification/resend"): (
        "resendVerificationEmail",
        "store-account",
    ),
    ("POST", "/api/v1/store/account/session"): ("loginCustomer", "store-account"),
    ("DELETE", "/api/v1/store/account/session"): ("logoutCustomer", "store-account"),
    ("GET", "/api/v1/store/account/me"): ("getCustomerAccount", "store-account"),
    ("PATCH", "/api/v1/store/account/me"): ("updateCustomerAccount", "store-account"),
    ("POST", "/api/v1/store/account/password"): ("changeCustomerPassword", "store-account"),
    ("POST", "/api/v1/store/account/password-reset"): ("requestPasswordReset", "store-account"),
    ("POST", "/api/v1/store/account/password-reset/confirm"): (
        "confirmPasswordReset",
        "store-account",
    ),
    ("POST", "/api/v1/store/account/me/delete"): ("deleteCustomerAccount", "store-account"),
    ("POST", "/api/v1/admin/auth/session"): ("staffLogin", "admin-auth"),
    ("DELETE", "/api/v1/admin/auth/session"): ("staffLogout", "admin-auth"),
    ("GET", "/api/v1/admin/auth/me"): ("getStaffAccount", "admin-auth"),
    ("POST", "/api/v1/admin/auth/password"): ("changeStaffPassword", "admin-auth"),
    ("GET", "/api/v1/admin/events"): ("streamAdminEvents", "admin-realtime"),
    ("GET", "/api/v1/store/navigation"): ("getStoreNavigation", "store-catalog"),
    ("GET", "/api/v1/store/products"): ("listStoreProducts", "store-catalog"),
    ("GET", "/api/v1/store/products/{slug}"): ("getStoreProduct", "store-catalog"),
    ("GET", "/api/v1/admin/catalog/references"): ("getCatalogReferences", "admin-catalog"),
    ("GET", "/api/v1/admin/categories"): ("listCategories", "admin-catalog"),
    ("POST", "/api/v1/admin/categories"): ("createCategory", "admin-catalog"),
    ("PATCH", "/api/v1/admin/categories/{category_id}"): ("updateCategory", "admin-catalog"),
    ("GET", "/api/v1/admin/scales"): ("listScales", "admin-catalog"),
    ("POST", "/api/v1/admin/scales"): ("createScale", "admin-catalog"),
    ("PATCH", "/api/v1/admin/scales/{code}"): ("updateScale", "admin-catalog"),
    ("DELETE", "/api/v1/admin/scales/{code}"): ("deleteScale", "admin-catalog"),
    ("GET", "/api/v1/admin/products"): ("listProducts", "admin-catalog"),
    ("POST", "/api/v1/admin/products"): ("createProduct", "admin-catalog"),
    ("POST", "/api/v1/admin/catalog/quick-entries"): ("createQuickEntry", "admin-catalog"),
    ("POST", "/api/v1/admin/catalog/publish-ready"): ("publishReadyProducts", "admin-catalog"),
    ("GET", "/api/v1/admin/products/{product_id}"): ("getProduct", "admin-catalog"),
    ("PATCH", "/api/v1/admin/products/{product_id}"): ("updateProduct", "admin-catalog"),
    ("DELETE", "/api/v1/admin/products/{product_id}"): ("deleteProduct", "admin-catalog"),
    ("POST", "/api/v1/admin/products/{product_id}/publish"): ("publishProduct", "admin-catalog"),
    ("POST", "/api/v1/admin/products/{product_id}/archive"): ("archiveProduct", "admin-catalog"),
    ("POST", "/api/v1/admin/products/{product_id}/scales"): ("addProductScale", "admin-catalog"),
    ("PATCH", "/api/v1/admin/product-scales/{product_scale_id}"): (
        "updateProductScale",
        "admin-catalog",
    ),
    ("DELETE", "/api/v1/admin/product-scales/{product_scale_id}"): (
        "deleteProductScale",
        "admin-catalog",
    ),
    ("POST", "/api/v1/admin/product-scales/{product_scale_id}/variants"): (
        "addVariant",
        "admin-catalog",
    ),
    ("PATCH", "/api/v1/admin/variants/{variant_id}"): ("updateVariant", "admin-catalog"),
    ("DELETE", "/api/v1/admin/variants/{variant_id}"): ("deleteVariant", "admin-catalog"),
    ("POST", "/api/v1/admin/products/{product_id}/media"): (
        "attachProductImage",
        "admin-catalog",
    ),
    ("PUT", "/api/v1/admin/products/{product_id}/media"): (
        "arrangeProductGallery",
        "admin-catalog",
    ),
    ("POST", "/api/v1/admin/media/uploads"): ("requestMediaUpload", "admin-media"),
    ("POST", "/api/v1/admin/media/{asset_id}/complete"): ("completeMediaUpload", "admin-media"),
    ("GET", "/api/v1/admin/media/{asset_id}"): ("getMediaAsset", "admin-media"),
    ("POST", "/api/v1/admin/media/{asset_id}/reprocess"): ("reprocessMediaAsset", "admin-media"),
    ("DELETE", "/api/v1/admin/media/{asset_id}"): ("deleteMediaAsset", "admin-media"),
    ("GET", "/api/v1/store/cart"): ("getCart", "store-sales"),
    ("PUT", "/api/v1/store/cart/lines/{variant_id}"): ("setCartLine", "store-sales"),
    ("DELETE", "/api/v1/store/cart/lines/{variant_id}"): ("removeCartLine", "store-sales"),
    ("POST", "/api/v1/store/checkouts"): ("placeOrder", "store-sales"),
    ("GET", "/api/v1/store/orders/{public_token}"): ("getOrderByToken", "store-sales"),
    ("POST", "/api/v1/store/orders/{public_token}/payments"): ("payOrder", "store-sales"),
    ("GET", "/api/v1/store/account/orders"): ("listMyOrders", "store-account"),
    ("GET", "/api/v1/store/account/orders/{number}"): ("getMyOrder", "store-account"),
    ("GET", "/api/v1/store/account/addresses"): ("listAddresses", "store-account"),
    ("POST", "/api/v1/store/account/addresses"): ("addAddress", "store-account"),
    ("PATCH", "/api/v1/store/account/addresses/{address_id}"): ("changeAddress", "store-account"),
    ("DELETE", "/api/v1/store/account/addresses/{address_id}"): ("removeAddress", "store-account"),
    ("GET", "/api/v1/admin/orders"): ("listOrders", "admin-sales"),
    ("GET", "/api/v1/admin/orders/{order_id}"): ("getOrder", "admin-sales"),
    ("POST", "/api/v1/admin/orders/{order_id}/ship"): ("shipOrder", "admin-sales"),
    ("POST", "/api/v1/admin/orders/{order_id}/cancel"): ("cancelOrder", "admin-sales"),
    ("GET", "/api/v1/admin/inventory/locations"): ("listLocations", "admin-inventory"),
    ("POST", "/api/v1/admin/inventory/locations"): ("createLocation", "admin-inventory"),
    ("GET", "/api/v1/admin/inventory/locations/{code}"): ("getLocation", "admin-inventory"),
    ("PATCH", "/api/v1/admin/inventory/locations/{code}"): ("renameLocation", "admin-inventory"),
    ("DELETE", "/api/v1/admin/inventory/locations/{code}"): ("deleteLocation", "admin-inventory"),
    ("GET", "/api/v1/admin/inventory/stock"): ("listStock", "admin-inventory"),
    ("POST", "/api/v1/admin/inventory/units"): ("labelUnits", "admin-inventory"),
    ("GET", "/api/v1/admin/inventory/units/{code}"): ("getUnit", "admin-inventory"),
    ("POST", "/api/v1/admin/inventory/units/{code}/scrap"): ("scrapUnit", "admin-inventory"),
    ("POST", "/api/v1/admin/inventory/scans"): ("recordScan", "admin-inventory"),
    ("POST", "/api/v1/admin/inventory/scans/{scan_id}/undo"): ("undoScan", "admin-inventory"),
    ("GET", "/api/v1/admin/inventory/orders/{order_id}/pick-list"): (
        "getPickList",
        "admin-inventory",
    ),
    ("POST", "/api/v1/admin/inventory/orders/{order_id}/allocation"): (
        "allocateOrder",
        "admin-inventory",
    ),
    ("POST", "/api/v1/admin/inventory/labels"): ("printLabels", "admin-inventory"),
    ("GET", "/api/v1/admin/catalog/articles.csv"): ("exportArticles", "admin-catalog"),
    ("GET", "/api/v1/store/products/{slug}/availability"): (
        "getProductAvailability",
        "store-inventory",
    ),
    ("GET", "/api/v1/store/fairs"): ("listFairs", "store-site"),
    ("GET", "/api/v1/store/fairs/calendar.ics"): ("getFairCalendar", "store-site"),
    ("GET", "/api/v1/store/fairs/{fair_id}/calendar.ics"): ("getFairEvent", "store-site"),
    ("POST", "/api/v1/store/fair-news/subscriptions"): ("subscribeFairNews", "store-site"),
    ("POST", "/api/v1/store/fair-news/confirmations"): ("confirmFairNews", "store-site"),
    ("POST", "/api/v1/store/fair-news/unsubscriptions"): ("unsubscribeFairNews", "store-site"),
    ("GET", "/api/v1/store/imprint"): ("getImprint", "store-site"),
    ("GET", "/api/v1/admin/fairs"): ("listAdminFairs", "admin-site"),
    ("POST", "/api/v1/admin/fairs"): ("createFair", "admin-site"),
    ("PUT", "/api/v1/admin/fairs/{fair_id}"): ("updateFair", "admin-site"),
    ("DELETE", "/api/v1/admin/fairs/{fair_id}"): ("deleteFair", "admin-site"),
    ("POST", "/api/v1/admin/fairs/{fair_id}/announcement"): ("announceFair", "admin-site"),
    ("GET", "/api/v1/admin/fair-news"): ("getFairNewsCounts", "admin-site"),
    ("GET", "/api/v1/admin/marketplace/ebay"): ("getEbayStatus", "admin-marketplace"),
    ("POST", "/api/v1/admin/marketplace/ebay/connect"): ("connectEbay", "admin-marketplace"),
    ("POST", "/api/v1/admin/marketplace/ebay/disconnect"): (
        "disconnectEbay",
        "admin-marketplace",
    ),
    ("PUT", "/api/v1/admin/marketplace/ebay/settings"): (
        "changeEbaySettings",
        "admin-marketplace",
    ),
    ("GET", "/api/v1/admin/marketplace/ebay/policies"): (
        "listEbayPolicies",
        "admin-marketplace",
    ),
    ("POST", "/api/v1/admin/marketplace/ebay/location"): (
        "createEbayLocation",
        "admin-marketplace",
    ),
    ("GET", "/api/v1/admin/marketplace/ebay/categories"): (
        "listEbayCategories",
        "admin-marketplace",
    ),
    ("PUT", "/api/v1/admin/marketplace/ebay/categories"): (
        "setEbayCategories",
        "admin-marketplace",
    ),
    ("GET", "/api/v1/admin/marketplace/ebay/listings"): (
        "listEbayListings",
        "admin-marketplace",
    ),
    ("GET", "/api/v1/admin/marketplace/ebay/products/{product_id}/listings"): (
        "listProductEbayListings",
        "admin-marketplace",
    ),
    ("PUT", "/api/v1/admin/marketplace/ebay/products/{product_id}/listings/{scale_code}"): (
        "setProductEbayListing",
        "admin-marketplace",
    ),
    ("POST", "/api/v1/admin/marketplace/ebay/listings/{listing_id}/sync"): (
        "syncEbayListing",
        "admin-marketplace",
    ),
    ("GET", "/api/v1/admin/marketplace/ebay/orders"): ("listEbayOrders", "admin-marketplace"),
    ("POST", "/api/v1/admin/marketplace/ebay/orders/fetch"): (
        "fetchEbayOrders",
        "admin-marketplace",
    ),
    ("POST", "/api/v1/admin/marketplace/ebay/orders/{marketplace_order_id}/report-shipment"): (
        "reportEbayShipment",
        "admin-marketplace",
    ),
    ("POST", "/api/v1/admin/marketplace/ebay/test-sales"): (
        "createEbayTestSale",
        "admin-marketplace",
    ),
    ("POST", "/api/v1/admin/marketplace/ebay/test-sales/{external_id}/cancel"): (
        "cancelEbayTestSale",
        "admin-marketplace",
    ),
    ("GET", "/healthz"): ("getHealth", "system"),
    ("GET", "/readyz"): ("getReadiness", "system"),
}


class TestOpenApi:
    @pytest.fixture
    def document(self, app: FastAPI) -> dict[str, Any]:
        return app.openapi()

    def test_every_route_has_its_operation_id_and_tag(self, document: dict[str, Any]) -> None:
        operations = {
            (method.upper(), path): (operation["operationId"], operation["tags"])
            for path, item in document["paths"].items()
            for method, operation in item.items()
        }
        assert operations == {
            key: (operation_id, [tag]) for key, (operation_id, tag) in EXPECTED_OPERATIONS.items()
        }

    def test_errors_are_documented_as_problem_details(self, document: dict[str, Any]) -> None:
        for item in document["paths"].values():
            for operation in item.values():
                for status, response in operation["responses"].items():
                    if int(status) >= 400:
                        assert list(response["content"]) == ["application/problem+json"]
                        assert "Problem codes:" in response["description"]
        schemas = document["components"]["schemas"]
        assert {"Problem", "ValidationProblem", "ProblemFieldError"} <= set(schemas)
        assert "HTTPValidationError" not in schemas

    def test_responses_never_expose_secrets(self, document: dict[str, Any]) -> None:
        schemas = document["components"]["schemas"]
        for name in ("AccountOut", "StaffOut"):
            assert not {"password_hash", "token", "password"} & set(schemas[name]["properties"])
