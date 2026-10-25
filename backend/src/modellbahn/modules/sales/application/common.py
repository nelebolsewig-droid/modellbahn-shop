"""What the sales use cases share: the unit of work factory, order read models, fingerprints."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from modellbahn.modules.media.contracts.images import ImageView
from modellbahn.modules.sales.application.ports import SalesUnitOfWork
from modellbahn.modules.sales.domain.model import Order

type UnitOfWorkFactory = Callable[[], SalesUnitOfWork]


@dataclass(frozen=True, slots=True)
class OrderDetails:
    """An order with the images of its lines (those the media module still has, and ready)."""

    order: Order
    images: dict[UUID, ImageView]


@dataclass(frozen=True, slots=True)
class OrderPage:
    items: list[Order]
    next_cursor: str | None


async def order_details(uow: SalesUnitOfWork, order: Order) -> OrderDetails:
    ids = [line.image_asset_id for line in order.lines if line.image_asset_id is not None]
    images = await uow.images.load(ids)
    return OrderDetails(
        order=order, images={key: image for key, image in images.items() if image.is_ready}
    )


def fingerprint(request: dict[str, Any]) -> str:
    """SHA-256 of a request in canonical JSON, to tell a retry from a different request."""
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
