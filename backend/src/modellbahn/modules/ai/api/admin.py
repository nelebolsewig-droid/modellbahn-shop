"""Product text drafts in the admin area (``/api/v1/admin/ai``, ADR 0021).

A draft never reaches the shop by itself: the Stellwerk shows it next to the current
text, saves the fields somebody takes over through the catalogue's own route, and then
records here which ones they were.
"""

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Query, status

from modellbahn.modules.ai.api.deps import CopyEditor, CopyOwner, CopyServiceDep
from modellbahn.modules.ai.api.errors import STAFF_ACCESS
from modellbahn.modules.ai.api.schemas import (
    AiRunListOut,
    AiRunOut,
    AiStatusOut,
    ApplyIn,
    CopyRequestIn,
    DraftsQueuedOut,
)
from modellbahn.modules.ai.application.copy import RECENT_LIMIT_MAX
from modellbahn.modules.ai.domain.model import Review
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin/ai", tags=["admin-ai"])

_DISABLED: Final = {409: ["ai_disabled"]}
_RUN_NOT_FOUND: Final = {404: ["ai_run_not_found"]}


@router.get(
    "/status",
    operation_id="getAiStatus",
    summary="Whether drafts can be written, the model, and the month's budget",
    responses=problems(STAFF_ACCESS, unsafe=False, validated=False),
)
async def ai_status(_: CopyEditor, service: CopyServiceDep) -> AiStatusOut:
    return AiStatusOut.from_status(await service.status())


@router.post(
    "/product-copy",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="requestProductCopy",
    summary="Ask for a text draft of a product; an open one is returned instead",
    responses=problems({**STAFF_ACCESS, **_DISABLED, 404: ["product_not_found"]}),
)
async def request_product_copy(
    body: CopyRequestIn, staff: CopyEditor, service: CopyServiceDep
) -> AiRunOut:
    run = await service.request(product_id=body.product_id, requested_by=staff.id)
    return AiRunOut.from_run(run)


@router.post(
    "/product-copy/drafts",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="requestDraftProductCopies",
    summary="Ask for a text draft of every product still in draft that has none open",
    responses=problems({**STAFF_ACCESS, **_DISABLED}, validated=False),
)
async def request_draft_product_copies(
    staff: CopyOwner, service: CopyServiceDep
) -> DraftsQueuedOut:
    return DraftsQueuedOut.from_result(await service.request_drafts(requested_by=staff.id))


@router.get(
    "/runs",
    operation_id="listAiRuns",
    summary="The newest text drafts, of one product or in one review state",
    responses=problems(STAFF_ACCESS, unsafe=False),
)
async def list_runs(
    _: CopyEditor,
    service: CopyServiceDep,
    product_id: UUID | None = None,
    review: Review | None = None,
    limit: Annotated[int, Query(ge=1, le=RECENT_LIMIT_MAX)] = 50,
) -> AiRunListOut:
    runs = await service.recent(limit=limit, product_id=product_id, review=review)
    return AiRunListOut(items=[AiRunOut.from_run(run) for run in runs])


@router.get(
    "/runs/{run_id}",
    operation_id="getAiRun",
    summary="A text draft with what the model saw and what it cost",
    responses=problems({**STAFF_ACCESS, **_RUN_NOT_FOUND}, unsafe=False),
)
async def get_run(run_id: UUID, _: CopyEditor, service: CopyServiceDep) -> AiRunOut:
    return AiRunOut.from_run(await service.get(run_id))


@router.post(
    "/runs/{run_id}/applied",
    operation_id="markAiRunApplied",
    summary="Record which fields of the draft were taken over into the product",
    responses=problems({**STAFF_ACCESS, **_RUN_NOT_FOUND, 409: ["ai_run_not_reviewable"]}),
)
async def mark_applied(
    run_id: UUID, body: ApplyIn, _: CopyEditor, service: CopyServiceDep
) -> AiRunOut:
    return AiRunOut.from_run(await service.mark_applied(run_id, fields=body.fields))


@router.post(
    "/runs/{run_id}/discarded",
    operation_id="discardAiRun",
    summary="Put the draft aside without taking anything over",
    responses=problems({**STAFF_ACCESS, **_RUN_NOT_FOUND, 409: ["ai_run_not_reviewable"]}),
)
async def discard(run_id: UUID, _: CopyEditor, service: CopyServiceDep) -> AiRunOut:
    return AiRunOut.from_run(await service.discard(run_id))
