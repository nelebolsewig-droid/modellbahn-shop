"""FastAPI dependencies of the sales API: services, the cart cookie, idempotency keys."""

from datetime import timedelta
from typing import Annotated, Final
from uuid import UUID

from fastapi import Depends, Header, Request, Response, Security
from fastapi.security import APIKeyCookie

from modellbahn.modules.identity.contracts.auth import (
    Customer,
    StaffMember,
    StaffRole,
    customer_or_none,
    require_customer,
    require_staff,
)
from modellbahn.modules.sales.application.addresses import AddressService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.modules.sales.application.orders import OrderService
from modellbahn.modules.sales.domain.model import CART_LIFETIME
from modellbahn.platform.config import Settings
from modellbahn.platform.http import app_state
from modellbahn.platform.ratelimit import rate_limit

CART_COOKIE_NAME: Final = "mb_cart"
CART_COOKIE_MAX_AGE: Final = CART_LIFETIME + timedelta(days=1)
CHECKOUT_RATE_LIMITER: Final = "checkout_rate_limiter"
"""Name on ``app.state`` of the limiter shared by checkout and payment routes."""

# Responses that depend on the visitor (cart, orders) are never stored by caches.
PRIVATE_CACHE_CONTROL: Final = "no-store"


def get_cart_service(request: Request) -> CartService:
    return app_state(request, "cart_service", CartService)


def get_checkout_service(request: Request) -> CheckoutService:
    return app_state(request, "checkout_service", CheckoutService)


def get_order_service(request: Request) -> OrderService:
    return app_state(request, "order_service", OrderService)


def get_address_service(request: Request) -> AddressService:
    return app_state(request, "address_service", AddressService)


def get_settings(request: Request) -> Settings:
    return app_state(request, "settings", Settings)


CartServiceDep = Annotated[CartService, Depends(get_cart_service)]
CheckoutServiceDep = Annotated[CheckoutService, Depends(get_checkout_service)]
OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
AddressServiceDep = Annotated[AddressService, Depends(get_address_service)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

OptionalCustomer = Annotated[Customer | None, Depends(customer_or_none)]
CurrentCustomer = Annotated[Customer, Depends(require_customer)]
# Packers see orders and ship them; cancelling (and refunding) is for owner and staff.
OrderViewer = Annotated[
    StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF, StaffRole.PACKER))
]
OrderShipper = OrderViewer
OrderManager = Annotated[StaffMember, Depends(require_staff(StaffRole.OWNER, StaffRole.STAFF))]

limit_checkouts = rate_limit(CHECKOUT_RATE_LIMITER)

cart_cookie = APIKeyCookie(
    name=CART_COOKIE_NAME,
    scheme_name="cartCookie",
    description="The visitor's cart (set by setCartLine when it starts a cart).",
    auto_error=False,
)


def cart_id(token: Annotated[str | None, Security(cart_cookie)]) -> UUID | None:
    """The cart named by the cookie; a malformed cookie counts as no cart."""
    if not token:
        return None
    try:
        return UUID(token)
    except ValueError:
        return None


CartId = Annotated[UUID | None, Depends(cart_id)]

IdempotencyKey = Annotated[
    UUID,
    Header(
        alias="Idempotency-Key",
        description="A new UUID per intended action; repeat it when retrying the same request.",
    ),
]


def set_cart_cookie(response: Response, cart: UUID, *, secure: bool) -> None:
    response.set_cookie(
        key=CART_COOKIE_NAME,
        value=str(cart),
        max_age=int(CART_COOKIE_MAX_AGE.total_seconds()),
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )
