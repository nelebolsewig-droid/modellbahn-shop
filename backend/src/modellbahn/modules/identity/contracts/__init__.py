"""Public contract of the identity module: the only part other modules may import.

It offers the identity events other modules react to (e.g. sales adopts guest
orders on :class:`EmailVerified` and removes addresses on :class:`AccountDeleted`)
and a read-only facade for account data.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.identity.domain.events import (
    AccountDeleted,
    CustomerRegistered,
    EmailVerified,
    PasswordChanged,
)
from modellbahn.modules.identity.domain.model import AccountKind, AccountStatus, StaffRole
from modellbahn.modules.identity.infrastructure.tables import accounts
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "AccountDeleted",
    "AccountKind",
    "AccountSummary",
    "CustomerRegistered",
    "EmailVerified",
    "PasswordChanged",
    "StaffRole",
    "get_account_summary",
]


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """What other modules may know about an account."""

    id: UUID
    kind: AccountKind
    email: str
    display_name: str
    role: StaffRole | None
    email_verified: bool
    active: bool


async def get_account_summary(uow: UnitOfWork, account_id: UUID) -> AccountSummary | None:
    """Read an account inside the caller's unit of work (and transaction).

    Deleted accounts are returned too, anonymised and with ``active`` false, because
    other modules keep referring to them.
    """
    statement = select(
        accounts.c.id,
        accounts.c.kind,
        accounts.c.email,
        accounts.c.display_name,
        accounts.c.role,
        accounts.c.email_verified_at,
        accounts.c.status,
    ).where(accounts.c.id == account_id)
    row = (await uow.session.execute(statement)).one_or_none()
    if row is None:
        return None
    return AccountSummary(
        id=row.id,
        kind=row.kind,
        email=row.email,
        display_name=row.display_name,
        role=row.role,
        email_verified=row.email_verified_at is not None,
        active=row.status is AccountStatus.ACTIVE,
    )
