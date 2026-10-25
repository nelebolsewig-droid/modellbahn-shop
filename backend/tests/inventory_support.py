"""Helpers for inventory tests: a small store, units on its shelf, picking an order."""

import contextlib
from uuid import UUID, uuid4

from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.identity.domain.model import StaffRole
from modellbahn.modules.inventory.application.allocation import (
    AllocationService,
    PickList,
    PieceState,
)
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.scanning import ScanRequest, ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.domain.errors import LocationCodeTakenError
from modellbahn.modules.inventory.domain.model import LocationKind, ScanMode
from modellbahn.platform.events import JsonObject

COMPARTMENT = "R01-F01"
PASSWORD = "Lagerist-2026-sicher"


async def store(locations: LocationService) -> str:
    """Site LAGER with shelf R01 and its compartment F01 (once); the compartment's code."""
    for parent, segment, kind in (
        (None, "LAGER", LocationKind.SITE),
        ("LAGER", "R01", LocationKind.SHELF),
        ("R01", "F01", LocationKind.COMPARTMENT),
    ):
        with contextlib.suppress(LocationCodeTakenError):
            await locations.create(parent_code=parent, segment=segment, kind=kind, name="")
    return COMPARTMENT


async def stock_up(
    locations: LocationService, units: UnitService, variant_id: UUID, quantity: int = 1
) -> list[str]:
    """``quantity`` new units of the variant, stored in the compartment; their codes."""
    views = await units.label_units(
        variant_id=variant_id,
        quantity=quantity,
        location_code=await store(locations),
        staff_id=None,
    )
    return [view.unit.code for view in views]


async def staff_member(identity: IdentityService, email: str = "lager@example.com") -> UUID:
    account = await identity.create_staff(
        email=email, display_name="Lagerist", role=StaffRole.PACKER, password=PASSWORD
    )
    return account.id


async def scan(
    scans: ScanService,
    staff_id: UUID,
    raw: str,
    mode: ScanMode,
    *,
    context: dict[str, str] | None = None,
    scan_id: UUID | None = None,
) -> JsonObject:
    return await scans.scan(
        ScanRequest(
            scan_id=scan_id or uuid4(),
            raw=raw,
            mode=mode,
            source="scanner",
            context=context or {},
        ),
        staff_id=staff_id,
    )


async def pick_everything(
    scans: ScanService, allocation: AllocationService, order_id: UUID, staff_id: UUID
) -> PickList:
    """Scan every reserved unit of the order in pick mode; the pick list afterwards."""
    pick_list = await allocation.pick_list(order_id)
    for item in pick_list.items:
        if item.state is PieceState.RESERVED and item.unit_code is not None:
            answer = await scan(
                scans,
                staff_id,
                item.unit_code,
                ScanMode.PICK,
                context={"order_id": str(order_id)},
            )
            assert answer["outcome"] == "applied", answer
    return await allocation.pick_list(order_id)
