"""Assembling the marketplace from the settings, for the API and the worker alike."""

from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.marketplace.application.access import EbayAccess
from modellbahn.modules.marketplace.application.connection import ConnectionService
from modellbahn.modules.marketplace.application.deletions import (
    AccountDeletionService,
    TestBuyer,
)
from modellbahn.modules.marketplace.application.listings import ListingService
from modellbahn.modules.marketplace.application.marketplace import Marketplace
from modellbahn.modules.marketplace.application.orders import MarketplaceOrderService
from modellbahn.modules.marketplace.application.ports import (
    EbayGateway,
    GatewayMode,
    LocationAddress,
    UnitOfWorkFactory,
)
from modellbahn.modules.marketplace.infrastructure.builtin import (
    TEST_BUYER_NAME,
    BuiltInEbayGateway,
    sign_test_notification,
)
from modellbahn.modules.marketplace.infrastructure.ebay import HttpEbayGateway
from modellbahn.modules.marketplace.infrastructure.notifications import (
    EcdsaNotificationSignatures,
)
from modellbahn.modules.marketplace.infrastructure.repositories import (
    image_base_url,
    marketplace_uow_factory,
)
from modellbahn.modules.marketplace.infrastructure.tokens import FernetTokenCipher
from modellbahn.platform.clock import Clock
from modellbahn.platform.config import MarketplaceMode, Settings

CALLBACK_PATH: Final = "/api/v1/admin/marketplace/ebay/callback"
# eBay's notifications of closed accounts; webhooks pass without the CSRF header.
ACCOUNT_DELETION_PATH: Final = "/api/v1/webhooks/ebay/account-deletion"
# What a buyer pays for shipping on the test marketplace (the shop's rate within Germany).
TEST_SHIPPING_CENTS: Final = 590
_COUNTRY_CODES: Final = {"deutschland": "DE", "germany": "DE", "österreich": "AT", "austria": "AT"}


def build_marketplace(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession], clock: Clock
) -> Marketplace | None:
    """The marketplace, or None with ``MB_EBAY_MODE=off``."""
    if settings.ebay_mode is MarketplaceMode.OFF:
        return None
    uow_factory = _uow_factory(settings, session_factory)
    gateway: EbayGateway
    if settings.ebay_mode is MarketplaceMode.TEST:
        gateway = BuiltInEbayGateway(
            session_factory=session_factory,
            callback_url=f"{settings.public_base_url}{CALLBACK_PATH}",
            clock=clock,
        )
    else:
        gateway = HttpEbayGateway(
            mode=GatewayMode(settings.ebay_mode.value),
            client_id=settings.ebay_client_id.strip(),
            client_secret=settings.ebay_client_secret.get_secret_value().strip(),
            ru_name=settings.ebay_ru_name.strip(),
        )
    cipher = FernetTokenCipher(settings.ebay_token_key.get_secret_value())
    access = EbayAccess(uow_factory=uow_factory, gateway=gateway, cipher=cipher, clock=clock)
    imprint = settings.imprint
    return Marketplace(
        uow_factory=uow_factory,
        gateway=gateway,
        access=access,
        connection=ConnectionService(
            uow_factory=uow_factory,
            gateway=gateway,
            access=access,
            cipher=cipher,
            clock=clock,
            location=LocationAddress(
                name=settings.shop_name,
                street=imprint.street,
                postal_code=imprint.postal_code,
                city=imprint.city,
                country_code=_COUNTRY_CODES.get(imprint.country.casefold(), "DE"),
            ),
        ),
        listings=ListingService(
            uow_factory=uow_factory,
            gateway=gateway,
            access=access,
            clock=clock,
            brand=settings.shop_name,
        ),
        orders=MarketplaceOrderService(
            uow_factory=uow_factory,
            gateway=gateway,
            access=access,
            clock=clock,
            test_shipping_cents=TEST_SHIPPING_CENTS,
        ),
    )


def build_account_deletions(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    marketplace: Marketplace | None,
    clock: Clock,
) -> AccountDeletionService:
    """The endpoint for eBay's notifications of closed accounts, in every mode.

    eBay checks the endpoint before it enables the production keys, so it answers while
    eBay is still off; signatures can be checked once a gateway exists.
    """
    gateway = marketplace.gateway if marketplace is not None else None
    return AccountDeletionService(
        uow_factory=(
            marketplace.uow_factory
            if marketplace is not None
            else _uow_factory(settings, session_factory)
        ),
        signatures=EcdsaNotificationSignatures(gateway) if gateway is not None else None,
        verification_token=settings.ebay_verification_token.get_secret_value(),
        endpoint=f"{settings.public_base_url}{ACCOUNT_DELETION_PATH}",
        clock=clock,
        test_buyer=(
            TestBuyer(name=TEST_BUYER_NAME, sign=sign_test_notification)
            if isinstance(gateway, BuiltInEbayGateway)
            else None
        ),
    )


def _uow_factory(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> UnitOfWorkFactory:
    return marketplace_uow_factory(
        session_factory,
        image_base_url=image_base_url(
            public_base_url=settings.public_base_url,
            media_public_base_url=settings.media_public_base_url,
        ),
    )
