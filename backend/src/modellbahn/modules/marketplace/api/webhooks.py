"""eBay's calls to the shop: the notifications of closed accounts (ADR 0015).

No cookie and no CSRF header arrive here; eBay's signature is the proof. These routes
therefore never look at a session (``csrf_guard`` lets ``/api/v1/webhooks/`` pass).
"""

from typing import Annotated, Final

from fastapi import APIRouter, Header, Query, Request, Response, status
from fastapi.responses import JSONResponse

from modellbahn.modules.marketplace.api.deps import AccountDeletionsDep

router = APIRouter(prefix="/webhooks/ebay", tags=["webhooks"])

# eBay's notifications are a few hundred bytes; anything far larger is not one.
_BODY_MAX_BYTES: Final = 64 * 1024


@router.get("/account-deletion", include_in_schema=False)
async def check_endpoint(
    deletions: AccountDeletionsDep,
    challenge_code: Annotated[str, Query(min_length=1, max_length=512)],
) -> JSONResponse:
    """eBay's check that the endpoint belongs to the app: answer with the hash it expects."""
    return JSONResponse({"challengeResponse": deletions.challenge_response(challenge_code)})


@router.post("/account-deletion", include_in_schema=False, status_code=status.HTTP_204_NO_CONTENT)
async def account_deleted(
    request: Request,
    deletions: AccountDeletionsDep,
    signature: Annotated[str, Header(alias="X-EBAY-SIGNATURE", max_length=4096)] = "",
) -> Response:
    """A user closed their eBay account. 204 tells eBay it arrived; otherwise eBay retries."""
    body = await request.body()
    if len(body) > _BODY_MAX_BYTES:
        return Response(status_code=status.HTTP_413_CONTENT_TOO_LARGE)
    await deletions.receive(body, signature)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
