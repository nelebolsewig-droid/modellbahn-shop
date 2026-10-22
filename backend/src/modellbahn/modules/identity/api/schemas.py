"""Request and response bodies of the identity API (snake_case JSON)."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from modellbahn.modules.identity.domain.model import (
    DISPLAY_NAME_MAX_LENGTH,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    Account,
    StaffRole,
)

# Policy-checked passwords; the domain additionally rejects the e-mail address itself.
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
# Existing passwords are not re-validated, only bounded.
CurrentPassword = Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]
DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=DISPLAY_NAME_MAX_LENGTH),
]
OneTimeToken = Annotated[str, Field(min_length=1, max_length=128)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegistrationIn(_Request):
    email: EmailStr
    password: NewPassword
    display_name: DisplayName


class EmailIn(_Request):
    email: EmailStr


class TokenIn(_Request):
    token: OneTimeToken


class LoginIn(_Request):
    email: EmailStr
    password: CurrentPassword


class DisplayNameIn(_Request):
    display_name: DisplayName


class PasswordChangeIn(_Request):
    current_password: CurrentPassword
    new_password: NewPassword


class PasswordResetConfirmIn(_Request):
    token: OneTimeToken
    new_password: NewPassword


class AccountDeletionIn(_Request):
    password: CurrentPassword


class RegistrationAcceptedOut(BaseModel):
    """Same answer whether or not the address already had an account."""

    status: Literal["pending_verification"] = "pending_verification"


class RequestAcceptedOut(BaseModel):
    """Same answer whether or not an e-mail is sent."""

    status: Literal["accepted"] = "accepted"


class AccountOut(BaseModel):
    """A customer's own account."""

    id: UUID
    email: str
    display_name: str
    email_verified: bool
    created_at: datetime

    @classmethod
    def from_account(cls, account: Account) -> Self:
        return cls(
            id=account.id,
            email=account.email,
            display_name=account.display_name,
            email_verified=account.email_verified,
            created_at=account.created_at,
        )


class StaffOut(BaseModel):
    """A staff member's own account."""

    id: UUID
    email: str
    display_name: str
    role: StaffRole

    @classmethod
    def from_account(cls, account: Account) -> Self:
        if account.role is None:
            # The database guarantees a role for every staff account.
            msg = f"staff account {account.id} has no role"
            raise ValueError(msg)
        return cls(
            id=account.id,
            email=account.email,
            display_name=account.display_name,
            role=account.role,
        )
