"""A run per text draft (ADR 0021): what the model saw, what it wrote, what it cost.

A person asks for a draft; the run waits until the worker takes it, calls the model and
stores the answer. Nothing reaches the shop by itself: someone takes over the fields
they want in the product editor and marks the run as applied, or discards it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import UUID

from modellbahn.modules.ai.domain.errors import InvalidFieldError, RunNotReviewableError
from modellbahn.modules.ai.domain.events import CopyDrafted, CopyFailed
from modellbahn.platform.events import JsonObject
from modellbahn.platform.ids import new_id

TASK_PRODUCT_COPY: Final = "product_copy"
MAX_ATTEMPTS: Final = 3
"""A run that keeps dying with its worker is given up after this many starts."""
STALE_AFTER: Final = timedelta(minutes=10)
"""A run still ``running`` after this long lost its worker and may be started again."""
COPY_FIELDS: Final = ("summary", "description")
"""The product fields a draft fills."""
SUMMARY_MAX_LENGTH: Final = 280
DESCRIPTION_MAX_LENGTH: Final = 10_000
OPEN_QUESTIONS_MAX: Final = 8

# Claims a product text must not make without proof: a licence of the original maker.
_LICENCE_CLAIMS: Final = re.compile(r"\b(lizenz\w*|offiziell\w*|original\s*-?\s*lizenz)", re.I)
_NUMBER: Final = re.compile(r"\d+(?:[.,:]\d+)*")


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Review(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    DISCARDED = "discarded"


class FailureReason(StrEnum):
    BUDGET_EXCEEDED = "budget_exceeded"
    """The month's budget is used up."""
    REFUSED = "refused"
    """The model's safety filters declined, the fallback too."""
    TRUNCATED = "truncated"
    """The answer did not fit into the token limit."""
    INVALID_OUTPUT = "invalid_output"
    """The answer did not match the schema."""
    PRODUCT_GONE = "product_gone"
    """The product was deleted before the worker came to it."""
    PROVIDER = "provider_error"
    """The model's API failed (rate limit, outage, wrong key)."""
    ABANDONED = "abandoned"
    """The worker died with the run several times."""
    DISABLED = "disabled"
    """No model is configured any more."""


@dataclass(frozen=True, slots=True)
class CopyDraft:
    """What the model proposes: a short text for tiles, a description, open questions."""

    summary: str
    description: str
    open_questions: tuple[str, ...] = ()

    @classmethod
    def clean(cls, summary: str, description: str, open_questions: Iterable[str]) -> CopyDraft:
        """Trim to the product's limits; one line for the summary, paragraphs below."""
        one_line = " ".join(summary.split())
        paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", description.strip())]
        questions = tuple(" ".join(q.split()) for q in open_questions if q.strip())
        return cls(
            summary=one_line[:SUMMARY_MAX_LENGTH],
            description="\n\n".join(p for p in paragraphs if p)[:DESCRIPTION_MAX_LENGTH],
            open_questions=questions[:OPEN_QUESTIONS_MAX],
        )

    def to_json(self) -> JsonObject:
        return {
            "summary": self.summary,
            "description": self.description,
            "open_questions": list(self.open_questions),
        }

    @classmethod
    def from_json(cls, data: JsonObject) -> CopyDraft:
        questions = data.get("open_questions") or []
        return cls(
            summary=str(data.get("summary", "")),
            description=str(data.get("description", "")),
            open_questions=tuple(str(q) for q in questions) if isinstance(questions, list) else (),
        )


