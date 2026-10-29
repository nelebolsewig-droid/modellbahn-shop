"""FastAPI dependencies of the manufacturing API: services and who may do what."""

from typing import Annotated

from fastapi import Depends, Request

from modellbahn.modules.identity.contracts.auth import StaffMember, StaffRole, require_staff
from modellbahn.modules.manufacturing.application.jobs import PrintJobService
from modellbahn.modules.manufacturing.application.parts import (
    BomService,
    MaterialService,
    PartService,
)
from modellbahn.modules.manufacturing.application.printers import PrinterService
from modellbahn.platform.http import app_state


def get_printer_service(request: Request) -> PrinterService:
    return app_state(request, "printer_service", PrinterService)


def get_material_service(request: Request) -> MaterialService:
    return app_state(request, "material_service", MaterialService)


def get_part_service(request: Request) -> PartService:
    return app_state(request, "part_service", PartService)


def get_bom_service(request: Request) -> BomService:
    return app_state(request, "bom_service", BomService)


def get_print_job_service(request: Request) -> PrintJobService:
    return app_state(request, "print_job_service", PrintJobService)


PrinterServiceDep = Annotated[PrinterService, Depends(get_printer_service)]
MaterialServiceDep = Annotated[MaterialService, Depends(get_material_service)]
PartServiceDep = Annotated[PartService, Depends(get_part_service)]
BomServiceDep = Annotated[BomService, Depends(get_bom_service)]
PrintJobServiceDep = Annotated[PrintJobService, Depends(get_print_job_service)]

# Whoever stands at the printers reports a defect, starts a plate and says how it came
# out, packers included. Printers, parts, kits and the plan are for owner and staff.
PrinterOperator = Annotated[
    StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF, StaffRole.PACKER))
]
ProductionPlanner = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]
