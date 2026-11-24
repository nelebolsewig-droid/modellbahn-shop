"""The newsletter in the shop: the switch in the customer account and the mail links."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from modellbahn.modules.newsletter.api.deps import (
    CurrentReader,
    SubscriptionServiceDep,
    limit_newsletter,
)
from modellbahn.modules.newsletter.api.schemas import (
    NewsletterChoiceIn,
    NewsletterStatusOut,
    NewsletterTokenIn,
)
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/store", tags=["store-newsletter"])
# Mail programs post here without the shop's CSRF header; it reads no session, the token
# in the address is all that counts.
webhooks_router = APIRouter(prefix="/webhooks/newsletter", tags=["webhooks"])


@router.get(
    "/account/newsletter",
    operation_id="getNewsletter",
    summary="Does the logged-in customer get the newsletter?",
    responses=problems({401: ["not_authenticated"]}, unsafe=False, validated=False),
)
async def get_newsletter(
    customer: CurrentReader, service: SubscriptionServiceDep
) -> NewsletterStatusOut:
    return NewsletterStatusOut(status=(await service.status(customer.id)).value)


@router.put(
    "/account/newsletter",
    operation_id="setNewsletter",
    summary="Ask for the newsletter (double opt-in) or leave it",
    responses=problems({401: ["not_authenticated"]}),
)
async def set_newsletter(
    body: NewsletterChoiceIn, customer: CurrentReader, service: SubscriptionServiceDep
) -> NewsletterStatusOut:
    if body.subscribed:
        return NewsletterStatusOut(status=(await service.subscribe(customer.id)).value)
    await service.unsubscribe_account(customer.id)
    return NewsletterStatusOut(status="none")


@router.post(
    "/newsletter/confirmations",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="confirmNewsletter",
    summary="Confirm the newsletter with the link from the mail",
    responses=problems({400: ["newsletter_token_invalid"]}, rate_limited=True),
    dependencies=[Depends(limit_newsletter)],
)
async def confirm(body: NewsletterTokenIn, service: SubscriptionServiceDep) -> None:
    await service.confirm(body.token)


@router.post(
    "/newsletter/unsubscriptions",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="unsubscribeNewsletter",
    summary="Leave the newsletter with the link from any issue",
    responses=problems(rate_limited=True),
    dependencies=[Depends(limit_newsletter)],
)
async def unsubscribe(body: NewsletterTokenIn, service: SubscriptionServiceDep) -> None:
    await service.unsubscribe(body.token)


@webhooks_router.post(
    "/unsubscribe",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="unsubscribeNewsletterOneClick",
    summary="Leave the newsletter from the mail program's own button (RFC 8058)",
    responses=problems(rate_limited=True),
    dependencies=[Depends(limit_newsletter)],
)
async def unsubscribe_one_click(
    token: Annotated[str, Query(min_length=1, max_length=200)],
    service: SubscriptionServiceDep,
) -> None:
    """The mail program posts ``List-Unsubscribe=One-Click`` as a form; the token in the
    address is all that counts."""
    await service.unsubscribe(token)
