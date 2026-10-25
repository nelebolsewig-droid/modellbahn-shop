"""Use cases of the address book: a customer's shipping addresses, one of them the default."""

from uuid import UUID

from modellbahn.modules.sales.application.checkout import AddressInput
from modellbahn.modules.sales.application.common import UnitOfWorkFactory
from modellbahn.modules.sales.domain.errors import AddressNotFoundError
from modellbahn.modules.sales.domain.model import CustomerAddress, after_removal, make_default
from modellbahn.platform.clock import Clock


class AddressService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock

    async def book(self, account_id: UUID) -> list[CustomerAddress]:
        """The addresses, the default first, then oldest first."""
        async with self._uow() as uow:
            return _ordered(await uow.addresses.book(account_id))

    async def add(
        self, account_id: UUID, *, label: str, address: AddressInput, default: bool
    ) -> list[CustomerAddress]:
        now = self._clock.now()
        async with self._uow() as uow:
            book = await uow.addresses.book(account_id, for_update=True)
            entry = CustomerAddress.create(
                account_id=account_id,
                label=label,
                address=address.to_address(),
                existing=book,
                now=now,
            )
            uow.addresses.add(entry)
            book.append(entry)
            if default:
                make_default(book, entry.id, now)
            await uow.commit()
            return _ordered(book)

    async def change(
        self,
        account_id: UUID,
        address_id: UUID,
        *,
        label: str | None,
        address: AddressInput | None,
        default: bool,
    ) -> list[CustomerAddress]:
        """Change texts and/or make the entry the default (only ``True`` changes the default)."""
        now = self._clock.now()
        async with self._uow() as uow:
            book = await uow.addresses.book(account_id, for_update=True)
            entry = _entry(book, address_id)
            if label is not None or address is not None:
                entry.change(
                    label=entry.label if label is None else label,
                    address=entry.address if address is None else address.to_address(),
                    now=now,
                )
            if default:
                make_default(book, entry.id, now)
            await uow.commit()
            return _ordered(book)

    async def remove(self, account_id: UUID, address_id: UUID) -> list[CustomerAddress]:
        now = self._clock.now()
        async with self._uow() as uow:
            book = await uow.addresses.book(account_id, for_update=True)
            entry = _entry(book, address_id)
            await uow.addresses.delete(entry)
            book.remove(entry)
            after_removal(book, now)
            await uow.commit()
            return _ordered(book)


def _entry(book: list[CustomerAddress], address_id: UUID) -> CustomerAddress:
    # Only the account's own book is searched: another customer's id is "not found".
    entry = next((a for a in book if a.id == address_id), None)
    if entry is None:
        raise AddressNotFoundError
    return entry


def _ordered(book: list[CustomerAddress]) -> list[CustomerAddress]:
    return sorted(book, key=lambda a: (not a.is_default, a.created_at))
