"""Staff authentication for other modules' API layers (FastAPI dependencies).

It builds on the identity API, so only an API layer may import it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.identity.api.deps import CurrentStaff
from modellbahn.modules.identity.domain.model import StaffRole
from modellbahn.platform.errors import ForbiddenError

__all__ = ["StaffMember", "StaffRole", "require_staff"]


@dataclass(frozen=True, slots=True)
class StaffMember:
    """The logged-in staff member, as other modules see them."""

    id: UUID
    display_name: str
    role: StaffRole


def require_staff(*roles: StaffRole) -> Callable[..., Awaitable[StaffMember]]:
    """A dependency for routes that only staff with one of ``roles`` may use.

    Without an admin session the answer is 401 ``not_authenticated``; a staff member
    with another role gets 403 ``insufficient_role``.
    """
    allowed = frozenset(roles)

    async def dependency(auth: CurrentStaff) -> StaffMember:
        account = auth.account
        if account.role is None or account.role not in allowed:
            raise ForbiddenError("Your role does not allow this action.", code="insufficient_role")
        return StaffMember(id=account.id, display_name=account.display_name, role=account.role)

    return dependency
