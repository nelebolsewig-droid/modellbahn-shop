"""Staff login for the admin area: ``/api/v1/admin/auth``. There is no self-registration."""

from fastapi import APIRouter, Depends, Request, Response, status

from modellbahn.modules.identity.api.deps import (
    STAFF_COOKIE,
    CurrentStaff,
    IdentityServiceDep,
    SettingsDep,
    StaffSessionToken,
    limit_auth_requests,
)
from modellbahn.modules.identity.api.errors import password_field
from modellbahn.modules.identity.api.schemas import LoginIn, PasswordChangeIn, StaffOut
from modellbahn.modules.identity.domain.model import AccountKind
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])

_NOT_AUTHENTICATED = {401: ["not_authenticated"]}


@router.post(
    "/session",
    operation_id="staffLogin",
    summary="Log in to the admin area",
    responses=problems({401: ["invalid_credentials"]}, rate_limited=True),
    dependencies=[Depends(limit_auth_requests)],
)
async def staff_login(
    body: LoginIn,
    request: Request,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
) -> StaffOut:
    """Sets the ``mb_admin`` cookie. Locked accounts answer like wrong credentials."""
    started = await service.login(
        kind=AccountKind.STAFF,
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
    )
    STAFF_COOKIE.set(response, started.token, secure=settings.cookie_secure)
    return StaffOut.from_account(started.account)


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="staffLogout",
    summary="Log out of the admin area",
    responses=problems(validated=False),
)
async def staff_logout(
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
    token: StaffSessionToken,
) -> None:
    """Ends the session and clears the cookie. Idempotent."""
    if token:
        await service.logout(kind=AccountKind.STAFF, token=token)
    STAFF_COOKIE.clear(response, secure=settings.cookie_secure)


@router.get(
    "/me",
    operation_id="getStaffAccount",
    summary="The logged-in staff member's account and role",
    responses=problems(_NOT_AUTHENTICATED, unsafe=False, validated=False),
)
async def get_staff_account(auth: CurrentStaff) -> StaffOut:
    return StaffOut.from_account(auth.account)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="changeStaffPassword",
    summary="Change the password",
    responses=problems({400: ["invalid_password"], **_NOT_AUTHENTICATED}),
)
async def change_staff_password(
    body: PasswordChangeIn, auth: CurrentStaff, service: IdentityServiceDep
) -> None:
    """Ends every other admin session of the account; the worker mails a notice."""
    with password_field("new_password"):
        await service.change_password(
            account_id=auth.account.id,
            session_token_hash=auth.session_token_hash,
            current_password=body.current_password,
            new_password=body.new_password,
        )
