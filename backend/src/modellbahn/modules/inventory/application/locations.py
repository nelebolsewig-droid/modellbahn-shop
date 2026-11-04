"""Use cases of the location tree: list, create, rename, remove, look inside."""

from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.common import UnitOfWorkFactory
from modellbahn.modules.inventory.domain.errors import (
    LocationCodeTakenError,
    LocationInUseError,
    LocationNotEmptyError,
    LocationNotFoundError,
)
from modellbahn.modules.inventory.domain.events import LocationChanged
from modellbahn.modules.inventory.domain.model import Location, LocationKind, Unit
from modellbahn.modules.inventory.domain.parts import PartStock
from modellbahn.modules.manufacturing.contracts.parts import PartInfo
from modellbahn.platform.clock import Clock
from modellbahn.platform.uow import UniqueViolationError


@dataclass(frozen=True, slots=True)
class LocationNode:
    """A location in the tree with what lies in it and below it."""

    location: Location
    unit_count: int
    """Units lying in this location itself."""
    total_count: int
    """Units in this location and everything below it."""
    part_count: int = 0
    """Printed parts lying in this location itself."""


@dataclass(frozen=True, slots=True)
class LocationContents:
    node: LocationNode
    ancestors: list[Location]
    children: list[LocationNode]
    units: list[Unit]
    """Units in the location and below it, oldest first."""
    variants: dict[UUID, SaleVariant]
    locations: dict[UUID, Location]
    """Every location a listed unit lies in."""
    order_numbers: dict[UUID, str]
    """Order numbers of reserved units, by allocation id."""
    parts: list[PartStock]
    """Printed parts in the location and below it, by part number."""
    part_infos: dict[UUID, PartInfo]


class LocationService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def tree(self) -> list[LocationNode]:
        """Every location in path order, with unit counts."""
        async with self._uow() as uow:
            locations = await uow.locations.tree()
            counts = await uow.locations.unit_counts()
            part_counts = await uow.part_stock.location_totals()
        return _nodes(locations, counts, part_counts)

    async def create(
        self, *, parent_code: str | None, segment: str, kind: LocationKind, name: str
    ) -> Location:
        async with self._uow() as uow:
            parent = None
            if parent_code is not None:
                parent = await uow.locations.get_by_code(parent_code.strip().upper())
                if parent is None:
                    raise LocationNotFoundError
            now = self._clock.now()
            location = Location.create(
                parent=parent, segment=segment, kind=kind, name=name, now=now
            )
            if await uow.locations.get_by_code(location.code) is not None:
                raise LocationCodeTakenError
            uow.locations.add(location)
            uow.publish(
                LocationChanged(
                    aggregate_id=location.id, occurred_at=now, code=location.code, change="created"
                )
            )
            try:
                await uow.commit()
            except UniqueViolationError as exc:  # created at the same moment elsewhere
                raise LocationCodeTakenError from exc
            return location

    async def rename(self, code: str, *, name: str) -> Location:
        async with self._uow() as uow:
            location = await uow.locations.get_by_code(code, for_update=True)
            if location is None:
                raise LocationNotFoundError
            now = self._clock.now()
            location.rename(name, now)
            uow.publish(
                LocationChanged(
                    aggregate_id=location.id, occurred_at=now, code=location.code, change="renamed"
                )
            )
            await uow.commit()
            return location

    async def remove(self, code: str) -> None:
        """Remove an empty location that never held anything (its label is thrown away)."""
        async with self._uow() as uow:
            location = await uow.locations.get_by_code(code, for_update=True)
            if location is None:
                raise LocationNotFoundError
            if (
                await uow.locations.has_children(location.id)
                or await uow.units.in_locations([location.id])
                or await uow.part_stock.in_locations([location.id])
            ):
                raise LocationNotEmptyError
            if await uow.locations.in_journal(location.id) or await uow.part_ledger.mentions(
                location.id
            ):
                raise LocationInUseError
            await uow.locations.delete(location)
            uow.publish(
                LocationChanged(
                    aggregate_id=location.id,
                    occurred_at=self._clock.now(),
                    code=location.code,
                    change="removed",
                )
            )
            await uow.commit()

    async def contents(self, code: str) -> LocationContents:
        async with self._uow() as uow:
            location = await uow.locations.get_by_code(code)
            if location is None:
                raise LocationNotFoundError
            subtree = await uow.locations.subtree(location)
            counts = await uow.locations.unit_counts()
            part_counts = await uow.part_stock.location_totals()
            all_locations = await uow.locations.tree()
            ancestors = [
                candidate
                for candidate in all_locations
                if location.path.startswith(f"{candidate.path}.")
            ]
            units = await uow.units.in_locations([loc.id for loc in subtree])
            variants = await uow.catalog.variants({unit.variant_id for unit in units})
            allocations = await uow.allocations.by_ids(
                [unit.allocation_id for unit in units if unit.allocation_id is not None]
            )
            numbers = await uow.orders.numbers({a.order_id for a in allocations.values()})
            parts = await uow.part_stock.in_locations([loc.id for loc in subtree])
            part_infos = await uow.manufacturing.parts({entry.part_id for entry in parts})
        nodes = _nodes(subtree, counts, part_counts)
        parts.sort(
            key=lambda entry: (
                part_infos[entry.part_id].part_number if entry.part_id in part_infos else "",
                entry.location_id,
            )
        )
        return LocationContents(
            node=nodes[0],
            ancestors=ancestors,
            children=[node for node in nodes if node.location.parent_id == location.id],
            units=units,
            variants=dict(variants),
            locations={loc.id: loc for loc in subtree},
            order_numbers={
                allocation_id: numbers[allocation.order_id]
                for allocation_id, allocation in allocations.items()
                if allocation.order_id in numbers
            },
            parts=parts,
            part_infos=part_infos,
        )


def _nodes(
    locations: list[Location], counts: dict[UUID, int], part_counts: dict[UUID, int]
) -> list[LocationNode]:
    """Locations in path order with their own and their subtree's unit counts."""
    totals = {location.id: counts.get(location.id, 0) for location in locations}
    # Deepest first, so every child has added its total before its parent does.
    for location in sorted(locations, key=lambda loc: loc.depth, reverse=True):
        if location.parent_id in totals:
            totals[location.parent_id] += totals[location.id]
    return [
        LocationNode(
            location=location,
            unit_count=counts.get(location.id, 0),
            total_count=totals[location.id],
            part_count=part_counts.get(location.id, 0),
        )
        for location in locations
    ]
