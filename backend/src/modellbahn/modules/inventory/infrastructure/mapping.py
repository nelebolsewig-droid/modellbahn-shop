"""Imperative mapping of the inventory domain classes onto their tables.

Each class is its own aggregate here; the services load what they change and lock it.
"""

from sqlalchemy import inspect

from modellbahn.modules.inventory.domain.model import Allocation, LedgerEntry, Location, Scan, Unit
from modellbahn.modules.inventory.domain.parts import PartLedgerEntry, PartReceipt, PartStock
from modellbahn.modules.inventory.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the inventory classes. Safe to call more than once."""
    if inspect(Unit, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(Location, tables.locations)
    mapper_registry.map_imperatively(Allocation, tables.allocations)
    mapper_registry.map_imperatively(Unit, tables.units)
    mapper_registry.map_imperatively(Scan, tables.scans)
    mapper_registry.map_imperatively(LedgerEntry, tables.stock_ledger)
    mapper_registry.map_imperatively(PartStock, tables.part_stock)
    mapper_registry.map_imperatively(PartReceipt, tables.part_receipts)
    mapper_registry.map_imperatively(PartLedgerEntry, tables.part_ledger)
