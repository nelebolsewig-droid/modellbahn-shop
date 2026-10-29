"""The built-in test marketplace (``MB_EBAY_MODE=test``): eBay's flow without eBay.

Connecting skips eBay's consent page and lands on the callback at once. Listings "go up"
with made-up numbers, and orders are the sales recorded in ``marketplace.test_sales``
(the Stellwerk sells there as a buyer on eBay would). Nothing leaves the server, so the
whole chain from offer to shipment runs in development, in the smoke test and in CI.

Notifications of closed accounts are signed with a test key derived from a fixed seed,
so the same signature check as with eBay runs, and tests can sign their own.
"""

import base64
import hashlib
import json
from datetime import datetime, timedelta
from functools import cache
from typing import Final
from urllib.parse import urlencode

import structlog
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modellbahn.modules.marketplace.application.ports import (
    AccessGrant,
    ExternalLine,
    ExternalOrder,
    GatewayMode,
    ListingDraft,
    LocationAddress,
    MarketplaceRejectedError,
    NotificationKey,
    Policies,
    PolicyOption,
    PublishedListing,
    ShipmentReport,
    TokenGrant,
)
from modellbahn.modules.marketplace.infrastructure.tables import test_sales
from modellbahn.platform.clock import Clock

_logger = structlog.get_logger(__name__)

CONSENT_CODE: Final = "test-consent"
SELLER_NAME: Final = "adp-modelle-test"
TEST_BUYER_NAME: Final = "erika_testkauf"
"""The buyer of every test sale."""
TEST_NOTIFICATION_KEY_ID: Final = "test-marketplace-1"
# The test marketplace signs its notifications with a key anyone can derive from this
# seed, so tests can sign too. Test mode never runs in production (Settings refuse it).
_TEST_SIGNING_SEED: Final = b"modellbahn-shop: notifications of the test marketplace"
_P256_ORDER: Final = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_ACCESS_LIFETIME: Final = timedelta(hours=2)
_REFRESH_LIFETIME: Final = timedelta(days=548)


def _digits(text: str, count: int) -> str:
    number = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8])
    return f"{number % 10**count:0{count}d}"


@cache
def _test_signing_key() -> ec.EllipticCurvePrivateKey:
    secret = int.from_bytes(hashlib.sha256(_TEST_SIGNING_SEED).digest()) % (_P256_ORDER - 1)
    return ec.derive_private_key(secret + 1, ec.SECP256R1())


def sign_test_notification(body: bytes) -> str:
    """The ``X-EBAY-SIGNATURE`` header eBay would send with this body, from the test key."""
    signature = _test_signing_key().sign(body, ec.ECDSA(hashes.SHA1()))  # noqa: S303 - eBay's digest
    header = {
        "alg": "ecdsa",
        "kid": TEST_NOTIFICATION_KEY_ID,
        "signature": base64.b64encode(signature).decode(),
        "digest": "SHA1",
    }
    return base64.b64encode(json.dumps(header).encode()).decode()


