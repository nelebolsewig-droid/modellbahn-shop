"""How soon the shop can deliver: per variant of a product, for its product page."""

from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.inventory.application.common import UnitOfWorkFactory
from modellbahn.modules.inventory.domain.availability import Availability, availability
from modellbahn.modules.inventory.domain.errors import ProductNotFoundError
from modellbahn.modules.inventory.domain.model import UnitStatus


@dataclass(frozen=True, slots=True)
class VariantAvailability:
    variant_id: UUID
    availability: Availability
    free_units: int
    lead_time_weeks: tuple[int, int] | None
    """For variants made to order: how many weeks making one takes."""


class AvailabilityService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory) -> None:
        self._uow = uow_factory

    async def for_product(self, slug: str) -> list[VariantAvailability]:
        """Availability of one piece of each variant on sale; a product not in the shop is 404."""
        async with self._uow() as uow:
            variants = [v for v in await uow.catalog.product_variants(slug) if v.purchasable]
            if not variants:
                raise ProductNotFoundError
            counts = await uow.units.counts([variant.variant_id for variant in variants])
        free = {
            count.variant_id: count.count for count in counts if count.status is UnitStatus.IN_STOCK
        }
        return [
            VariantAvailability(
                variant_id=variant.variant_id,
                availability=availability(
                    free_units=free.get(variant.variant_id, 0),
                    wanted=1,
                    allow_backorder=variant.allow_backorder,
                ),
                free_units=free.get(variant.variant_id, 0),
                lead_time_weeks=variant.lead_time_weeks if variant.allow_backorder else None,
            )
            for variant in variants
        ]
