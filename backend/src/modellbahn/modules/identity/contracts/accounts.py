"""Read-only facade for account data, for other modules' application and infrastructure.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.identity.domain.model import AccountKind, AccountStatus, StaffRole
from modellbahn.modules.identity.infrastructure.tables import accounts
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "ACCOUNT_REFERENCE",
    "AccountKind",
    "AccountSummary",
    "StaffRole",
    "get_account_summary",
]

ACCOUNT_REFERENCE = "identity.accounts.id"
"""Target for another module's foreign key to an account (``ON DELETE SET NULL`` or
``RESTRICT``). Importing it also puts the accounts table on the shared metadata, which
SQLAlchemy needs to resolve the key."""


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