@dataclass(frozen=True, slots=True)
class Usage:
    """Tokens and what they cost, in millionths of a US dollar (the provider's currency)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_micro_usd: int = 0


def check_draft(draft: CopyDraft, facts_text: str) -> list[str]:
    """Hints for the person who reviews the draft: numbers and claims without a source.

    Every number in the text should come from the facts; a licence claim never does.
    """
    known = {_normal_number(n) for n in _NUMBER.findall(facts_text)}
    warnings = []
    text = f"{draft.summary}\n{draft.description}"
    unknown = sorted(
        {n for n in _NUMBER.findall(text) if _normal_number(n) not in known}, key=text.index
    )
    if unknown:
        warnings.append(f"Zahlen ohne Quelle in den Fakten: {', '.join(unknown)}. Bitte prüfen.")
    if _LICENCE_CLAIMS.search(text):
        warnings.append(
            "Der Text spricht von Lizenz oder Offiziellem. Bitte prüfen oder streichen."
        )
    return warnings


def _normal_number(number: str) -> str:
    return number.replace(",", ".")


@dataclass(eq=False, kw_only=True)
class AiRun:
    """One request for a draft and its call of the model."""

    id: UUID
    task: str
    product_id: UUID | None
    product_name: str
    requested_by: UUID | None
    status: RunStatus
    review: Review
    prompt_version: str = ""
    model: str = ""
    input: JsonObject = field(default_factory=dict)
    output: JsonObject | None = None
    warnings: list[str] = field(default_factory=list)
    failure: FailureReason | None = None
    failure_detail: str = ""
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_micro_usd: int = 0
    applied_fields: list[str] = field(default_factory=list)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    reviewed_at: datetime | None = None
    updated_at: datetime

    @classmethod
    def request(
        cls, *, product_id: UUID, product_name: str, requested_by: UUID | None, now: datetime
    ) -> AiRun:
        return cls(
            id=new_id(),
            task=TASK_PRODUCT_COPY,
            product_id=product_id,
            product_name=product_name,
            requested_by=requested_by,
            status=RunStatus.QUEUED,
            review=Review.PENDING,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_open(self) -> bool:
        """Waiting for the worker or being written."""
        return self.status in {RunStatus.QUEUED, RunStatus.RUNNING}

    @property
    def draft(self) -> CopyDraft | None:
        return CopyDraft.from_json(self.output) if self.output is not None else None

    def start(self, *, facts: JsonObject, now: datetime) -> None:
        """The worker takes the run; it records the facts the model will see."""
        self.status = RunStatus.RUNNING
        self.attempts += 1
        self.input = facts
        self.started_at = now
        self.updated_at = now

    def complete(
        self,
        *,
        draft: CopyDraft,
        warnings: list[str],
        model: str,
        prompt_version: str,
        usage: Usage,
        now: datetime,
    ) -> CopyDrafted:
        self.status = RunStatus.DONE
        self.output = draft.to_json()
        self.warnings = warnings
        self.model = model
        self.prompt_version = prompt_version
        self._account(usage)
        self.finished_at = now
        self.updated_at = now
        return CopyDrafted(
            aggregate_id=self.id,
            occurred_at=now,
            product_id=self.product_id,
            name=self.product_name,
        )

    def fail(
        self,
        reason: FailureReason,
        *,
        detail: str = "",
        model: str = "",
        prompt_version: str = "",
        usage: Usage | None = None,
        now: datetime,
    ) -> CopyFailed:
        self.status = RunStatus.FAILED
        self.failure = reason
        self.failure_detail = detail[:500]
        self.model = model or self.model
        self.prompt_version = prompt_version or self.prompt_version
        if usage is not None:
            self._account(usage)
        self.finished_at = now
        self.updated_at = now
        return CopyFailed(
            aggregate_id=self.id,
            occurred_at=now,
            product_id=self.product_id,
            name=self.product_name,
            reason=reason.value,
        )

    def postpone(self, *, detail: str, usage: Usage | None = None, now: datetime) -> None:
        """The provider failed for the moment: back into the queue, try again later."""
        self.status = RunStatus.QUEUED
        self.failure_detail = detail[:500]
        if usage is not None:
            self._account(usage)
        self.updated_at = now

    def apply(self, fields: Iterable[str], *, now: datetime) -> None:
        """Somebody took over these fields of the draft into the product."""
        chosen = list(dict.fromkeys(fields))
        unknown = [f for f in chosen if f not in COPY_FIELDS]
        if unknown or not chosen:
            raise InvalidFieldError("fields", "invalid", f"choose from {', '.join(COPY_FIELDS)}")
        self._ensure_reviewable()
        self.review = Review.APPLIED
        self.applied_fields = chosen
        self.reviewed_at = now
        self.updated_at = now

    def discard(self, *, now: datetime) -> None:
        if self.status is RunStatus.FAILED or self.is_open:
            # A failed or unfinished run has nothing to keep; discarding just files it away.
            self.review = Review.DISCARDED
        else:
            self._ensure_reviewable()
            self.review = Review.DISCARDED
        self.reviewed_at = now
        self.updated_at = now

    def _ensure_reviewable(self) -> None:
        if self.status is not RunStatus.DONE:
            raise RunNotReviewableError("no_draft")
        if self.review is not Review.PENDING:
            raise RunNotReviewableError("already_reviewed")

    def _account(self, usage: Usage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_tokens += usage.cache_read_tokens
        self.cache_write_tokens += usage.cache_write_tokens
        self.cost_micro_usd += usage.cost_micro_usd
