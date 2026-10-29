"""Use cases around what is printed: materials, parts and the bills of materials of kits."""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from modellbahn.modules.catalog.contracts.product_scales import ProductScaleLabel
from modellbahn.modules.manufacturing.application.common import commit, parts_of
from modellbahn.modules.manufacturing.application.ports import (
    ManufacturingUnitOfWork,
    PartUsage,
    UnitOfWorkFactory,
)
from modellbahn.modules.manufacturing.domain.errors import (
    InvalidFieldError,
    MaterialNotFoundError,
    PartNotFoundError,
    ProductScaleNotFoundError,
)
from modellbahn.modules.manufacturing.domain.model import (
    BillOfMaterials,
    Material,
    Part,
    PartDetails,
    Printer,
    PrintJob,
    Technology,
)
from modellbahn.platform.clock import Clock

PARTS_LISTED_MAX: Final = 500
RECENT_JOBS_SHOWN: Final = 20
_NOT_USED: Final = PartUsage(boms=0, jobs=0)


@dataclass(frozen=True, slots=True)
class MaterialEntry:
    material: Material
    parts: int
    """How many parts are made of it."""


@dataclass(frozen=True, slots=True)
class PartEntry:
    part: Part
    material: Material | None
    scale_name: str
    usage: PartUsage


@dataclass(frozen=True, slots=True)
class BomUse:
    """A kit that needs the part, and how many of it."""

    product_scale: ProductScaleLabel
    quantity: int


@dataclass(frozen=True, slots=True)
class PartRecord:
    """A part with everything around it: the kits that need it, its latest plates."""

    entry: PartEntry
    uses: Sequence[BomUse]
    jobs: Sequence[PrintJob]
    printers: Mapping[UUID, Printer]
    parts: Mapping[UUID, Part]
    """Every part on those plates, to name them: a plate often carries others too."""


@dataclass(frozen=True, slots=True)
class BomView:
    """A product in one scale with its bill of materials (``None`` while it has none)."""

    product_scale: ProductScaleLabel
    bom: BillOfMaterials | None
    parts: Mapping[UUID, Part]

    @property
    def part_count(self) -> int:
        return self.bom.part_count if self.bom is not None else 0

    @property
    def print_minutes(self) -> int | None:
        """Printing time of one kit: each part's share of a full plate, added up.

        ``None`` while a part has no plate time. On resin a plate of different parts takes
        no longer than its slowest, so a full plate of kits prints faster than this sum.
        """
        if self.bom is None or not self.bom.lines:
            return None
        shares = [self.parts[line.part_id].minutes_per_part for line in self.bom.lines]
        if any(share is None for share in shares):
            return None
        total = sum(
            (share or 0) * line.quantity for share, line in zip(shares, self.bom.lines, strict=True)
        )
        return max(1, math.ceil(total - 1e-9))


class MaterialService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def all(self) -> list[MaterialEntry]:
        async with self._uow() as uow:
            materials = await uow.materials.all()
            counts = await uow.materials.part_counts()
        return [MaterialEntry(material, counts.get(material.id, 0)) for material in materials]

    async def create(self, *, name: str, technology: Technology, notes: str) -> MaterialEntry:
        async with self._uow() as uow:
            material = Material.create(
                name=name, technology=technology, notes=notes, now=self._clock.now()
            )
            await _check_name(uow, material.name, except_id=None)
            uow.materials.add(material)
            await commit(uow)
        return MaterialEntry(material, 0)

    async def change(
        self, material_id: UUID, *, name: str, notes: str, active: bool
    ) -> MaterialEntry:
        async with self._uow() as uow:
            material = await _material(uow, material_id, for_update=True)
            material.change(name=name, notes=notes, active=active, now=self._clock.now())
            await _check_name(uow, material.name, except_id=material.id)
            await commit(uow)
            counts = await uow.materials.part_counts()
        return MaterialEntry(material, counts.get(material.id, 0))

    async def delete(self, material_id: UUID) -> None:
        """Only a material no part is made of; any other can be archived."""
        async with self._uow() as uow:
            material = await _material(uow, material_id, for_update=True)
            await uow.materials.delete(material)
            await commit(uow)


