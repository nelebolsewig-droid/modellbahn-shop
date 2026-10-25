"""The customer's orders and address book (``/api/v1/store/account``)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from modellbahn.modules.sales.api.deps import (
    PRIVATE_CACHE_CONTROL,
    AddressServiceDep,
    CurrentCustomer,
    OrderServiceDep,
)
from modellbahn.modules.sales.api.errors import CUSTOMER_ACCESS, ORDER_NOT_FOUND
from modellbahn.modules.sales.api.schemas import (
    CustomerAddressIn,
    CustomerAddressOut,
    CustomerAddressPatchIn,
    OrderOut,
    OrderPageOut,
)
from modellbahn.modules.sales.domain.model import CustomerAddress
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/store/account", tags=["store-account"])

_ADDRESS_NOT_FOUND = {404: ["address_not_found"]}


def _book(entries: list[CustomerAddress], response: Response) -> list[CustomerAddressOut]:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL
    return [CustomerAddressOut.from_entry(entry) for entry in entries]


@router.get(
    "/orders",
    operation_id="listMyOrders",
    summary="The customer's orders, including adopted guest orders, newest first",
    responses=problems(CUSTOMER_ACCESS, unsafe=False),
)
async def list_my_orders(
    customer: CurrentCustomer,
    service: OrderServiceDep,
    response: Response,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> OrderPageOut:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL
    page = await service.customer_orders(customer.id, cursor=cursor, limit=limit)
    return OrderPageOut.from_page(page)


@router.get(
    "/orders/{number}",
    operation_id="getMyOrder",
    summary="One of the customer's orders",
    responses=problems({**CUSTOMER_ACCESS, **ORDER_NOT_FOUND}, unsafe=False),
)
async def get_my_order(
    number: str, customer: CurrentCustomer, service: OrderServiceDep, response: Response
) -> OrderOut:
    response.headers["Cache-Control"] = PRIVATE_CACHE_CONTROL
    return OrderOut.from_details(await service.customer_order(customer.id, number))


@router.get(
    "/addresses",
    operation_id="listAddresses",
    summary="The address book, the default first",
    responses=problems(CUSTOMER_ACCESS, unsafe=False, validated=False),
)
async def list_addresses(
    customer: CurrentCustomer, service: AddressServiceDep, response: Response
) -> list[CustomerAddressOut]:
    return _book(await service.book(customer.id), response)


@router.post(
    "/addresses",
    status_code=status.HTTP_201_CREATED,
    operation_id="addAddress",
    summary="Add an address; answers with the whole book",
    responses=problems({**CUSTOMER_ACCESS, 409: ["address_book_full"]}),
)
async def add_address(
    body: CustomerAddressIn,
    customer: CurrentCustomer,
    service: AddressServiceDep,
    response: Response,
) -> list[CustomerAddressOut]:
    """The first address of a book becomes its default."""
    book = await service.add(
        customer.id, label=body.label, address=body.to_input(), default=body.is_default
    )
    return _book(book, response)


@router.patch(
    "/addresses/{address_id}",
    operation_id="changeAddress",
    summary="Change an address or make it the default; answers with the whole book",
    responses=problems({**CUSTOMER_ACCESS, **_ADDRESS_NOT_FOUND}),
)
async def change_address(
    address_id: UUID,
    body: CustomerAddressPatchIn,
    customer: CurrentCustomer,
    service: AddressServiceDep,
    response: Response,
) -> list[CustomerAddressOut]:
    book = await service.change(
        customer.id,
        address_id,
        label=body.label,
        address=body.address.to_input() if body.address else None,
        default=body.is_default,
    )
    return _book(book, response)


@router.delete(
    "/addresses/{address_id}",
    operation_id="removeAddress",
    summary="Remove an address; answers with the whole book",
    responses=problems({**CUSTOMER_ACCESS, **_ADDRESS_NOT_FOUND}),
)
async def remove_address(
    address_id: UUID, customer: CurrentCustomer, service: AddressServiceDep, response: Response
) -> list[CustomerAddressOut]:
    """If it was the default, the oldest remaining address takes over."""
    return _book(await service.remove(customer.id, address_id), response)
