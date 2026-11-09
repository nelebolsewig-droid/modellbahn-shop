"""FastAPI dependencies of the AI API: the service and who may do what."""

from typing import Annotated

from fastapi import Depends, Request

from modellbahn.modules.ai.application.copy import CopyService
from modellbahn.modules.identity.contracts.auth import StaffMember, StaffRole, require_staff
from modellbahn.platform.http import app_state


def get_copy_service(request: Request) -> CopyService:
    return app_state(request, "copy_service", CopyService)


CopyServiceDep = Annotated[CopyService, Depends(get_copy_service)]

# Whoever keeps the catalogue asks for a draft and takes it over. A run over every draft
# product costs real money, so only the owner starts it.
CopyEditor = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]
CopyOwner = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER))]
