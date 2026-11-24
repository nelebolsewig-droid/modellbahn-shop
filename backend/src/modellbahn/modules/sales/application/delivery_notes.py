"""Delivery notes for the parcel, drawn on demand (ADR 0047)."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from starlette.concurrency import run_in_threadpool

from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.domain.delivery_notes import DeliveryNote, Sender, delivery_note
from modellbahn.modules.sales.domain.errors import OrderNotFoundError
from modellbahn.platform.clock import Clock


class DeliveryNoteRenderer(Protocol):
    def render(self, note: DeliveryNote) -> bytes: ...


@dataclass(frozen=True, slots=True)
class DeliveryNoteFile:
    filename: str
    document: bytes


class DeliveryNoteService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        renderer: DeliveryNoteRenderer,
        sender: Sender,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._renderer = renderer
        self._sender = sender

    async def for_order(self, order_id: UUID) -> DeliveryNoteFile:
        """The note of a paid or shipped order as a PDF; nothing is stored."""
        async with self._uow() as uow:
            order = await uow.orders.get(order_id)
        if order is None:
            raise OrderNotFoundError
        note = delivery_note(order, sender=self._sender, printed_at=self._clock.now())
        document = await run_in_threadpool(self._renderer.render, note)
        return DeliveryNoteFile(filename=note.filename, document=document)
