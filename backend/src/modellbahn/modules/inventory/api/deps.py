"""FastAPI dependencies of the inventory API: services and who may do what."""

from typing import Annotated

from fastapi import Depends, Request

from modellbahn.modules.identity.contracts.auth import StaffMember, StaffRole, require_staff
from modellbahn.modules.inventory.application.allocation import AllocationService
from modellbahn.modules.inventory.application.assembly import AssemblyService
from modellbahn.modules.inventory.application.availability import AvailabilityService
from modellbahn.modules.inventory.application.labels import LabelService
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.parts import PartStoreService
from modellbahn.modules.inventory.application.scanning import ScanService
from modellbahn.modules.inventory.application.stock import StockService
from modellbahn.modules.inventory.application.till import TillService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.platform.http import app_state


def get_location_service(request: Request) -> LocationService:
    return app_state(request, "location_service", LocationService)


def get_unit_service(request: Request) -> UnitService:
    return app_state(request, "unit_service", UnitService)


def get_stock_service(request: Request) -> StockService:
    return app_state(request, "stock_service", StockService)


def get_scan_service(request: Request) -> ScanService:
    return app_state(request, "scan_service", ScanService)


def get_allocation_service(request: Request) -> AllocationService:
    return app_state(request, "allocation_service", AllocationService)


def get_label_service(request: Request) -> LabelService:
    return app_state(request, "label_service", LabelService)


def get_availability_service(request: Request) -> AvailabilityService:
    return app_state(request, "availability_service", AvailabilityService)


def get_part_store_service(request: Request) -> PartStoreService:
    return app_state(request, "part_store_service", PartStoreService)


def get_assembly_service(request: Request) -> AssemblyService:
    return app_state(request, "assembly_service", AssemblyService)


def get_till_service(request: Request) -> TillService:
    return app_state(request, "till_service", TillService)


LocationServiceDep = Annotated[LocationService, Depends(get_location_service)]
UnitServiceDep = Annotated[UnitService, Depends(get_unit_service)]
ScanServiceDep = Annotated[ScanService, Depends(get_scan_service)]
StockServiceDep = Annotated[StockService, Depends(get_stock_service)]
AllocationServiceDep = Annotated[AllocationService, Depends(get_allocation_service)]
LabelServiceDep = Annotated[LabelService, Depends(get_label_service)]
AvailabilityServiceDep = Annotated[AvailabilityService, Depends(get_availability_service)]
PartStoreServiceDep = Annotated[PartStoreService, Depends(get_part_store_service)]
AssemblyServiceDep = Annotated[AssemblyService, Depends(get_assembly_service)]
TillServiceDep = Annotated[TillService, Depends(get_till_service)]

# Packers scan, pick and print labels; arranging the store and its stock is for owner and staff.
StockWorker = Annotated[
    StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF, StaffRole.PACKER))
]
STOCK_MANAGERS = frozenset({StaffRole.OWNER, StaffRole.STAFF})
"""Who may arrange the store and its stock: book pieces in by hand and out."""
StockManager = Annotated[StaffMember, Depends(require_staff(*STOCK_MANAGERS))]