class PartService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def search(
        self,
        *,
        scale_code: str | None = None,
        technology: Technology | None = None,
        query: str | None = None,
        include_archived: bool = False,
    ) -> list[PartEntry]:
        async with self._uow() as uow:
            parts = await uow.parts.search(
                scale_code=scale_code,
                technology=technology.value if technology is not None else None,
                query=query.strip() if query and query.strip() else None,
                include_archived=include_archived,
                limit=PARTS_LISTED_MAX,
            )
            return await _entries(uow, parts)

    async def record(self, part_id: UUID) -> PartRecord:
        async with self._uow() as uow:
            part = await _part(uow, part_id)
            (entry,) = await _entries(uow, [part])
            lines = await uow.boms.lines_with_part(part.id)
            labels = await uow.catalog.product_scales({line.product_scale_id for line in lines})
            jobs = await uow.jobs.latest(
                statuses=(), printer_id=None, part_id=part.id, limit=RECENT_JOBS_SHOWN
            )
            printers = await uow.printers.by_ids({job.printer_id for job in jobs})
            on_plates = await parts_of(uow, jobs)
        uses = [
            BomUse(product_scale=labels[line.product_scale_id], quantity=line.quantity)
            for line in lines
            if line.product_scale_id in labels
        ]
        uses.sort(key=lambda use: (use.product_scale.product_name, use.product_scale.scale_code))
        return PartRecord(
            entry=entry, uses=uses, jobs=jobs, printers=printers, parts={**on_plates, part.id: part}
        )

    async def create(
        self, details: PartDetails, *, scale_code: str, technology: Technology
    ) -> PartEntry:
        async with self._uow() as uow:
            checked = details.checked()
            if scale_code not in await uow.catalog.scale_names():
                raise InvalidFieldError("scale_code", "unknown", "no such scale")
            await _check_number(uow, checked.part_number, except_id=None)
            part = Part.create(
                checked,
                scale_code=scale_code,
                technology=technology,
                material=await _material_of(uow, checked),
                now=self._clock.now(),
            )
            uow.parts.add(part)
            await commit(uow)
            (entry,) = await _entries(uow, [part])
        return entry

    async def change(self, part_id: UUID, details: PartDetails, *, active: bool) -> PartEntry:
        async with self._uow() as uow:
            part = await _part(uow, part_id, for_update=True)
            checked = details.checked()
            await _check_number(uow, checked.part_number, except_id=part.id)
            part.change(
                checked,
                material=await _material_of(uow, checked),
                active=active,
                now=self._clock.now(),
            )
            await commit(uow)
            (entry,) = await _entries(uow, [part])
        return entry

    async def delete(self, part_id: UUID) -> None:
        """Only a part no kit needs and no plate carried; any other can be archived."""
        async with self._uow() as uow:
            part = await _part(uow, part_id, for_update=True)
            await uow.parts.delete(part)
            await commit(uow)


class BomService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def get(self, product_scale_id: UUID) -> BomView:
        async with self._uow() as uow:
            label = await _product_scale(uow, product_scale_id)
            bom = await uow.boms.get(product_scale_id)
            return await _view(uow, label, bom)

    async def replace(
        self,
        product_scale_id: UUID,
        lines: Sequence[tuple[UUID, int]],
        *,
        staff_id: UUID | None,
    ) -> BomView:
        """Set the parts of the kit; no lines at all removes its bill of materials."""
        now = self._clock.now()
        async with self._uow() as uow:
            label = await _product_scale(uow, product_scale_id)
            bom = await uow.boms.get(product_scale_id, for_update=True)
            if not lines:
                if bom is not None:
                    await uow.boms.delete(bom)
                    await commit(uow)
                return await _view(uow, label, None)
            parts = await uow.parts.by_ids({part_id for part_id, _ in lines})
            resolved: list[tuple[Part, int]] = []
            for index, (part_id, quantity) in enumerate(lines):
                part = parts.get(part_id)
                if part is None:
                    raise InvalidFieldError(f"lines.{index}.part_id", "unknown", "no such part")
                resolved.append((part, quantity))
            if bom is None:
                bom = BillOfMaterials.start(
                    product_scale_id=product_scale_id,
                    scale_code=label.scale_code,
                    staff_id=staff_id,
                    now=now,
                )
                uow.boms.add(bom)
            bom.replace(resolved, staff_id=staff_id, now=now)
            await commit(uow)
            return await _view(uow, label, bom)


async def _entries(uow: ManufacturingUnitOfWork, parts: Sequence[Part]) -> list[PartEntry]:
    materials = await uow.materials.by_ids(
        {part.material_id for part in parts if part.material_id is not None}
    )
    usage = await uow.parts.usage([part.id for part in parts])
    scale_names = await uow.catalog.scale_names()
    return [
        PartEntry(
            part=part,
            material=materials.get(part.material_id) if part.material_id is not None else None,
            scale_name=scale_names.get(part.scale_code, part.scale_code),
            usage=usage.get(part.id, _NOT_USED),
        )
        for part in parts
    ]


async def _view(
    uow: ManufacturingUnitOfWork, label: ProductScaleLabel, bom: BillOfMaterials | None
) -> BomView:
    parts = await uow.parts.by_ids({line.part_id for line in bom.lines}) if bom is not None else {}
    return BomView(product_scale=label, bom=bom, parts=parts)


async def _product_scale(uow: ManufacturingUnitOfWork, product_scale_id: UUID) -> ProductScaleLabel:
    label = (await uow.catalog.product_scales([product_scale_id])).get(product_scale_id)
    if label is None:
        raise ProductScaleNotFoundError
    return label


async def _material(
    uow: ManufacturingUnitOfWork, material_id: UUID, *, for_update: bool = False
) -> Material:
    material = await uow.materials.get(material_id, for_update=for_update)
    if material is None:
        raise MaterialNotFoundError
    return material


async def _material_of(uow: ManufacturingUnitOfWork, details: PartDetails) -> Material | None:
    if details.material_id is None:
        return None
    material = await uow.materials.get(details.material_id)
    if material is None:
        raise InvalidFieldError("material_id", "unknown", "no such material")
    return material


async def _part(uow: ManufacturingUnitOfWork, part_id: UUID, *, for_update: bool = False) -> Part:
    part = await uow.parts.get(part_id, for_update=for_update)
    if part is None:
        raise PartNotFoundError
    return part


async def _check_name(uow: ManufacturingUnitOfWork, name: str, *, except_id: UUID | None) -> None:
    if await uow.materials.name_taken(name, except_id=except_id):
        raise InvalidFieldError("name", "duplicate", "another material has it")


async def _check_number(
    uow: ManufacturingUnitOfWork, part_number: str, *, except_id: UUID | None
) -> None:
    if await uow.parts.number_taken(part_number, except_id=except_id):
        raise InvalidFieldError("part_number", "duplicate", "another part has it")
