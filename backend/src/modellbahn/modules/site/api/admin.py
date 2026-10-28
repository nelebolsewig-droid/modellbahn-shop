"""The fairs in the Stellwerk: keep the dates, publish them, send the fair news."""

from uuid import UUID

from fastapi import APIRouter, Response, status

from modellbahn.modules.site.api.deps import (
    FairEditor,
    FairServiceDep,
    SubscriptionServiceDep,
)
from modellbahn.modules.site.api.errors import STAFF_ACCESS
from modellbahn.modules.site.api.schemas import (
    AdminFairListOut,
    AdminFairOut,
    AnnouncementOut,
    FairIn,
    SubscriptionCountsOut,
)
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin", tags=["admin-site"])


@router.get(
    "/fairs",
    operation_id="listAdminFairs",
    summary="Every fair, the latest first",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def list_fairs(_: FairEditor, service: FairServiceDep) -> AdminFairListOut:
    return AdminFairListOut(items=[AdminFairOut.from_fair(fair) for fair in await service.all()])


@router.post(
    "/fairs",
    status_code=status.HTTP_201_CREATED,
    operation_id="createFair",
    summary="Add a fair",
    responses=problems(STAFF_ACCESS),
)
async def create_fair(body: FairIn, _: FairEditor, service: FairServiceDep) -> AdminFairOut:
    fair = await service.create(body.details(), published=body.published)
    return AdminFairOut.from_fair(fair)


@router.put(
    "/fairs/{fair_id}",
    operation_id="updateFair",
    summary="Change a fair (all of its details)",
    responses=problems({**STAFF_ACCESS, 404: ["fair_not_found"]}),
)
async def update_fair(
    fair_id: UUID, body: FairIn, _: FairEditor, service: FairServiceDep
) -> AdminFairOut:
    fair = await service.change(fair_id, body.details(), published=body.published)
    return AdminFairOut.from_fair(fair)


@router.delete(
    "/fairs/{fair_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteFair",
    summary="Remove a fair",
    responses=problems({**STAFF_ACCESS, 404: ["fair_not_found"]}),
)
async def delete_fair(fair_id: UUID, _: FairEditor, service: FairServiceDep) -> Response:
    await service.delete(fair_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/fairs/{fair_id}/announcement",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="announceFair",
    summary="Mail the fair to every confirmed subscriber of the fair news (once)",
    responses=problems(
        {
            **STAFF_ACCESS,
            404: ["fair_not_found"],
            409: ["fair_not_published", "fair_past", "fair_already_announced"],
        }
    ),
)
async def announce_fair(fair_id: UUID, _: FairEditor, service: FairServiceDep) -> AnnouncementOut:
    announcement = await service.announce(fair_id)
    return AnnouncementOut(
        fair=AdminFairOut.from_fair(announcement.fair), recipients=announcement.recipients
    )


@router.get(
    "/fair-news",
    operation_id="getFairNewsCounts",
    summary="How many receive the fair news",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def fair_news_counts(_: FairEditor, service: SubscriptionServiceDep) -> SubscriptionCountsOut:
    counts = await service.counts()
    return SubscriptionCountsOut(confirmed=counts["confirmed"], pending=counts["pending"])
