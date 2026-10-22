"""Operational HTTP endpoints and small helpers for the FastAPI composition."""

import asyncio
from typing import Final, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.platform.errors import ServiceUnavailableError, problem_responses

READINESS_TIMEOUT_SECONDS: Final = 2.0


def app_state[T](request: Request, name: str, expected: type[T]) -> T:
    """Typed access to an object the composition root put on ``app.state``."""
    value: object = getattr(request.app.state, name, None)
    if not isinstance(value, expected):
        msg = f"app.state.{name} is not configured with a {expected.__name__}"
        raise TypeError(msg)
    return value


class HealthOut(BaseModel):
    """Answer of the health probes."""

    status: Literal["ok"] = "ok"


router = APIRouter(tags=["system"])


@router.get("/healthz", operation_id="getHealth", summary="Liveness probe")
async def healthz() -> HealthOut:
    """The process is up and serving requests. Does not touch the database."""
    return HealthOut()


@router.get(
    "/readyz",
    operation_id="getReadiness",
    summary="Readiness probe",
    responses=problem_responses({503: ["database_unavailable"]}),
)
async def readyz(request: Request) -> HealthOut:
    """The process can serve real traffic: the database answers."""
    engine = app_state(request, "engine", AsyncEngine)
    try:
        async with asyncio.timeout(READINESS_TIMEOUT_SECONDS), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError, TimeoutError) as exc:
        raise ServiceUnavailableError(
            "The database is not reachable.", code="database_unavailable"
        ) from exc
    return HealthOut()
