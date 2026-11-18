"""Outbox event handlers of the manufacturing module; the worker runs them.

* ``inventory.allocation.backordered``: a paid piece has to be made, the plates for it
  are queued (ADR 0034). Planning plans only what is missing, so a retried event or a
  dozen pieces of one order at once plan nothing twice.
"""

from modellbahn.modules.inventory.contracts.events import AllocationBackordered
from modellbahn.modules.manufacturing.application.automation import AutoPlanner
from modellbahn.platform.outbox import HandlerRegistry


class ManufacturingHandlers:
    def __init__(self, *, planner: AutoPlanner) -> None:
        self._planner = planner

    def register(self, registry: HandlerRegistry) -> None:
        """Subscribe the handlers to their events."""
        registry.register(AllocationBackordered, self.plan)

    async def plan(self, _: AllocationBackordered) -> None:
        await self._planner.plan_waiting()
