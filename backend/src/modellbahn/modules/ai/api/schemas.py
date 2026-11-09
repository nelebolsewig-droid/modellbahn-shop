"""Request and response bodies of the AI API (snake_case JSON)."""

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field

from modellbahn.modules.ai.application.copy import AiStatus, DraftsQueued
from modellbahn.modules.ai.domain.model import (
    COPY_FIELDS,
    AiRun,
    FailureReason,
    Review,
    RunStatus,
)

type CopyField = Literal["summary", "description"]


class AiStatusOut(BaseModel):
    enabled: bool = Field(description="False while no language model is configured.")
    model: str = Field(examples=["claude-opus-5-5"], description="Empty while switched off.")
    monthly_budget_micro_usd: int = Field(
        examples=[20_000_000], description="The month's budget in millionths of a dollar."
    )
    spent_micro_usd: int = Field(
        examples=[1_240_000], description="Spent this month (UTC) in millionths of a dollar."
    )
    cost_per_draft_micro_usd: int = Field(
        examples=[38_000],
        description="What a draft cost on average lately; an estimate before the first.",
    )

    @classmethod
    def from_status(cls, status: AiStatus) -> Self:
        return cls(
            enabled=status.enabled,
            model=status.model,
            monthly_budget_micro_usd=status.monthly_budget_micro_usd,
            spent_micro_usd=status.spent_micro_usd,
            cost_per_draft_micro_usd=status.cost_per_draft_micro_usd,
        )


class CopyDraftOut(BaseModel):
    summary: str
    description: str = Field(description="Paragraphs separated by an empty line.")
    open_questions: list[str] = Field(
        description="What the model missed in the facts, as questions to the workshop."
    )


class AiRunOut(BaseModel):
    id: UUID
    product_id: UUID | None = Field(description="None once the product was deleted.")
    product_name: str
    status: RunStatus
    review: Review
    draft: CopyDraftOut | None = Field(description="Only once the run is done.")
    warnings: list[str] = Field(
        description="Hints of the check: numbers without a source, claims of a licence."
    )
    failure: FailureReason | None
    failure_detail: str
    applied_fields: list[CopyField]
    model: str = Field(description="The model that answered; empty before the call.")
    prompt_version: str
    attempts: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_micro_usd: int = Field(description="What the run cost, in millionths of a dollar.")
    facts: dict[str, Any] = Field(description="The facts the model saw.")
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    reviewed_at: datetime | None

    @classmethod
    def from_run(cls, run: AiRun) -> Self:
        draft = run.draft
        return cls(
            id=run.id,
            product_id=run.product_id,
            product_name=run.product_name,
            status=run.status,
            review=run.review,
            draft=CopyDraftOut(
                summary=draft.summary,
                description=draft.description,
                open_questions=list(draft.open_questions),
            )
            if draft is not None
            else None,
            warnings=list(run.warnings),
            failure=run.failure,
            failure_detail=run.failure_detail,
            applied_fields=[f for f in run.applied_fields if f in COPY_FIELDS],  # type: ignore[misc]
            model=run.model,
            prompt_version=run.prompt_version,
            attempts=run.attempts,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            cache_read_tokens=run.cache_read_tokens,
            cache_write_tokens=run.cache_write_tokens,
            cost_micro_usd=run.cost_micro_usd,
            facts=dict(run.input),
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            reviewed_at=run.reviewed_at,
        )


class AiRunListOut(BaseModel):
    items: list[AiRunOut]


class CopyRequestIn(BaseModel):
    product_id: UUID


class DraftsQueuedOut(BaseModel):
    queued: int = Field(description="Products in draft that got a new run.")
    skipped: int = Field(description="Products in draft with a run open or waiting for review.")

    @classmethod
    def from_result(cls, result: DraftsQueued) -> Self:
        return cls(queued=result.queued, skipped=result.skipped)


class ApplyIn(BaseModel):
    fields: list[CopyField] = Field(
        min_length=1, max_length=len(COPY_FIELDS), description="What was taken over."
    )
