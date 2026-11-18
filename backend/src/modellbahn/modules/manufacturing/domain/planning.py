"""Automatic planning (ADR 0034): the plates it takes to make what paid orders wait for.

Pure arithmetic over parts and printers; the use case gathers the figures and creates
the print jobs. It plans only what is missing, so running it again plans nothing new.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from modellbahn.modules.manufacturing.domain.model import Part, Printer, estimate_minutes


@dataclass(frozen=True, slots=True)
class PlannedPlate:
    """One plate to queue: so many of one part on one printer."""

    printer: Printer
    part: Part
    quantity: int


@dataclass(frozen=True, slots=True)
class Plan:
    plates: list[PlannedPlate]
    unplaced: dict[UUID, int]
    """Parts no printer in service can print (wrong technology, all down), with how many."""


def shortfall(
    needed: Mapping[UUID, int], supply: Mapping[UUID, int], on_plates: Mapping[UUID, int]
) -> dict[UUID, int]:
    """Per part: what kits need, less what lies ready and what open plates will bring."""
    missing = {
        part_id: quantity - supply.get(part_id, 0) - on_plates.get(part_id, 0)
        for part_id, quantity in needed.items()
    }
    return {part_id: quantity for part_id, quantity in missing.items() if quantity > 0}


def plan_plates(
    missing: Iterable[tuple[Part, int]],
    printers: Sequence[Printer],
    queued_minutes: Mapping[UUID, int],
) -> Plan:
    """Full plates of each part, each on the printer of its technology with the shortest queue.

    A plate holds as many of a part as ``parts_per_plate`` says; the last one takes the
    rest. A plate without a known time counts an hour, so the queues still even out.
    """
    queues = {
        printer.id: queued_minutes.get(printer.id, 0) for printer in printers if printer.in_service
    }
    plates: list[PlannedPlate] = []
    unplaced: dict[UUID, int] = {}
    for part, quantity in missing:
        candidates = [
            printer
            for printer in printers
            if printer.in_service and printer.technology is part.technology
        ]
        if not part.active or not candidates:
            unplaced[part.id] = unplaced.get(part.id, 0) + quantity
            continue
        left = quantity
        while left > 0:
            on_plate = min(left, max(part.parts_per_plate, 1))
            printer = min(candidates, key=lambda candidate: (queues[candidate.id], candidate.code))
            plates.append(PlannedPlate(printer=printer, part=part, quantity=on_plate))
            queues[printer.id] += estimate_minutes(printer.technology, [(part, on_plate)]) or 60
            left -= on_plate
    return Plan(plates=plates, unplaced=unplaced)
