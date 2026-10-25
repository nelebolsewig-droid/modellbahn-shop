"""Stock as the shop shows it, public: how soon each variant can be delivered."""

from typing import Final

from fastapi import APIRouter, Response

from modellbahn.modules.inventory.api.deps import AvailabilityServiceDep
from modellbahn.modules.inventory.api.schemas import AvailabilityOut, VariantAvailabilityOut
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/store", tags=["store-inventory"])

# Stock changes with every sale; a few seconds of caching still spare the database a
# burst of visitors.
AVAILABILITY_CACHE_CONTROL: Final = "public, max-age=15"


@router.get(
    "/products/{slug}/availability",
    operation_id="getProductAvailability",
    summary="How soon each variant of a product can be delivered",
    responses=problems({404: ["product_not_found"]}, unsafe=False),
)
async def get_availability(
    slug: str, response: Response, service: AvailabilityServiceDep
) -> AvailabilityOut:
    items = await service.for_product(slug)
    response.headers["Cache-Control"] = AVAILABILITY_CACHE_CONTROL
    return AvailabilityOut(items=[VariantAvailabilityOut.from_availability(i) for i in items])
