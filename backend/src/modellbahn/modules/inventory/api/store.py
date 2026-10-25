"""Stock as the shop shows it, public: availability per variant, the product behind a label."""

from typing import Final

from fastapi import APIRouter, Response

from modellbahn.modules.inventory.api.deps import AvailabilityServiceDep, UnitServiceDep
from modellbahn.modules.inventory.api.schemas import (
    AvailabilityOut,
    PublicUnitOut,
    VariantAvailabilityOut,
)
from modellbahn.modules.inventory.domain.errors import UnitNotFoundError
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/store", tags=["store-inventory"])

# Stock changes with every sale; a few seconds of caching still spare the database a
# burst of visitors.
AVAILABILITY_CACHE_CONTROL: Final = "public, max-age=15"


@router.get(
    "/products/{slug}/availability",
    operation_id="getProductAvailability",
    summary="How soon each variant of a product can be delivered",
    responses=problems({404: ["product_not_found"]}, unsafe=False, validated=False),
)
async def get_availability(
    slug: str, response: Response, service: AvailabilityServiceDep
) -> AvailabilityOut:
    items = await service.for_product(slug)
    response.headers["Cache-Control"] = AVAILABILITY_CACHE_CONTROL
    return AvailabilityOut(items=[VariantAvailabilityOut.from_availability(i) for i in items])


@router.get(
    "/units/{code}",
    operation_id="getPublicUnit",
    summary="The product a unit's label belongs to (a customer scanned it)",
    responses=problems({404: ["unit_not_found"]}, unsafe=False, validated=False),
)
async def get_public_unit(code: str, service: UnitServiceDep) -> PublicUnitOut:
    slug = await service.product_of(code)
    if slug is None:
        raise UnitNotFoundError
    return PublicUnitOut(product_slug=slug)
