"""Use cases of the cart: read it with current prices, change quantities, clean up."""

from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.contracts.availability import Availability, availability
from modellbahn.modules.media.contracts.images import ImageView
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.application.ports import SalesUnitOfWork
from modellbahn.modules.sales.domain.errors import (
    InsufficientStockError,
    VariantUnavailableError,
)
from modellbahn.modules.sales.domain.model import (
    DEFAULT_COUNTRY,
    Cart,
    ShippingZone,
    Totals,
    shipping_zone,
)
from modellbahn.platform.clock import Clock


@dataclass(frozen=True, slots=True)
class CartItem:
    """A cart line with the variant as the catalogue sells it now."""

    variant: SaleVariant
    quantity: int
    image: ImageView | None
    free_units: int

    @property
    def availability(self) -> Availability:
        """How the quantity can be delivered: from stock, made to order, or not at all."""
        if not self.variant.purchasable:
            return Availability.UNAVAILABLE
        return availability(
            free_units=self.free_units,
            wanted=self.quantity,
            allow_backorder=self.variant.allow_backorder,
        )

    @property
    def available(self) -> bool:
        """For sale, and deliverable in this quantity."""
        return self.availability is not Availability.UNAVAILABLE

    @property
    def line_total_cents(self) -> int:
        return self.variant.price_cents * self.quantity


@dataclass(frozen=True, slots=True)
class CartView:
    """The cart priced from the catalogue, with shipping to the default country.

    Lines whose variant no longer exists are left out; lines that cannot be bought any
    more stay visible (so the customer sees what is gone) but do not count.
    """

    cart_id: UUID | None
    items: list[CartItem]
    totals: Totals
    shipping_zone: ShippingZone

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items if item.available)

    @property
    def ready_for_checkout(self) -> bool:
        return bool(self.items) and all(item.available for item in self.items)


async def price_cart(uow: SalesUnitOfWork, cart: Cart | None) -> CartView:
    zone = shipping_zone(DEFAULT_COUNTRY)
    lines = cart.lines if cart is not None else []
    variants = await uow.catalog.sale_variants([line.variant_id for line in lines])
    images = await uow.images.load(
        [v.image_asset_id for v in variants.values() if v.image_asset_id is not None]
    )
    free = await uow.inventory.free_units(variants)
    items = [
        CartItem(
            variant=variant,
            quantity=line.quantity,
            image=_ready(images.get(variant.image_asset_id)) if variant.image_asset_id else None,
            free_units=free.get(variant.variant_id, 0),
        )
        for line in sorted(lines, key=lambda line: line.added_at)
        if (variant := variants.get(line.variant_id)) is not None
    ]
    subtotal = sum(item.line_total_cents for item in items if item.available)
    return CartView(
        cart_id=cart.id if cart is not None else None,
        items=items,
        totals=Totals.of(subtotal, zone),
        shipping_zone=zone,
    )


async def _check_deliverable(uow: SalesUnitOfWork, variant_id: UUID, quantity: int) -> None:
    variant = (await uow.catalog.sale_variants([variant_id])).get(variant_id)
    if variant is None or not variant.purchasable:
        raise VariantUnavailableError(variant_id)
    free = (await uow.inventory.free_units([variant_id])).get(variant_id, 0)
    deliverable = availability(
        free_units=free, wanted=quantity, allow_backorder=variant.allow_backorder
    )
    if deliverable is Availability.UNAVAILABLE:
        raise InsufficientStockError({variant_id: free})


def _ready(image: ImageView | None) -> ImageView | None:
    return image if image is not None and image.is_ready else None


class CartService:
    """The visitor's cart. Its id travels in a cookie; a missing or expired cart is empty."""

    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def view(self, cart_id: UUID | None) -> CartView:
        async with self._uow() as uow:
            cart = await self._live_cart(uow, cart_id, for_update=False)
            return await price_cart(uow, cart)

    async def set_quantity(self, cart_id: UUID | None, variant_id: UUID, quantity: int) -> CartView:
        """Put ``quantity`` pieces in the cart, starting a new cart if there is none.

        Only variants on sale go in, and more than the shelves hold only if the variant
        is made to order. Taking something out always works.
        """
        now = self._clock.now()
        async with self._uow() as uow:
            cart = await self._live_cart(uow, cart_id, for_update=True)
            line = cart.line_for(variant_id) if cart is not None else None
            if quantity > (line.quantity if line is not None else 0):
                await _check_deliverable(uow, variant_id, quantity)
            if cart is None:
                if quantity == 0:
                    return await price_cart(uow, None)
                cart = Cart.start(now)
                uow.carts.add(cart)
            cart.set_quantity(variant_id, quantity, now)
            await uow.commit()
            return await price_cart(uow, cart)

    async def purge_expired(self) -> int:
        """Remove expired carts (a periodic job of the worker)."""
        async with self._uow() as uow:
            removed = await uow.carts.delete_expired(self._clock.now())
            await uow.commit()
            return removed

    async def _live_cart(
        self, uow: SalesUnitOfWork, cart_id: UUID | None, *, for_update: bool
    ) -> Cart | None:
        if cart_id is None:
            return None
        cart = await uow.carts.get(cart_id, for_update=for_update)
        if cart is None or cart.is_expired(self._clock.now()):
            return None
        return cart
