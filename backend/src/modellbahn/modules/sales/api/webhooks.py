"""SumUp's calls to the shop: a checkout changed (ADR 0019).

SumUp posts ``{"event_type": "CHECKOUT_STATUS_CHANGED", "id": "<checkout>"}`` without a
signature. The shop believes none of it: the id only names which payment to ask SumUp
about. No cookie and no CSRF header arrive here (``csrf_guard`` lets ``/api/v1/webhooks/``
pass). The answer never tells whether the id was one of ours, and the checkout limiter
keeps anyone from making the shop ask SumUp over and over.
"""

import json
from typing import Final

from fastapi import APIRouter, Depends, Request, Response, status

from modellbahn.modules.sales.api.deps import PaymentServiceDep, limit_checkouts

router = APIRouter(prefix="/webhooks/sumup", tags=["webhooks"])

# SumUp's notifications are a few dozen bytes; anything far larger is not one.
_BODY_MAX_BYTES: Final = 16 * 1024
_CHECKOUT_ID_MAX_LENGTH: Final = 128


@router.post(
    "",
    include_in_schema=False,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_checkouts)],
)
async def checkout_changed(request: Request, payments: PaymentServiceDep) -> Response:
    """A checkout changed. 204 tells SumUp it arrived; the worker catches anything missed."""
    body = await request.body()
    if len(body) > _BODY_MAX_BYTES:
        return Response(status_code=status.HTTP_413_CONTENT_TOO_LARGE)
    checkout_id = _checkout_id(body)
    if checkout_id is not None:
        await payments.notify(checkout_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _checkout_id(body: bytes) -> str | None:
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("id")
    if not isinstance(value, str) or not 0 < len(value) <= _CHECKOUT_ID_MAX_LENGTH:
        return None
    return value
