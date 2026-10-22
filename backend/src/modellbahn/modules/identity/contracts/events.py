"""Identity events and the types they carry, for other modules to react to.

Plain Python like the domain it comes from: importing it keeps a domain layer pure.
"""

from modellbahn.modules.identity.domain.events import (
    AccountDeleted,
    CustomerRegistered,
    EmailVerified,
    PasswordChanged,
)
from modellbahn.modules.identity.domain.model import AccountKind, StaffRole

__all__ = [
    "AccountDeleted",
    "AccountKind",
    "CustomerRegistered",
    "EmailVerified",
    "PasswordChanged",
    "StaffRole",
]
