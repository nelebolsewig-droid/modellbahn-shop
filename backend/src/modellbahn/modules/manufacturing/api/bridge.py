"""The printer bridge reports what the printers do (ADR 0049).

``POST /api/v1/webhooks/printer-bridge`` with ``Authorization: Bearer <MB_PRINTER_BRIDGE_TOKEN>``.
No cookie and no CSRF header: the bridge is a program, not a browser (``csrf_guard`` lets
``/api/v1/webhooks/`` pass); the key is what proves it. Without a key set the endpoint
answers 404, as if it were not there.
"""

import secrets
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.manufacturing.application.bridge import (
    SLICE_FILE_MAX_LENGTH,
    BridgeState,
    Outcome,
    PrinterBridgeService,
    PrinterReport,
)
from modellbahn.platform.config import Settings
from modellbahn.platform.errors import NotFoundError, UnauthorizedError
from modellbahn.platform.http import app_state

router = APIRouter(prefix="/webhooks/printer-bridge", tags=["webhooks"])

_PRINTERS_MAX: Final = 50


class PrinterReportIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    code: str = Field(min_length=1, max_length=20)
    state: BridgeState
    task_id: str = Field(default="", max_length=200)
    slice_file: str = Field(default="", max_length=SLICE_FILE_MAX_LENGTH * 4)
    elapsed_seconds: int | None = Field(default=None, ge=0)
    remaining_seconds: int | None = Field(default=None, ge=0)
    error: str = Field(default="", max_length=200)
    volume_ml: float | None = Field(default=None, gt=0, le=100_000)
    layer_height_um: int | None = Field(default=None, gt=0, le=1000)


class BridgeReportIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    printers: list[PrinterReportIn] = Field(max_length=_PRINTERS_MAX)


class ReportResultOut(BaseModel):
    code: str
    outcome: Outcome
    job_number: int | None


class BridgeReportOut(BaseModel):
    results: list[ReportResultOut]


def _bridge_key(request: Request, authorization: Annotated[str, Header()] = "") -> None:
    settings = app_state(request, "settings", Settings)
    expected = settings.printer_bridge_token.get_secret_value()
    if not expected:
        raise NotFoundError
    scheme, _, given = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(
        given.strip().encode(), expected.encode()
    ):
        raise UnauthorizedError("The printer bridge's key is missing or wrong.")


@router.post("", include_in_schema=False, dependencies=[Depends(_bridge_key)])
async def report(body: BridgeReportIn, request: Request) -> BridgeReportOut:
    service = app_state(request, "printer_bridge_service", PrinterBridgeService)
    results = await service.sync(
        [
            PrinterReport(
                code=item.code,
                state=item.state,
                task_id=item.task_id,
                slice_file=item.slice_file,
                elapsed_seconds=item.elapsed_seconds,
                remaining_seconds=item.remaining_seconds,
                error=item.error,
                volume_ml=item.volume_ml,
                layer_height_um=item.layer_height_um,
            )
            for item in body.printers
        ]
    )
    return BridgeReportOut(
        results=[
            ReportResultOut(code=r.code, outcome=r.outcome, job_number=r.job_number)
            for r in results
        ]
    )
