"""Staff and customer authentication for other modules' API layers (FastAPI dependencies).

It builds on the identity API, so only an API layer may import it.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Request

from modellbahn.modules.identity.api.deps import (
    CUSTOMER_COOKIE,
    CurrentCustomer,
    CurrentStaff,
    get_identity_service,
)
from modellbahn.modules.identity.domain.errors import NotAuthenticatedError
from modellbahn.modules.identity.domain.model import StaffRole
from modellbahn.platform.errors import ForbiddenError

__all__ = [
    "Customer",
    "StaffMember",
    "StaffRole",
    "customer_or_none",
    "require_customer",
    "require_staff",
]


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


@dataclass(frozen=True, slots=True)
class Customer:
    """The logged-in customer, as other modules see them."""

    id: UUID
    email: str
    display_name: str


async def require_customer(auth: CurrentCustomer) -> Customer:
    """A dependency for routes of the customer account; 401 ``not_authenticated`` otherwise."""
    account = auth.account
    return Customer(id=account.id, email=account.email, display_name=account.display_name)


async def customer_or_none(request: Request) -> Customer | None:
    """The logged-in customer if there is one, for routes that guests may use as well.

    An invalid or expired cookie counts as a guest; the account routes clear it.
    """
    token = request.cookies.get(CUSTOMER_COOKIE.name)
    if not token:
        return None
    try:
        auth = await get_identity_service(request).authenticate(
            kind=CUSTOMER_COOKIE.kind, token=token
        )
    except NotAuthenticatedError:
        return None
    account = auth.account
    return Customer(id=account.id, email=account.email, display_name=account.display_name)
