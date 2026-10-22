"""Customer account API of the shop: ``/api/v1/store/account``."""

from fastapi import APIRouter, Request, Response, status

from modellbahn.modules.identity.api.deps import (
    CUSTOMER_COOKIE,
    CurrentCustomer,
    CustomerSessionToken,
    IdentityServiceDep,
    SettingsDep,
)
from modellbahn.modules.identity.api.errors import password_field, problems
from modellbahn.modules.identity.api.schemas import (
    AccountDeletionIn,
    AccountOut,
    DisplayNameIn,
    EmailIn,
    LoginIn,
    PasswordChangeIn,
    PasswordResetConfirmIn,
    RegistrationAcceptedOut,
    RegistrationIn,
    RequestAcceptedOut,
    TokenIn,
)
from modellbahn.modules.identity.domain.model import AccountKind

router = APIRouter(prefix="/store/account", tags=["store-account"])

_NOT_AUTHENTICATED = {401: ["not_authenticated"]}


@router.post(
    "/register",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="registerCustomer",
    summary="Register a customer account",
    responses=problems(),
)
async def register_customer(
    body: RegistrationIn, service: IdentityServiceDep
) -> RegistrationAcceptedOut:
    """Always 202, also for an address that already has an account (no enumeration).

    The worker then sends either the verification mail or a notice to the owner of
    the existing account.
    """
    with password_field("password"):
        await service.register_customer(
            email=body.email, password=body.password, display_name=body.display_name
        )
    return RegistrationAcceptedOut()


@router.post(
    "/email-verification",
    operation_id="verifyCustomerEmail",
    summary="Verify the e-mail address and log in",
    responses=problems({400: ["invalid_token"]}),
)
async def verify_customer_email(
    body: TokenIn,
    request: Request,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
) -> AccountOut:
    """Redeem the token from the verification mail; sets the ``mb_session`` cookie."""
    started = await service.verify_email(
        token=body.token, user_agent=request.headers.get("user-agent")
    )
    CUSTOMER_COOKIE.set(response, started.token, secure=settings.cookie_secure)
    return AccountOut.from_account(started.account)


@router.post(
    "/email-verification/resend",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="resendVerificationEmail",
    summary="Send the verification mail again",
    responses=problems(),
)
async def resend_verification_email(
    body: EmailIn, service: IdentityServiceDep
) -> RequestAcceptedOut:
    """Always 202; only unverified customer accounts get a mail."""
    await service.request_verification_mail(email=body.email)
    return RequestAcceptedOut()


@router.post(
    "/session",
    operation_id="loginCustomer",
    summary="Log in",
    responses=problems({401: ["invalid_credentials"], 403: ["email_not_verified"]}),
)
async def login_customer(
    body: LoginIn,
    request: Request,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
) -> AccountOut:
    """Sets the ``mb_session`` cookie. Locked accounts answer like wrong credentials.

    ``email_not_verified`` comes only after a correct password.
    """
    started = await service.login(
        kind=AccountKind.CUSTOMER,
        email=body.email,
        password=body.password,
        user_agent=request.headers.get("user-agent"),
    )
    CUSTOMER_COOKIE.set(response, started.token, secure=settings.cookie_secure)
    return AccountOut.from_account(started.account)


@router.delete(
    "/session",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="logoutCustomer",
    summary="Log out",
    responses=problems(validated=False),
)
async def logout_customer(
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
    token: CustomerSessionToken,
) -> None:
    """Ends the session and clears the cookie. Idempotent."""
    if token:
        await service.logout(kind=AccountKind.CUSTOMER, token=token)
    CUSTOMER_COOKIE.clear(response, secure=settings.cookie_secure)


@router.get(
    "/me",
    operation_id="getCustomerAccount",
    summary="The logged-in customer's account",
    responses=problems(_NOT_AUTHENTICATED, unsafe=False, validated=False),
)
async def get_customer_account(auth: CurrentCustomer) -> AccountOut:
    return AccountOut.from_account(auth.account)


@router.patch(
    "/me",
    operation_id="updateCustomerAccount",
    summary="Change the display name",
    responses=problems(_NOT_AUTHENTICATED),
)
async def update_customer_account(
    body: DisplayNameIn, auth: CurrentCustomer, service: IdentityServiceDep
) -> AccountOut:
    account = await service.rename(account_id=auth.account.id, display_name=body.display_name)
    return AccountOut.from_account(account)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="changeCustomerPassword",
    summary="Change the password",
    responses=problems({400: ["invalid_password"], **_NOT_AUTHENTICATED}),
)
async def change_customer_password(
    body: PasswordChangeIn, auth: CurrentCustomer, service: IdentityServiceDep
) -> None:
    """Ends every other session of the account; the worker mails a notice."""
    with password_field("new_password"):
        await service.change_password(
            account_id=auth.account.id,
            session_token_hash=auth.session_token_hash,
            current_password=body.current_password,
            new_password=body.new_password,
        )


@router.post(
    "/password-reset",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="requestPasswordReset",
    summary="Request a password reset link",
    responses=problems(),
)
async def request_password_reset(body: EmailIn, service: IdentityServiceDep) -> RequestAcceptedOut:
    """Always 202; only active customer accounts get a mail."""
    await service.request_password_reset(email=body.email)
    return RequestAcceptedOut()


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="confirmPasswordReset",
    summary="Set a new password with a reset link",
    responses=problems({400: ["invalid_token"]}),
)
async def confirm_password_reset(body: PasswordResetConfirmIn, service: IdentityServiceDep) -> None:
    """Ends every session of the account; the worker mails a notice."""
    with password_field("new_password"):
        await service.reset_password(token=body.token, new_password=body.new_password)


@router.post(
    "/me/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deleteCustomerAccount",
    summary="Delete the account",
    responses=problems({400: ["invalid_password"], **_NOT_AUTHENTICATED}),
)
async def delete_customer_account(
    body: AccountDeletionIn,
    auth: CurrentCustomer,
    response: Response,
    service: IdentityServiceDep,
    settings: SettingsDep,
) -> None:
    """Anonymises the account (GDPR), ends all sessions and clears the cookie."""
    await service.delete_account(account_id=auth.account.id, password=body.password)
    CUSTOMER_COOKIE.clear(response, secure=settings.cookie_secure)
