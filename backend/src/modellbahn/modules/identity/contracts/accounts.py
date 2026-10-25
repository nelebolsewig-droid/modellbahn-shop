"""Read-only facade for account data, for other modules' application and infrastructure.

It runs SQL, so a domain layer must not import it (the pure-domain contract says so).
"""

from collections.abc import Collection
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select

from modellbahn.modules.identity.domain.model import AccountKind, AccountStatus, StaffRole
from modellbahn.modules.identity.infrastructure.tables import accounts
from modellbahn.platform.uow import UnitOfWork

__all__ = [
    "ACCOUNT_REFERENCE",
    "CUSTOMER_KIND",
    "CUSTOMER_REFERENCE",
    "AccountKind",
    "AccountSummary",
    "StaffRole",
    "find_verified_customer",
    "get_account_summary",
    "load_display_names",
]

ACCOUNT_REFERENCE = "identity.accounts.id"
"""Target for another module's foreign key to an account (``ON DELETE SET NULL`` or
``RESTRICT``). Importing it also puts the accounts table on the shared metadata, which
SQLAlchemy needs to resolve the key."""

CUSTOMER_REFERENCE = ("identity.accounts.id", "identity.accounts.kind")
CUSTOMER_KIND = AccountKind.CUSTOMER.value
"""Target and kind for a composite foreign key ``(account_id, account_kind)`` whose kind
column is fixed to ``CUSTOMER_KIND``: the database then accepts customer accounts only."""


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


async def find_verified_customer(uow: UnitOfWork, email: str) -> UUID | None:
    """The active customer account whose verified address is ``email`` (any letter case).

    Only a verified address counts: whoever controls it may see what was ordered with it.
    """
    statement = select(accounts.c.id).where(
        accounts.c.kind == AccountKind.CUSTOMER,
        accounts.c.email == email,
        accounts.c.status == AccountStatus.ACTIVE,
        accounts.c.email_verified_at.is_not(None),
    )
    return (await uow.session.execute(statement)).scalar_one_or_none()


async def load_display_names(uow: UnitOfWork, account_ids: Collection[UUID]) -> dict[UUID, str]:
    """The display names of the accounts among ``account_ids`` (e.g. who booked a movement)."""
    ids = list(set(account_ids))
    if not ids:
        return {}
    rows = await uow.session.execute(
        select(accounts.c.id, accounts.c.display_name).where(accounts.c.id.in_(ids))
    )
    return {row.id: row.display_name for row in rows}
