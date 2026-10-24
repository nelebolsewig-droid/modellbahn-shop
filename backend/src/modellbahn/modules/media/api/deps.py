"""FastAPI dependencies of the media API: the service, settings, who may manage media."""

from typing import Annotated

from fastapi import Depends, Request

from modellbahn.modules.identity.contracts.auth import StaffMember, StaffRole, require_staff
from modellbahn.modules.media.application.services import MediaService
from modellbahn.platform.config import Settings
from modellbahn.platform.http import app_state


def get_media_service(request: Request) -> MediaService:
    return app_state(request, "media_service", MediaService)


def get_public_base_url(request: Request) -> str:
    return app_state(request, "settings", Settings).media_public_base_url


MediaServiceDep = Annotated[MediaService, Depends(get_media_service)]
PublicBaseUrl = Annotated[str, Depends(get_public_base_url)]
# Packers scan and pack, nothing else (KONZEPT §9.2).
MediaEditor = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]
