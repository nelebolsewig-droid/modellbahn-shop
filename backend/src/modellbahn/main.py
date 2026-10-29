"""Composition root of the API process: ``uvicorn modellbahn.main:app``."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from typing import Any, Final

from fastapi import APIRouter, Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn import __version__
from modellbahn.modules.catalog.api import admin as catalog_admin
from modellbahn.modules.catalog.api import store as catalog_store
from modellbahn.modules.catalog.api.errors import (
    install_error_translations as install_catalog_error_translations,
)
from modellbahn.modules.catalog.application.scales import ScaleService
from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.catalog.application.services import (
    UnitOfWorkFactory as CatalogUnitOfWorkFactory,
)
from modellbahn.modules.catalog.infrastructure.mapping import (
    start_mappers as start_catalog_mappers,
)
from modellbahn.modules.catalog.infrastructure.repositories import catalog_uow_factory
from modellbahn.modules.identity.api import admin as identity_admin
from modellbahn.modules.identity.api import store as identity_store
from modellbahn.modules.identity.api.deps import (
    AUTH_RATE_LIMITER,
    current_staff,
    staff_session_is_valid,
)
from modellbahn.modules.identity.api.errors import (
    install_error_translations as install_identity_error_translations,
)
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.identity.infrastructure.mapping import (
    start_mappers as start_identity_mappers,
)
from modellbahn.modules.identity.infrastructure.repositories import SqlIdentityUnitOfWork
from modellbahn.modules.inventory.api import admin as inventory_admin
from modellbahn.modules.inventory.api import store as inventory_store
from modellbahn.modules.inventory.api.errors import (
    install_error_translations as install_inventory_error_translations,
)
from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.application.availability import AvailabilityService
from modellbahn.modules.inventory.application.common import (
    UnitOfWorkFactory as InventoryUnitOfWorkFactory,
)
from modellbahn.modules.inventory.application.labels import LabelService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.infrastructure.labels import ReportLabLabelRenderer
from modellbahn.modules.inventory.infrastructure.mapping import (
    start_mappers as start_inventory_mappers,
)
from modellbahn.modules.inventory.infrastructure.repositories import inventory_uow_factory
from modellbahn.modules.manufacturing.api import admin as manufacturing_admin
from modellbahn.modules.manufacturing.api.errors import (
    install_error_translations as install_manufacturing_error_translations,
)
from modellbahn.modules.manufacturing.application.jobs import PrintJobService
from modellbahn.modules.manufacturing.application.parts import (
    BomService,
    MaterialService,
    PartService,
)
from modellbahn.modules.manufacturing.application.ports import (
    UnitOfWorkFactory as ManufacturingUnitOfWorkFactory,
)
from modellbahn.modules.manufacturing.application.printers import PrinterService
from modellbahn.modules.manufacturing.infrastructure.mapping import (
    start_mappers as start_manufacturing_mappers,
)
from modellbahn.modules.manufacturing.infrastructure.repositories import (
    manufacturing_uow_factory,
)
from modellbahn.modules.marketplace.api import admin as marketplace_admin
from modellbahn.modules.marketplace.api import webhooks as marketplace_webhooks
from modellbahn.modules.marketplace.api.deps import ACCOUNT_DELETIONS_STATE, MARKETPLACE_STATE
from modellbahn.modules.marketplace.api.errors import (
    install_error_translations as install_marketplace_error_translations,
)
from modellbahn.modules.marketplace.infrastructure.setup import (
    build_account_deletions,
    build_marketplace,
)
from modellbahn.modules.media.api import admin as media_admin
from modellbahn.modules.media.api.errors import (
    install_error_translations as install_media_error_translations,
)
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.media.infrastructure.mapping import start_mappers as start_media_mappers
from modellbahn.modules.media.infrastructure.repositories import SqlMediaUnitOfWork
from modellbahn.modules.media.infrastructure.storage import S3MediaStorage
from modellbahn.modules.sales.api import account as sales_account
from modellbahn.modules.sales.api import admin as sales_admin
from modellbahn.modules.sales.api import store as sales_store
from modellbahn.modules.sales.api.deps import CHECKOUT_RATE_LIMITER
from modellbahn.modules.sales.api.errors import (
    install_error_translations as install_sales_error_translations,
)
from modellbahn.modules.sales.application.addresses import AddressService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.infrastructure.mapping import start_mappers as start_sales_mappers
from modellbahn.modules.sales.infrastructure.payments import MockPaymentGateway
from modellbahn.modules.sales.infrastructure.repositories import sales_uow_factory
from modellbahn.modules.site.api import admin as site_admin
from modellbahn.modules.site.api import store as site_store
from modellbahn.modules.site.api.deps import FAIR_NEWS_RATE_LIMITER
from modellbahn.modules.site.api.errors import (
    install_error_translations as install_site_error_translations,
)
from modellbahn.modules.site.application.fairs import FairService
from modellbahn.modules.site.application.subscriptions import SubscriptionService
from modellbahn.modules.site.infrastructure.mapping import start_mappers as start_site_mappers
from modellbahn.modules.site.infrastructure.repositories import site_uow_factory
from modellbahn.platform import http
from modellbahn.platform.clock import SystemClock
from modellbahn.platform.config import Settings
from modellbahn.platform.db import asyncpg_dsn, create_engine, create_session_factory
from modellbahn.platform.errors import (
    add_problem_schemas,
    install_exception_handlers,
    problems,
)
from modellbahn.platform.events import event_registry
from modellbahn.platform.lifecycle import on_exit_signal
from modellbahn.platform.logging import RequestContextMiddleware, configure_logging
from modellbahn.platform.ratelimit import RateLimiter
from modellbahn.platform.realtime import RealtimeHub, create_event_stream_router
from modellbahn.platform.security import Argon2PasswordHasher, csrf_guard

API_PREFIX: Final = "/api/v1"

_DESCRIPTION: Final = """\
API of the Modellbahn-Shop.

