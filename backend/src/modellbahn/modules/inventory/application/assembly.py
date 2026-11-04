"""Assembly (*Montage*): parts out of their boxes, by the bill of materials, into units.

The plan says, for a number of kits of a variant, how many of each part are needed and
which boxes they come from: started boxes first, so they empty, and the takes in walking
order. Assembling books exactly that plan inside one transaction: the part stock of the
kit's parts is locked first, then every unit is labelled and takes its parts, and the
parts journal names the unit for every take. A kit thus knows the boxes its parts came
from; a box that ran short since the plan was shown stops the assembly (409).
"""

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.common import (
    Journal,
    PartJournal,
    UnitOfWorkFactory,
    resolve_location,
)
from modellbahn.modules.inventory.application.parts import walking_order
from modellbahn.modules.inventory.application.ports import InventoryUnitOfWork
from modellbahn.modules.inventory.application.units import UnitView, label_new_units, unit_views
from modellbahn.modules.inventory.domain.errors import (
    BillOfMaterialsMissingError,
    InsufficientPartsError,
    VariantNotFoundError,
)
from modellbahn.modules.inventory.domain.model import Location
from modellbahn.modules.inventory.domain.parts import (
    PartNeed,
    PartStock,
    check_kits,
    kits_possible,
    plan_takes,
)
from modellbahn.modules.manufacturing.contracts.parts import PartInfo
from modellbahn.platform.clock import Clock


@dataclass(frozen=True, slots=True)
class PlannedTake:
    location: Location
    quantity: int


@dataclass(frozen=True, slots=True)
class PlannedPart:
    """One part of the kit: how many, how many are there, and from which boxes."""

    part: PartInfo
    need: PartNeed
    takes: list[PlannedTake]
    """In walking order."""


@dataclass(frozen=True, slots=True)
class AssemblyPlan:
    variant: SaleVariant
    kits: int
    parts: list[PlannedPart]
    """In the order of the bill of materials."""
    possible: int
    """How many kits the parts in stock suffice for."""

    @property
    def ready(self) -> bool:
        return all(planned.need.missing == 0 for planned in self.parts)


@dataclass(frozen=True, slots=True)
class Assembly:
    plan: AssemblyPlan
    units: list[UnitView]


class AssemblyService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def plan(self, variant_id: UUID, kits: int) -> AssemblyPlan:
        """What ``kits`` kits of the variant take, and where it lies; nothing is booked."""
        check_kits(kits)
        async with self._uow() as uow:
            plan, _ = await _plan(uow, variant_id, kits, for_update=False)
            return plan

    async def assemble(
        self,
        variant_id: UUID,
        kits: int,
        *,
        location_code: str | None,
        staff_id: UUID,
    ) -> Assembly:
        """Take the parts, label the units; put them away into ``location_code`` if given."""
        check_kits(kits)
        async with self._uow() as uow:
            location = (
                await resolve_location(uow, location_code, "location_code")
                if location_code is not None
                else None
            )
            plan, stock = await _plan(uow, variant_id, kits, for_update=True)
            if not plan.ready:
                raise InsufficientPartsError
            now = self._clock.now()
            units = await label_new_units(
                uow,
                Journal(uow, staff_id=staff_id, now=now),
                variant_id=variant_id,
                quantity=kits,
                location=location,
            )
            journal = PartJournal(uow, staff_id=staff_id, now=now)
            # What is left of each planned take while the units take their share; the first
            # units empty the started boxes, as planned.
            left = {
                (planned.part.part_id, take.location_id): take.quantity
                for planned in plan.parts
                for take in planned.need.takes
            }
            for unit in units:
                for planned in plan.parts:
                    wanted = planned.need.per_kit
                    for take in planned.need.takes:
                        key = (planned.part.part_id, take.location_id)
                        quantity = min(wanted, left[key])
                        if quantity == 0:
                            continue
                        journal.book(stock[key].assemble(quantity, unit.id, now))
                        left[key] -= quantity
                        wanted -= quantity
                        if wanted == 0:
                            break
            await journal.announce()
            await uow.commit()
            return Assembly(plan=plan, units=await unit_views(uow, units))


async def _plan(
    uow: InventoryUnitOfWork, variant_id: UUID, kits: int, *, for_update: bool
) -> tuple[AssemblyPlan, dict[tuple[UUID, UUID], PartStock]]:
    variant = (await uow.catalog.variants([variant_id])).get(variant_id)
    if variant is None:
        raise VariantNotFoundError
    kit = await uow.manufacturing.bill_of_materials(variant.product_scale_id)
    if not kit:
        raise BillOfMaterialsMissingError
    stock = await uow.part_stock.for_parts(
        [line.part.part_id for line in kit], for_update=for_update
    )
    locations = await uow.locations.by_ids({entry.location_id for entry in stock})
    by_part: defaultdict[UUID, list[PartStock]] = defaultdict(list)
    for entry in walking_order(stock, locations):
        by_part[entry.part_id].append(entry)
    planned: list[PlannedPart] = []
    for line in kit:
        need = plan_takes(
            part_id=line.part.part_id,
            per_kit=line.quantity,
            kits=kits,
            stock=by_part[line.part.part_id],
        )
        takes = [
            PlannedTake(location=locations[take.location_id], quantity=take.quantity)
            for take in need.takes
        ]
        takes.sort(key=lambda take: take.location.path)
        planned.append(PlannedPart(part=line.part, need=need, takes=takes))
    plan = AssemblyPlan(
        variant=variant,
        kits=kits,
        parts=planned,
        possible=kits_possible([entry.need for entry in planned]),
    )
    return plan, {(entry.part_id, entry.location_id): entry for entry in stock}
