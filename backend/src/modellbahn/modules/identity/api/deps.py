"""FastAPI dependencies of the identity API: the service, session cookies, current account."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Literal

from fastapi import Depends, Request, Response, Security
from fastapi.security import APIKeyCookie

from modellbahn.modules.identity.application.services import Authentication, IdentityService
from modellbahn.modules.identity.domain.errors import NotAuthenticatedError
from modellbahn.modules.identity.domain.model import (
    CUSTOMER_SESSION_LIFETIME,
    STAFF_SESSION_LIFETIME,
    AccountKind,
)
from modellbahn.platform.config import Settings
from modellbahn.platform.errors import UnauthorizedError
from modellbahn.platform.http import app_state
from modellbahn.platform.ratelimit import rate_limit


def get_identity_service(request: Request) -> IdentityService:
    return app_state(request, "identity_service", IdentityService)


def get_settings(request: Request) -> Settings:
    return app_state(request, "settings", Settings)


IdentityServiceDep = Annotated[IdentityService, Depends(get_identity_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

AUTH_RATE_LIMITER = "auth_rate_limiter"
"""Name on ``app.state`` of the limiter shared by login, registration and reset routes."""

# Logins, registrations, verifications and reset requests of one client address
# count together: guessing passwords on many accounts and mass-mailing both show up.
limit_auth_requests = rate_limit(AUTH_RATE_LIMITER)


@dataclass(frozen=True, slots=True)
class SessionCookie:
    """The cookie that carries the session token of one area (shop or admin)."""

    name: str
    kind: AccountKind
    max_age: timedelta
    same_site: Literal["lax", "strict"]

    def set(self, response: Response, token: str, *, secure: bool) -> None:
        response.set_cookie(
            key=self.name,
            value=token,
            max_age=int(self.max_age.total_seconds()),
            path="/",
            secure=secure,
            httponly=True,
            samesite=self.same_site,
        )

    def clear(self, response: Response, *, secure: bool) -> None:
        response.delete_cookie(
            key=self.name, path="/", secure=secure, httponly=True, samesite=self.same_site
        )

    def clearing_headers(self, *, secure: bool) -> dict[str, str]:
        """``Set-Cookie`` header that removes the cookie, for error responses."""
        response = Response()
        self.clear(response, secure=secure)
        return {"set-cookie": response.headers["set-cookie"]}


CUSTOMER_COOKIE = SessionCookie(
    name="mb_session", kind=AccountKind.CUSTOMER, max_age=CUSTOMER_SESSION_LIFETIME, same_site="lax"
)
STAFF_COOKIE = SessionCookie(
    name="mb_admin", kind=AccountKind.STAFF, max_age=STAFF_SESSION_LIFETIME, same_site="strict"
)

# Declared as API-key cookies so that the OpenAPI document shows which routes need them.
customer_session = APIKeyCookie(
    name=CUSTOMER_COOKIE.name,
    scheme_name="customerSession",
    description="Session cookie of the shop (set by loginCustomer and verifyCustomerEmail).",
    auto_error=False,
)
staff_session = APIKeyCookie(
    name=STAFF_COOKIE.name,
    scheme_name="staffSession",
    description="Session cookie of the admin area (set by staffLogin).",
    auto_error=False,
)

CustomerSessionToken = Annotated[str | None, Security(customer_session)]
StaffSessionToken = Annotated[str | None, Security(staff_session)]


async def _authenticate(
    service: IdentityService, cookie: SessionCookie, token: str | None, *, secure: bool
) -> Authentication:
    if not token:
        raise UnauthorizedError("You are not logged in.", code="not_authenticated")
    try:
        return await service.authenticate(kind=cookie.kind, token=token)
    except NotAuthenticatedError:
        # Remove the stale cookie, so the frontend's routing stops treating it as a login.
        raise UnauthorizedError(
            "Your session is no longer valid.",
            code="not_authenticated",
            headers=cookie.clearing_headers(secure=secure),
        ) from None


async def current_customer(
    service: IdentityServiceDep, settings: SettingsDep, token: CustomerSessionToken
) -> Authentication:
    """The logged-in customer; 401 ``not_authenticated`` otherwise."""
    return await _authenticate(service, CUSTOMER_COOKIE, token, secure=settings.cookie_secure)


async def current_staff(
    service: IdentityServiceDep, settings: SettingsDep, token: StaffSessionToken
) -> Authentication:
    """The logged-in staff member; 401 ``not_authenticated`` otherwise."""
    return await _authenticate(service, STAFF_COOKIE, token, secure=settings.cookie_secure)


CurrentCustomer = Annotated[Authentication, Depends(current_customer)]
CurrentStaff = Annotated[Authentication, Depends(current_staff)]


async def staff_session_is_valid(request: Request) -> bool:
    """Whether the admin session of ``request`` is still valid (re-checked by open streams)."""
    token = request.cookies.get(STAFF_COOKIE.name)
    if not token:
        return False
    try:
        await get_identity_service(request).authenticate(kind=STAFF_COOKIE.kind, token=token)
    except NotAuthenticatedError:
        return False
    return True
