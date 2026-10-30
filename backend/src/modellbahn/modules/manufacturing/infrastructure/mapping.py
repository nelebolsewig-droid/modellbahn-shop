"""Imperative mapping of the manufacturing domain classes onto their tables.

A bill of materials owns its lines and a print job its lines; they are loaded with them
(``selectin``: the async session cannot load lazily). Printers, their status reports,
materials and parts are mapped on their own and refer to each other by id.
"""

from sqlalchemy import inspect
from sqlalchemy.orm import relationship

from modellbahn.modules.manufacturing.domain.model import (
    BillOfMaterials,
    BomLine,
    Material,
    Part,
    Printer,
    PrintJob,
    PrintJobLine,
    StatusReport,
)
from modellbahn.modules.manufacturing.infrastructure import tables
from modellbahn.platform.db import mapper_registry


def start_mappers() -> None:
    """Map the manufacturing classes. Safe to call more than once."""
    if inspect(Printer, raiseerr=False) is not None:
        return
    mapper_registry.map_imperatively(Printer, tables.printers)
    mapper_registry.map_imperatively(StatusReport, tables.printer_status_reports)
    mapper_registry.map_imperatively(Material, tables.materials)
    mapper_registry.map_imperatively(Part, tables.parts)
    mapper_registry.map_imperatively(BomLine, tables.bom_lines)
    mapper_registry.map_imperatively(
        BillOfMaterials,
        tables.boms,
        properties={
            "lines": relationship(
                BomLine,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.bom_lines.c.position,
                primaryjoin=tables.boms.c.product_scale_id == tables.bom_lines.c.product_scale_id,
                foreign_keys=[tables.bom_lines.c.product_scale_id],
            )
        },
    )
    mapper_registry.map_imperatively(PrintJobLine, tables.print_job_lines)
    mapper_registry.map_imperatively(
        PrintJob,
        tables.print_jobs,
        properties={
            "lines": relationship(
                PrintJobLine,
                cascade="all, delete-orphan",
                passive_deletes=True,
                lazy="selectin",
                order_by=tables.print_job_lines.c.position,
                primaryjoin=tables.print_jobs.c.id == tables.print_job_lines.c.job_id,
                foreign_keys=[tables.print_job_lines.c.job_id],
            )
        },
    )
