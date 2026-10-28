"""The shop's public face: fairs, their calendar, the fair news sign-up and the imprint."""

from typing import Final
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from modellbahn.modules.site.api.deps import (
    FairServiceDep,
    ImprintDep,
    PublicBaseUrlDep,
    SubscriptionServiceDep,
    limit_fair_news,
)
from modellbahn.modules.site.api.schemas import (
    FairCalendarOut,
    FairOut,
    ImprintOut,
    SubscriptionIn,
    TokenIn,
)
from modellbahn.modules.site.application.ical import calendar
from modellbahn.platform.errors import FieldError, ValidationFailedError, problems

router = APIRouter(prefix="/store", tags=["store-site"])

FAIRS_CACHE_CONTROL: Final = "public, max-age=60"
IMPRINT_CACHE_CONTROL: Final = "public, max-age=300"
CALENDAR_MEDIA_TYPE: Final = "text/calendar; charset=utf-8"
_CALENDAR_CONTENT: Final = {"text/calendar": {"schema": {"type": "string"}}}


@router.get(
    "/fairs",
    operation_id="listFairs",
    summary="The fairs to come and the last ones",
    responses=problems(unsafe=False, validated=False),
)
async def list_fairs(response: Response, service: FairServiceDep) -> FairCalendarOut:
    fairs = await service.calendar()
    response.headers["Cache-Control"] = FAIRS_CACHE_CONTROL
    return FairCalendarOut(
        upcoming=[FairOut.from_fair(fair) for fair in fairs.upcoming],
        past=[FairOut.from_fair(fair) for fair in fairs.past],
    )


@router.get(
    "/fairs/calendar.ics",
    operation_id="getFairCalendar",
    summary="All fairs as a calendar to subscribe to (iCalendar)",
    response_class=Response,
    responses={
        200: {"description": "The calendar.", "content": _CALENDAR_CONTENT},
        **problems(unsafe=False, validated=False),
    },
)
async def fair_calendar(
    service: FairServiceDep, imprint: ImprintDep, base_url: PublicBaseUrlDep
) -> Response:
    body = calendar(await service.feed(), shop_name=imprint.shop_name, base_url=base_url)
    return Response(
        body,
        media_type=CALENDAR_MEDIA_TYPE,
        headers={"Cache-Control": FAIRS_CACHE_CONTROL},
    )


@router.get(
    "/fairs/{fair_id}/calendar.ics",
    operation_id="getFairEvent",
    summary="One fair as a calendar entry (iCalendar)",
    response_class=Response,
    responses={
        200: {"description": "The calendar entry.", "content": _CALENDAR_CONTENT},
        **problems({404: ["fair_not_found"]}, unsafe=False),
    },
)
async def fair_event(
    fair_id: UUID, service: FairServiceDep, imprint: ImprintDep, base_url: PublicBaseUrlDep
) -> Response:
    fair = await service.published(fair_id)
    body = calendar([fair], shop_name=imprint.shop_name, base_url=base_url)
    return Response(
        body,
        media_type=CALENDAR_MEDIA_TYPE,
        headers={
            "Cache-Control": FAIRS_CACHE_CONTROL,
            "Content-Disposition": 'attachment; filename="messe.ics"',
        },
    )


@router.post(
    "/fair-news/subscriptions",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="subscribeFairNews",
    summary="Ask for the fair news by e-mail (double opt-in)",
    responses=problems(rate_limited=True),
    dependencies=[Depends(limit_fair_news)],
)
async def subscribe(body: SubscriptionIn, service: SubscriptionServiceDep) -> None:
    """Always 202: the mail with the confirmation link goes out unless the address is
    confirmed already, and the answer never tells which."""
    if not body.consent:
        raise ValidationFailedError(
            [FieldError(field="consent", code="required", message="consent is required")]
        )
    await service.subscribe(body.email)


@router.post(
    "/fair-news/confirmations",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="confirmFairNews",
    summary="Confirm the fair news with the link from the mail",
    responses=problems({400: ["fair_news_token_invalid"]}, rate_limited=True),
    dependencies=[Depends(limit_fair_news)],
)
async def confirm(body: TokenIn, service: SubscriptionServiceDep) -> None:
    await service.confirm(body.token)


@router.post(
    "/fair-news/unsubscriptions",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="unsubscribeFairNews",
    summary="Leave the fair news with the link from any of its mails",
    responses=problems(rate_limited=True),
    dependencies=[Depends(limit_fair_news)],
)
async def unsubscribe(body: TokenIn, service: SubscriptionServiceDep) -> None:
    await service.unsubscribe(body.token)


@router.get(
    "/imprint",
    operation_id="getImprint",
    summary="Who runs the shop (provider details, § 5 DDG)",
    responses=problems(unsafe=False, validated=False),
)
async def get_imprint(response: Response, imprint: ImprintDep) -> ImprintOut:
    response.headers["Cache-Control"] = IMPRINT_CACHE_CONTROL
    return ImprintOut.from_imprint(imprint)
