"""Use cases of the connection to eBay: consent, business policies, location, categories."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import structlog

from modellbahn.modules.marketplace.application.access import EbayAccess
from modellbahn.modules.marketplace.application.ports import (
    EbayGateway,
    GatewayMode,
    LocationAddress,
    MarketplaceRejectedError,
    MarketplaceUnitOfWork,
    Policies,
    PolicyOption,
    TokenCipher,
    UnitOfWorkFactory,
)
from modellbahn.modules.marketplace.domain.errors import (
    ConnectionStateInvalidError,
    NotConnectedError,
)
from modellbahn.modules.marketplace.domain.model import (
    LOCATION_KEY,
    EbayAccount,
    Tokens,
    check_category_id,
)
from modellbahn.platform.clock import Clock
from modellbahn.platform.security import generate_token

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CategoryMapping:
    """A category of the shop and the eBay category its products are listed in."""

    category_id: UUID
    path: str
    ebay_category_id: str


@dataclass(frozen=True, slots=True)
class SettingsChange:
    """What the Stellwerk changes; ``None`` keeps the value, an empty policy id clears it."""

    fulfillment_policy_id: str | None = None
    payment_policy_id: str | None = None
    return_policy_id: str | None = None
    price_markup_percent: int | None = None
    made_to_order_quantity: int | None = None


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


class ConnectionService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        gateway: EbayGateway,
        access: EbayAccess,
        cipher: TokenCipher,
        clock: Clock,
        location: LocationAddress,
    ) -> None:
        self._uow = uow_factory
        self._gateway = gateway
        self._access = access
        self._cipher = cipher
        self._clock = clock
        self._location = location

    @property
    def mode(self) -> GatewayMode:
        return self._gateway.mode

    async def status(self) -> EbayAccount:
        async with self._uow() as uow:
            account = await self._account(uow)
            await uow.commit()
            return account

    async def begin_connect(self) -> str:
        """The address of eBay's consent page; its answer comes back to the callback."""
        state = generate_token()
        async with self._uow() as uow:
            account = await self._account(uow, for_update=True)
            account.begin_connect(_state_hash(state), self._clock.now())
            await uow.commit()
        return self._gateway.authorize_url(state)

    async def complete_connect(self, *, code: str, state: str) -> EbayAccount:
        """eBay's answer: the code becomes tokens, the account gets ready for offers."""
        async with self._uow() as uow:
            account = await uow.account.get(for_update=True)
            if account is None:
                raise ConnectionStateInvalidError
            try:
                account.check_state(_state_hash(state), self._clock.now())
            finally:
                # The state is used up either way.
                await uow.commit()
        grant = await self._gateway.exchange_code(code)
        seller = await self._gateway.seller_name(grant.access_token)
        now = self._clock.now()
        async with self._uow() as uow:
            account = await self._account(uow, for_update=True)
            account.connect(
                seller_name=seller,
                tokens=Tokens(
                    access_token=self._cipher.encrypt(grant.access_token),
                    access_expires_at=grant.access_expires_at,
                    refresh_token=self._cipher.encrypt(grant.refresh_token),
                    refresh_expires_at=grant.refresh_expires_at,
                ),
                now=now,
            )
            await uow.commit()
        _logger.info("marketplace.ebay.connected", seller=seller, mode=self.mode.value)
        await self._prepare(grant.access_token)
        return await self.status()

    async def disconnect(self) -> EbayAccount:
        """Take every offer off eBay, then forget the tokens and the account's settings."""
        async with self._uow() as uow:
            account = await self._account(uow)
            up = await uow.listings.up() if account.is_connected else []
        if up:
            token = await self._access.token()
            now = self._clock.now()
            for listing_id in [listing.id for listing in up]:
                async with self._uow() as uow:
                    listing = await uow.listings.get(listing_id, for_update=True)
                    if listing is None or not listing.is_up:
                        continue
                    await self._gateway.end(
                        token, group_key=listing.group_key, offer_ids=listing.offer_ids
                    )
                    uow.publish(listing.ended(now))
                    await uow.commit()
        async with self._uow() as uow:
            account = await self._account(uow, for_update=True)
            account.disconnect(self._clock.now())
            await uow.commit()
        _logger.info("marketplace.ebay.disconnected", listings_ended=len(up))
        return account

    async def change_settings(self, change: SettingsChange) -> EbayAccount:
        now = self._clock.now()
        async with self._uow() as uow:
            account = await self._account(uow, for_update=True)
            account.change_settings(
                fulfillment_policy_id=change.fulfillment_policy_id,
                payment_policy_id=change.payment_policy_id,
                return_policy_id=change.return_policy_id,
                price_markup_percent=change.price_markup_percent,
                made_to_order_quantity=change.made_to_order_quantity,
                now=now,
            )
            # Prices, quantities and policies are part of every offer.
            await uow.listings.mark_all_due(now)
            await uow.commit()
            return account

    async def policies(self) -> Policies:
        return await self._gateway.policies(await self._access.token())

    async def create_location(self) -> EbayAccount:
        await self._prepare(await self._access.token())
        return await self.status()

    async def category_map(self) -> list[CategoryMapping]:
        async with self._uow() as uow:
            labels = await uow.catalog.categories()
            mapping = await uow.categories.all()
        return [
            CategoryMapping(
                category_id=label.category_id,
                path=label.path,
                ebay_category_id=mapping.get(label.category_id, ""),
            )
            for label in labels
        ]

    async def set_category_map(self, mapping: dict[UUID, str]) -> list[CategoryMapping]:
        """Replace the whole mapping; an empty number removes a category from it."""
        cleaned = {
            category_id: check_category_id(number, field=f"categories.{category_id}")
            for category_id, number in mapping.items()
        }
        now = self._clock.now()
        async with self._uow() as uow:
            known = {label.category_id for label in await uow.catalog.categories()}
            await uow.categories.replace(
                {key: value for key, value in cleaned.items() if value and key in known}, now
            )
            await uow.listings.mark_all_due(now)
            await uow.commit()
        return await self.category_map()

    async def _prepare(self, access_token: str) -> None:
        """Create the location and pick the only policy of a kind; each may fail alone."""
        location_ready = False
        try:
            await self._gateway.ensure_location(access_token, LOCATION_KEY, self._location)
            location_ready = True
        except MarketplaceRejectedError as exc:
            _logger.warning("marketplace.ebay.location_refused", code=exc.code)
        try:
            policies = await self._gateway.policies(access_token)
        except MarketplaceRejectedError as exc:
            _logger.warning("marketplace.ebay.policies_refused", code=exc.code)
            policies = Policies(fulfillment=[], payment=[], returns=[])
        now = self._clock.now()
        async with self._uow() as uow:
            account = await self._account(uow, for_update=True)
            if not account.is_connected:
                raise NotConnectedError
            if location_ready:
                account.location_created(now)
            account.change_settings(
                fulfillment_policy_id=_only(policies.fulfillment, account.fulfillment_policy_id),
                payment_policy_id=_only(policies.payment, account.payment_policy_id),
                return_policy_id=_only(policies.returns, account.return_policy_id),
                now=now,
            )
            await uow.listings.mark_all_due(now)
            await uow.commit()

    async def _account(
        self, uow: MarketplaceUnitOfWork, *, for_update: bool = False
    ) -> EbayAccount:
        account = await uow.account.get(for_update=for_update)
        if account is None:
            account = EbayAccount.new(self._clock.now())
            uow.account.add(account)
        return account


def _only(options: Sequence[PolicyOption], current: str) -> str | None:
    """The one policy of its kind, if none is chosen yet (else leave the choice alone)."""
    if current or len(options) != 1:
        return None
    return options[0].id
