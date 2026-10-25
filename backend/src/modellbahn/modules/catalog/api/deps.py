"""FastAPI dependencies of the catalogue API: the service, editors, versions (ETag)."""

from typing import Annotated, Final

from fastapi import Depends, Header, Request, Response

from modellbahn.modules.catalog.application.scales import ScaleService
from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.identity.contracts.auth import StaffMember, StaffRole, require_staff
from modellbahn.platform.errors import PreconditionFailedError, PreconditionRequiredError
from modellbahn.platform.http import app_state

# What the shop's own pages may cache; the shop renders on the server, so this mostly
# spares the API repeated identical requests.
STORE_CACHE_CONTROL: Final = "public, max-age=60"


def get_catalog_service(request: Request) -> CatalogService:
    return app_state(request, "catalog_service", CatalogService)


CatalogServiceDep = Annotated[CatalogService, Depends(get_catalog_service)]


def get_scale_service(request: Request) -> ScaleService:
    return app_state(request, "scale_service", ScaleService)


ScaleServiceDep = Annotated[ScaleService, Depends(get_scale_service)]
# Packers scan and pack, nothing else (KONZEPT §9.2).
CatalogEditor = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]
IfMatch = Annotated[
    str | None,
    Header(description='The ETag of the product as read, e.g. `"7"`. A newer version answers 412.'),
]


def etag(version: int) -> str:
    return f'"{version}"'


def set_etag(response: Response, version: int) -> None:
    response.headers["ETag"] = etag(version)


def expected_version(if_match: str | None, *, required: bool) -> int | None:
    """The version named by ``If-Match``; ``None`` if absent (and allowed) or ``*``.

    Routes that overwrite what the client saw (texts, the whole gallery) require it,
    so an old browser tab cannot silently undo someone else's work.
    """
    if if_match is None or not if_match.strip():
        if required:
            raise PreconditionRequiredError("Send If-Match with the ETag of the product as read.")
        return None
    value = if_match.strip()
    if value == "*":
        return None
    value = value.removeprefix("W/").strip('"')
    if not value.isdigit():
        raise PreconditionFailedError("If-Match names no version of this product.")
    return int(value)
