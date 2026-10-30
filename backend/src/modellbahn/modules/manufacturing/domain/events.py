"""Domain events of the manufacturing module.

The printer hall in the admin area follows them live: a printer reported defective, a job
started, a plate done. The payloads carry codes, numbers and states, nothing personal.
"""

from dataclasses import dataclass
from typing import ClassVar, Final
from uuid import UUID

from modellbahn.platform.events import DomainEvent, JsonObject, domain_event

PRINTER_AGGREGATE: Final = "manufacturing.printer"
PRINT_JOB_AGGREGATE: Final = "manufacturing.print_job"
STAFF_AUDIENCE: Final = frozenset({"staff"})


@domain_event
@dataclass(frozen=True, kw_only=True)
class PrinterStatusChanged(DomainEvent):
    """A printer was added, or someone reported a new state (defective, repaired …)."""

    event_type: ClassVar[str] = "manufacturing.printer.status_changed"
    aggregate_type: ClassVar[str] = PRINTER_AGGREGATE
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    code: str
    status: str
    previous_status: str | None
    """``None`` for a printer just added."""

    def public_payload(self) -> JsonObject:
        return {
            "printer_id": str(self.aggregate_id),
            "code": self.code,
            "status": self.status,
            "previous_status": self.previous_status,
        }


@dataclass(frozen=True, kw_only=True)
class _PrintJobEvent(DomainEvent):
    audience: ClassVar[frozenset[str]] = STAFF_AUDIENCE

    number: int
    printer_id: UUID
    printer_code: str
    status: str

    def public_payload(self) -> JsonObject:
        return {
            "job_id": str(self.aggregate_id),
            "number": self.number,
            "printer_id": str(self.printer_id),
            "printer_code": self.printer_code,
            "status": self.status,
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class PrintJobChanged(_PrintJobEvent):
    """A job was queued, moved, started, taken off the printer or cancelled."""

    event_type: ClassVar[str] = "manufacturing.print_job.changed"
    aggregate_type: ClassVar[str] = PRINT_JOB_AGGREGATE

    change: str
    """``queued``, ``rescheduled``, ``started``, ``printed`` or ``cancelled``."""

    def public_payload(self) -> JsonObject:
        return {**super().public_payload(), "change": self.change}


@domain_event
@dataclass(frozen=True, kw_only=True)
class PrintJobCompleted(_PrintJobEvent):
    """A plate is done: its good parts can go into stock (the handler loads the lines)."""

    event_type: ClassVar[str] = "manufacturing.print_job.completed"
    aggregate_type: ClassVar[str] = PRINT_JOB_AGGREGATE

    good_parts: int
    failed_parts: int

    def public_payload(self) -> JsonObject:
        return {
            **super().public_payload(),
            "good_parts": self.good_parts,
            "failed_parts": self.failed_parts,
        }


@domain_event
@dataclass(frozen=True, kw_only=True)
class PrintJobFailed(_PrintJobEvent):
    """The whole plate failed, on the printer or afterwards."""

    event_type: ClassVar[str] = "manufacturing.print_job.failed"
    aggregate_type: ClassVar[str] = PRINT_JOB_AGGREGATE

    reason: str

    def public_payload(self) -> JsonObject:
        return {**super().public_payload(), "reason": self.reason}
