"""Composition root of the API process: ``uvicorn modellbahn.main:app``."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from typing import Any, Final

from fastapi import APIRouter, Depends, FastAPI

from modellbahn import __version__
from modellbahn.modules.catalog.api import admin as catalog_admin
from modellbahn.modules.catalog.api import store as catalog_store
from modellbahn.modules.catalog.api.errors import (
    install_error_translations as install_catalog_error_translations,
)
from modellbahn.modules.catalog.application.services import CatalogService
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
from modellbahn.modules.media.api import admin as media_admin
from modellbahn.modules.media.api.errors import (
    install_error_translations as install_media_error_translations,
)
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.media.infrastructure.mapping import start_mappers as start_media_mappers
from modellbahn.modules.media.infrastructure.repositories import SqlMediaUnitOfWork
from modellbahn.modules.media.infrastructure.storage import S3MediaStorage
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
    {"name": "store-account", "description": "Customer accounts of the shop."},
    {"name": "admin-auth", "description": "Staff login for the admin area."},
    {"name": "admin-catalog", "description": "Products, gauges, variants, galleries."},
    {"name": "admin-media", "description": "Product photos: uploads, processing, sizes."},
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
    start_identity_mappers()
    start_media_mappers()
    start_catalog_mappers()
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
    catalog_service = CatalogService(
        uow_factory=catalog_uow_factory(
            session_factory, public_base_url=settings.media_public_base_url
        ),
        clock=clock,
    )
    hub = RealtimeHub(asyncpg_dsn(settings.database_url))

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
    app.state.catalog_service = catalog_service
    app.state.realtime_hub = hub
    setattr(
        app.state,
        AUTH_RATE_LIMITER,
        RateLimiter(
            limit=settings.auth_rate_limit, window_seconds=settings.auth_rate_window_seconds
        ),
    )

    app.add_middleware(RequestContextMiddleware)
    install_exception_handlers(app)
    install_identity_error_translations(app)
    install_media_error_translations(app)
    install_catalog_error_translations(app)

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(catalog_store.router)
    api.include_router(identity_store.router)
    api.include_router(identity_admin.router)
    api.include_router(catalog_admin.router)
    api.include_router(media_admin.router)
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
    app.include_router(http.router)
    app.include_router(api)
    return app


app = create_app()