* Errors are RFC 9457 problem details (`application/problem+json`) with a stable `code`.
* State-changing requests (POST, PUT, PATCH, DELETE) under `/api/` must send the header
  `X-Modellbahn-Client: web` and, if they have a body, `Content-Type: application/json`.
* Customers and staff authenticate with separate session cookies (`mb_session`, `mb_admin`).
"""

_TAGS: Final = [
    {"name": "store-catalog", "description": "Products of the shop, public."},
    {"name": "store-sales", "description": "Cart, checkout, order status and payment."},
    {"name": "store-account", "description": "Customer accounts, their orders and addresses."},
    {"name": "store-inventory", "description": "How soon products can be delivered."},
    {
        "name": "store-site",
        "description": "Fairs, their calendar, the fair news by e-mail and the imprint.",
    },
    {"name": "admin-auth", "description": "Staff login for the admin area."},
    {"name": "admin-catalog", "description": "Products, scales, variants, galleries."},
    {"name": "admin-media", "description": "Product photos: uploads, processing, sizes."},
    {"name": "admin-sales", "description": "Orders: overview, dispatch, cancellation."},
    {
        "name": "admin-inventory",
        "description": "Locations, units, scans, picking and labels of the workshop.",
    },
    {"name": "admin-site", "description": "Fairs and the fair news."},
    {
        "name": "admin-manufacturing",
        "description": "Printers and their state, parts, bills of materials, print jobs.",
    },
    {
        "name": "admin-marketplace",
        "description": "eBay: the connection, offers kept in step with the shop, its orders.",
    },
    {"name": "admin-realtime", "description": "Live events for the admin area (SSE)."},
    {"name": "system", "description": "Health probes."},
]


class _ModellbahnApi(FastAPI):
    def openapi(self) -> dict[str, Any]:
        return add_problem_schemas(super().openapi())


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application. Nothing connects to the database before startup."""
    settings = settings or Settings()
    configure_logging(environment=settings.environment, level=settings.log_level)

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    _start_mappers()
    clock = SystemClock()
    identity_service = IdentityService(
        uow_factory=partial(SqlIdentityUnitOfWork, session_factory),
        hasher=Argon2PasswordHasher.from_settings(settings),
        clock=clock,
    )
    media_service = MediaService(
        uow_factory=partial(SqlMediaUnitOfWork, session_factory),
        storage=S3MediaStorage.from_settings(settings),
        clock=clock,
    )
    hub = RealtimeHub(asyncpg_dsn(settings.database_url))
    marketplace = build_marketplace(settings, session_factory, clock)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await hub.start()
        try:
            # Open event streams end at once on SIGTERM, so the server need not wait
            # for them until its graceful-shutdown timeout cancels them.
            with on_exit_signal(hub.close_streams):
                yield
        finally:
            await hub.stop()
            if marketplace is not None:
                await marketplace.aclose()
            await engine.dispose()

    # The interactive documentation is a development aid; production does not expose it.
    with_docs = not settings.is_production
    app = _ModellbahnApi(
        title="Modellbahn-Shop API",
        version=__version__,
        description=_DESCRIPTION,
        openapi_tags=_TAGS,
        openapi_url=f"{API_PREFIX}/openapi.json" if with_docs else None,
        docs_url=f"{API_PREFIX}/docs" if with_docs else None,
        redoc_url=None,
        lifespan=lifespan,
        dependencies=[Depends(csrf_guard)],
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.identity_service = identity_service
    app.state.media_service = media_service
    _attach_catalog_services(
        app,
        uow_factory=catalog_uow_factory(
            session_factory, public_base_url=settings.media_public_base_url
        ),
        clock=clock,
    )
    _attach_sales_services(
        app,
        uow_factory=sales_uow_factory(
            session_factory, public_base_url=settings.media_public_base_url
        ),
        clock=clock,
    )
    _attach_inventory_services(app, uow_factory=inventory_uow_factory(session_factory), clock=clock)
    _attach_manufacturing_services(
        app, uow_factory=manufacturing_uow_factory(session_factory), clock=clock
    )
    site_uow = site_uow_factory(session_factory)
    app.state.fair_service = FairService(uow_factory=site_uow, clock=clock)
    app.state.subscription_service = SubscriptionService(uow_factory=site_uow, clock=clock)
    app.state.imprint = settings.imprint
    setattr(app.state, MARKETPLACE_STATE, marketplace)
    setattr(
        app.state,
        ACCOUNT_DELETIONS_STATE,
        build_account_deletions(settings, session_factory, marketplace, clock),
    )
    app.state.realtime_hub = hub
    _attach_rate_limiters(app, settings)

    app.add_middleware(RequestContextMiddleware)
    install_exception_handlers(app)
    for install_error_translations in (
        install_identity_error_translations,
        install_media_error_translations,
        install_catalog_error_translations,
        install_sales_error_translations,
        install_inventory_error_translations,
        install_site_error_translations,
        install_marketplace_error_translations,
        install_manufacturing_error_translations,
    ):
        install_error_translations(app)

    api = _api_router(hub, engine)
    app.include_router(http.router)
    app.include_router(api)
    return app


def _start_mappers() -> None:
    """Map every module's domain classes onto its tables (each module once)."""
    start_identity_mappers()
    start_media_mappers()
    start_catalog_mappers()
    start_sales_mappers()
    start_inventory_mappers()
    start_site_mappers()
    start_manufacturing_mappers()


def _api_router(hub: RealtimeHub, engine: AsyncEngine) -> APIRouter:
    """Every module's routes under ``/api/v1``, and the admin event stream."""
    api = APIRouter(prefix=API_PREFIX)
    api.include_router(catalog_store.router)
    api.include_router(identity_store.router)
    api.include_router(sales_store.router)
    api.include_router(sales_account.router)
    api.include_router(inventory_store.router)
    api.include_router(site_store.router)
    api.include_router(identity_admin.router)
    api.include_router(catalog_admin.router)
    api.include_router(media_admin.router)
    api.include_router(sales_admin.router)
    api.include_router(inventory_admin.router)
    api.include_router(manufacturing_admin.router)
    api.include_router(site_admin.router)
    api.include_router(marketplace_admin.router)
    api.include_router(marketplace_webhooks.router)
    api.include_router(
        create_event_stream_router(
            hub=hub,
            engine=engine,
            registry=event_registry,
            audience="staff",
            path="/admin/events",
            operation_id="streamAdminEvents",
            tags=["admin-realtime"],
            dependencies=[Depends(current_staff)],
            authorize=staff_session_is_valid,
            responses=problems({401: ["not_authenticated"]}, unsafe=False),
        )
    )
    return api


def _attach_rate_limiters(app: FastAPI, settings: Settings) -> None:
    setattr(
        app.state,
        AUTH_RATE_LIMITER,
        RateLimiter(
            limit=settings.auth_rate_limit, window_seconds=settings.auth_rate_window_seconds
        ),
    )
    setattr(
        app.state,
        FAIR_NEWS_RATE_LIMITER,
        RateLimiter(
            limit=settings.fair_news_rate_limit,
            window_seconds=settings.fair_news_rate_window_seconds,
        ),
    )
    setattr(
        app.state,
        CHECKOUT_RATE_LIMITER,
        RateLimiter(
            limit=settings.checkout_rate_limit,
            window_seconds=settings.checkout_rate_window_seconds,
        ),
    )


def _attach_catalog_services(
    app: FastAPI, *, uow_factory: CatalogUnitOfWorkFactory, clock: SystemClock
) -> None:
    app.state.catalog_service = CatalogService(uow_factory=uow_factory, clock=clock)
    app.state.scale_service = ScaleService(uow_factory=uow_factory)


def _attach_sales_services(
    app: FastAPI, *, uow_factory: UnitOfWorkFactory, clock: SystemClock
) -> None:
    gateway = MockPaymentGateway()
    app.state.cart_service = CartService(uow_factory=uow_factory, clock=clock)
    app.state.checkout_service = CheckoutService(
        uow_factory=uow_factory, clock=clock, gateway=gateway
    )
    app.state.order_service = OrderService(uow_factory=uow_factory, clock=clock, gateway=gateway)
    app.state.address_service = AddressService(uow_factory=uow_factory, clock=clock)


def _attach_inventory_services(
    app: FastAPI, *, uow_factory: InventoryUnitOfWorkFactory, clock: SystemClock
) -> None:
    app.state.location_service = LocationService(uow_factory=uow_factory, clock=clock)
    app.state.unit_service = UnitService(uow_factory=uow_factory, clock=clock)
    app.state.scan_service = ScanService(uow_factory=uow_factory, clock=clock)
    app.state.allocation_service = AllocationService(uow_factory=uow_factory, clock=clock)
    app.state.label_service = LabelService(
        uow_factory=uow_factory, renderer=ReportLabLabelRenderer()
    )
    app.state.availability_service = AvailabilityService(uow_factory=uow_factory)


def _attach_manufacturing_services(
    app: FastAPI, *, uow_factory: ManufacturingUnitOfWorkFactory, clock: SystemClock
) -> None:
    app.state.printer_service = PrinterService(uow_factory=uow_factory, clock=clock)
    app.state.material_service = MaterialService(uow_factory=uow_factory, clock=clock)
    app.state.part_service = PartService(uow_factory=uow_factory, clock=clock)
    app.state.bom_service = BomService(uow_factory=uow_factory, clock=clock)
    app.state.print_job_service = PrintJobService(uow_factory=uow_factory, clock=clock)


app = create_app()
