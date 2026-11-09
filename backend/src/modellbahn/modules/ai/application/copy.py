"""Product texts from the model (ADR 0021): ask for a draft, write it, review it.

:class:`CopyService` serves the Stellwerk: it queues runs and records what people did
with a draft. :class:`CopyWorker` runs in the worker: it takes one queued run after the
other, calls the model and stores the draft. Both refuse to spend money past the
month's budget.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID

import structlog

from modellbahn.modules.ai.application.ports import (
    AiUnitOfWork,
    CopyFacts,
    CopyWriter,
    CopyWriterError,
    UnitOfWorkFactory,
)
from modellbahn.modules.ai.domain.errors import (
    AiDisabledError,
    ProductNotFoundError,
    RunNotFoundError,
)
from modellbahn.modules.ai.domain.model import (
    MAX_ATTEMPTS,
    STALE_AFTER,
    AiRun,
    FailureReason,
    Review,
    check_draft,
)
from modellbahn.platform.clock import Clock

RECENT_LIMIT_MAX: Final = 200
WORK_TIME_BUDGET: Final = timedelta(minutes=2)
"""One tick of the worker job writes drafts for at most this long, then lets others run."""
PROVIDER_PAUSE: Final = timedelta(minutes=1)
"""After a passing failure of the provider the worker waits this long before the next run."""
DEFAULT_COST_ESTIMATE_MICRO_USD: Final = 40_000
"""What a draft is expected to cost before any was written (four cents)."""

_logger = structlog.get_logger(__name__)


def month_start(moment: datetime) -> datetime:
    """The first instant of the month of ``moment``, in UTC (the provider bills in UTC)."""
    utc = moment.astimezone(UTC)
    return utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True, slots=True)
class AiStatus:
    enabled: bool
    model: str
    monthly_budget_micro_usd: int
    spent_micro_usd: int
    """This month so far."""
    cost_per_draft_micro_usd: int
    """What a draft cost on average lately, or an estimate before the first one."""


@dataclass(frozen=True, slots=True)
class DraftsQueued:
    queued: int
    """Drafts of products that had no open or unreviewed draft."""
    skipped: int


class CopyService:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        enabled: bool,
        model: str,
        monthly_budget_micro_usd: int,
    ) -> None:
        self._uow = uow_factory
        self._clock = clock
        self._enabled = enabled
        self._model = model
        self._budget = monthly_budget_micro_usd

    async def status(self) -> AiStatus:
        async with self._uow() as uow:
            spent = await uow.runs.spent_since(month_start(self._clock.now()))
            average = await uow.runs.average_cost()
        return AiStatus(
            enabled=self._enabled,
            model=self._model if self._enabled else "",
            monthly_budget_micro_usd=self._budget,
            spent_micro_usd=spent,
            cost_per_draft_micro_usd=average or DEFAULT_COST_ESTIMATE_MICRO_USD,
        )

    async def request(self, *, product_id: UUID, requested_by: UUID | None) -> AiRun:
        """Queue a draft for the product; an open run of the product is returned instead."""
        self._require_enabled()
        async with self._uow() as uow:
            facts = await uow.facts.copy_facts(product_id)
            if facts is None:
                raise ProductNotFoundError
            existing = (await uow.runs.open_for([product_id])).get(product_id)
            if existing is not None and existing.is_open:
                return existing
            run = AiRun.request(
                product_id=product_id,
                product_name=facts.name,
                requested_by=requested_by,
                now=self._clock.now(),
            )
            uow.runs.add(run)
            await uow.commit()
        _logger.info("ai.copy.requested", run_id=str(run.id), product_id=str(product_id))
        return run

    async def request_drafts(self, *, requested_by: UUID | None) -> DraftsQueued:
        """Queue a draft for every product still in draft that has none open or to review."""
        self._require_enabled()
        async with self._uow() as uow:
            products = await uow.facts.draft_products()
            open_runs = await uow.runs.open_for([product_id for product_id, _ in products])
            now = self._clock.now()
            queued = 0
            for product_id, name in products:
                if product_id in open_runs:
                    continue
                uow.runs.add(
                    AiRun.request(
                        product_id=product_id,
                        product_name=name,
                        requested_by=requested_by,
                        now=now,
                    )
                )
                queued += 1
            await uow.commit()
        _logger.info("ai.copy.requested_drafts", queued=queued, skipped=len(products) - queued)
        return DraftsQueued(queued=queued, skipped=len(products) - queued)

    async def recent(
        self, *, limit: int, product_id: UUID | None = None, review: Review | None = None
    ) -> list[AiRun]:
        async with self._uow() as uow:
            return list(
                await uow.runs.recent(
                    limit=min(limit, RECENT_LIMIT_MAX), product_id=product_id, review=review
                )
            )

    async def get(self, run_id: UUID) -> AiRun:
        async with self._uow() as uow:
            run = await uow.runs.get(run_id)
            if run is None:
                raise RunNotFoundError
            return run

    async def mark_applied(self, run_id: UUID, *, fields: Sequence[str]) -> AiRun:
        """Record which fields somebody took over into the product (the editor saves them)."""
        async with self._uow() as uow:
            run = await self._locked(uow, run_id)
            run.apply(fields, now=self._clock.now())
            await uow.commit()
            return run

    async def discard(self, run_id: UUID) -> AiRun:
        async with self._uow() as uow:
            run = await self._locked(uow, run_id)
            run.discard(now=self._clock.now())
            await uow.commit()
            return run

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise AiDisabledError

    @staticmethod
    async def _locked(uow: AiUnitOfWork, run_id: UUID) -> AiRun:
        run = await uow.runs.get(run_id, for_update=True)
        if run is None:
            raise RunNotFoundError
        return run


class CopyWorker:
    """Writes the queued drafts one after the other (a periodic job of the worker)."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        writer: CopyWriter | None,
        clock: Clock,
        monthly_budget_micro_usd: int,
    ) -> None:
        self._uow = uow_factory
        self._writer = writer
        self._clock = clock
        self._budget = monthly_budget_micro_usd
        self._paused_until: datetime | None = None

    async def work(self) -> int:
        """Write drafts until none is due or the tick's time is up; how many were done."""
        started = self._clock.now()
        done = 0
        while self._clock.now() - started < WORK_TIME_BUDGET:
            if self._paused_until is not None and self._clock.now() < self._paused_until:
                break
            if not await self.write_next():
                break
            done += 1
        return done

    async def write_next(self) -> bool:
        """Take the oldest due run and write its draft; False if there was none."""
        claimed = await self._claim()
        if claimed is None:
            return False
        run_id, facts = claimed
        if facts is None or self._writer is None:
            return True  # _claim failed the run already
        try:
            written = await self._writer.write(facts)
        except CopyWriterError as error:
            if error.retryable:
                self._paused_until = self._clock.now() + PROVIDER_PAUSE
            await self._finish_failed(run_id, error)
            return True
        async with self._uow() as uow:
            run = await uow.runs.get(run_id, for_update=True)
            if run is None:
                return True
            warnings = check_draft(written.draft, json.dumps(run.input, ensure_ascii=False))
            uow.publish(
                run.complete(
                    draft=written.draft,
                    warnings=warnings,
                    model=written.model,
                    prompt_version=written.prompt_version,
                    usage=written.usage,
                    now=self._clock.now(),
                )
            )
            await uow.commit()
        _logger.info(
            "ai.copy.drafted",
            run_id=str(run_id),
            model=written.model,
            input_tokens=written.usage.input_tokens,
            output_tokens=written.usage.output_tokens,
            cost_micro_usd=written.usage.cost_micro_usd,
            warnings=len(warnings),
        )
        return True

    async def _claim(self) -> tuple[UUID, CopyFacts | None] | None:
        """Lock the next due run and start it; fail it here if it cannot be written."""
        now = self._clock.now()
        async with self._uow() as uow:
            run = await uow.runs.next_due(stale_before=now - STALE_AFTER)
            if run is None:
                return None
            reason: FailureReason | None = None
            facts: CopyFacts | None = None
            if self._writer is None:
                reason = FailureReason.DISABLED
            elif run.attempts >= MAX_ATTEMPTS:
                reason = FailureReason.ABANDONED
            elif await uow.runs.spent_since(month_start(now)) >= self._budget:
                reason = FailureReason.BUDGET_EXCEEDED
            elif run.product_id is not None:
                facts = await uow.facts.copy_facts(run.product_id)
            if facts is None:
                reason = reason or FailureReason.PRODUCT_GONE
                uow.publish(run.fail(reason, now=now))
                await uow.commit()
                _logger.info("ai.copy.failed", run_id=str(run.id), reason=reason.value)
                return run.id, None
            run.start(facts=facts.facts, now=now)
            await uow.commit()
            return run.id, facts

    async def _finish_failed(self, run_id: UUID, error: CopyWriterError) -> None:
        """Fail the run, or queue it again after a passing failure with attempts left."""
        async with self._uow() as uow:
            run = await uow.runs.get(run_id, for_update=True)
            if run is None:
                return
            now = self._clock.now()
            if error.retryable and run.attempts < MAX_ATTEMPTS:
                run.postpone(detail=error.detail, usage=error.usage, now=now)
                await uow.commit()
                _logger.warning(
                    "ai.copy.postponed",
                    run_id=str(run_id),
                    attempts=run.attempts,
                    detail=error.detail,
                )
                return
            uow.publish(
                run.fail(
                    error.reason,
                    detail=error.detail,
                    model=error.model,
                    prompt_version=error.prompt_version,
                    usage=error.usage,
                    now=now,
                )
            )
            await uow.commit()
        _logger.warning(
            "ai.copy.failed", run_id=str(run_id), reason=error.reason.value, detail=error.detail
        )
