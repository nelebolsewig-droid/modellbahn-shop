"""What the AI use cases need from the outside: the model, the product facts, the runs."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from modellbahn.modules.ai.domain.model import AiRun, CopyDraft, FailureReason, Review, Usage
from modellbahn.platform.events import DomainEvent, JsonObject


@dataclass(frozen=True, slots=True)
class CopyFacts:
    """Everything the model may know about a product, and the photos it may look at."""

    product_id: UUID
    name: str
    facts: JsonObject
    """Name, category, prototype, epochs, scales with sizes, finishes and colours."""
    image_urls: tuple[str, ...]
    """Public addresses of up to two photos, the main photo first; empty if none."""


class FactsSource(Protocol):
    async def copy_facts(self, product_id: UUID) -> CopyFacts | None:
        """The facts of the product, or None if it does not exist."""
        ...

    async def draft_products(self) -> Sequence[tuple[UUID, str]]:
        """Id and name of every product that is still a draft, the oldest first."""
        ...


@dataclass(frozen=True, slots=True)
class WrittenCopy:
    draft: CopyDraft
    usage: Usage
    model: str
    """The model that answered (with a fallback, not always the one asked for)."""
    prompt_version: str


class CopyWriterError(Exception):
    """The model gave no usable draft; ``usage`` holds what the attempt cost anyway.

    ``retryable`` marks a passing failure of the provider (overloaded, rate limit, no
    connection): the run may wait and try again instead of failing.
    """

    def __init__(
        self,
        reason: FailureReason,
        detail: str = "",
        *,
        usage: Usage | None = None,
        model: str = "",
        prompt_version: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail
        self.usage = usage
        self.model = model
        self.prompt_version = prompt_version
        self.retryable = retryable


class CopyWriter(Protocol):
    """The language model behind the drafts (the anti-corruption layer of the concept)."""

    @property
    def model(self) -> str: ...

    async def write(self, facts: CopyFacts) -> WrittenCopy:
        """A draft from the facts; raises :class:`CopyWriterError` instead of a bad draft."""
        ...

    async def aclose(self) -> None: ...


class RunRepository(Protocol):
    async def get(self, run_id: UUID, *, for_update: bool = False) -> AiRun | None: ...

    async def next_due(self, *, stale_before: datetime) -> AiRun | None:
        """The oldest run to work on, locked and skipped by other workers.

        A queued run that nobody discarded, or one still running since before
        ``stale_before`` (its worker died).
        """
        ...

    async def open_for(self, product_ids: Sequence[UUID]) -> dict[UUID, AiRun]:
        """Per product, its newest run that is open or waits for review."""
        ...

    async def recent(
        self, *, limit: int, product_id: UUID | None = None, review: Review | None = None
    ) -> Sequence[AiRun]:
        """The newest runs, of one product or with one review state if given."""
        ...

    async def spent_since(self, moment: datetime) -> int:
        """What the runs since ``moment`` cost, in millionths of a dollar."""
        ...

    async def average_cost(self) -> int | None:
        """What the latest written drafts cost on average, None before the first one."""
        ...

    def add(self, run: AiRun) -> None: ...


class AiUnitOfWork(Protocol):
    """One transaction over the runs and the product facts (see ``platform.uow``)."""

    @property
    def runs(self) -> RunRepository: ...

    @property
    def facts(self) -> FactsSource: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def publish(self, *events: DomainEvent) -> None: ...

    async def commit(self) -> None: ...


type UnitOfWorkFactory = Callable[[], AiUnitOfWork]