def public_test_key() -> NotificationKey:
    """The test key's public half, on one line as eBay's Notification API hands keys out."""
    der = (
        _test_signing_key()
        .public_key()
        .public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    pem = f"-----BEGIN PUBLIC KEY-----{base64.b64encode(der).decode()}-----END PUBLIC KEY-----"
    return NotificationKey(pem=pem, algorithm="ECDSA", digest="SHA1")


class BuiltInEbayGateway:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        callback_url: str,
        clock: Clock,
    ) -> None:
        self._session_factory = session_factory
        self._callback_url = callback_url
        self._clock = clock

    @property
    def mode(self) -> GatewayMode:
        return GatewayMode.TEST

    def authorize_url(self, state: str) -> str:
        return f"{self._callback_url}?{urlencode({'code': CONSENT_CODE, 'state': state})}"

    async def exchange_code(self, code: str) -> TokenGrant:
        if code != CONSENT_CODE:
            raise MarketplaceRejectedError("invalid_grant", "the consent code is not valid")
        now = self._clock.now()
        return TokenGrant(
            access_token=f"test-access-{_digits(str(now), 8)}",
            access_expires_at=now + _ACCESS_LIFETIME,
            refresh_token="test-refresh",  # noqa: S106 - the test marketplace's own
            refresh_expires_at=now + _REFRESH_LIFETIME,
        )

    async def refresh(self, refresh_token: str) -> AccessGrant:
        now = self._clock.now()
        return AccessGrant(
            access_token=f"test-access-{_digits(str(now), 8)}",
            access_expires_at=now + _ACCESS_LIFETIME,
        )

    async def seller_name(self, access_token: str) -> str:
        return SELLER_NAME

    async def policies(self, access_token: str) -> Policies:
        return Policies(
            fulfillment=[
                PolicyOption(id="test-ship-dhl", name="DHL Paket, 1 bis 2 Werktage"),
                PolicyOption(id="test-ship-made", name="Auf Bestellung, bis 10 Werktage"),
            ],
            payment=[PolicyOption(id="test-pay", name="eBay-Zahlungsabwicklung")],
            returns=[PolicyOption(id="test-return-30", name="30 Tage Rückgabe")],
        )

    async def ensure_location(self, access_token: str, key: str, address: LocationAddress) -> None:
        _logger.info("marketplace.test.location", key=key, city=address.city)

    async def publish(self, access_token: str, draft: ListingDraft) -> PublishedListing:
        offer_ids = {
            offer.sku: draft.known_offer_ids.get(offer.sku) or f"T{_digits(offer.sku, 10)}"
            for offer in draft.offers
        }
        # One listing per shape: switching between one and several choices gives a new one.
        shape = "group" if len(draft.offers) > 1 else "single"
        external_id = f"99{_digits(f'{draft.group_key}:{shape}', 10)}"
        _logger.info(
            "marketplace.test.published",
            group_key=draft.group_key,
            external_id=external_id,
            offers=len(offer_ids),
        )
        return PublishedListing(external_id=external_id, offer_ids=offer_ids)

    async def end(self, access_token: str, *, group_key: str, offer_ids: dict[str, str]) -> None:
        _logger.info("marketplace.test.ended", group_key=group_key)

    async def orders(
        self, access_token: str, *, modified_since: datetime, until: datetime
    ) -> list[ExternalOrder]:
        async with self._session_factory() as session:
            rows = await session.execute(
                select(test_sales)
                # Both ends count, as in eBay's filter lastmodifieddate:[from..to].
                .where(test_sales.c.modified_at.between(modified_since, until))
                .order_by(test_sales.c.created_at, test_sales.c.id)
            )
            sales = rows.all()
        return [
            ExternalOrder(
                external_id=sale.external_id,
                # The test buyer, at a made-up address the shop ships to.
                buyer_name=TEST_BUYER_NAME,
                email="testkauf@example.com",
                recipient="Erika Mustermann",
                street="Teststraße 1",
                postal_code="10115",
                city="Berlin",
                country_code="DE",
                shipping_cents=sale.shipping_cents,
                paid=True,
                cancelled=sale.cancelled_at is not None,
                paid_at=sale.created_at,
                lines=[
                    ExternalLine(
                        line_ref=f"{sale.external_id}-1",
                        sku=sale.sku,
                        title=f"Testkauf {sale.sku}",
                        quantity=sale.quantity,
                        unit_price_cents=sale.unit_price_cents,
                    )
                ],
            )
            for sale in sales
        ]

    async def notification_key(self, key_id: str) -> NotificationKey:
        if key_id != TEST_NOTIFICATION_KEY_ID:
            raise MarketplaceRejectedError("unknown_key", "the test marketplace has one key")
        return public_test_key()

    async def aclose(self) -> None:
        return None

    async def report_shipment(self, access_token: str, report: ShipmentReport) -> None:
        _logger.info(
            "marketplace.test.shipment_reported",
            external_id=report.external_id,
            carrier=report.carrier,
        )
