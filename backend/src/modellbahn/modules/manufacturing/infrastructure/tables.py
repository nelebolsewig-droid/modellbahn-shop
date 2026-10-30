"""SQLAlchemy Core tables of the ``manufacturing`` schema.

They mirror migration ``0010_manufacturing`` exactly, including constraint names;
``tests/integration/test_migrations.py`` compares both.

Composite keys carry the rules the model also checks, so a bug cannot break them:

* a bill of materials refers to ``(product_scale_id, scale_code)`` in the catalogue and its
  lines to ``(part_id, scale_code)``: an N part never gets into an H0 kit;
* a part refers to ``(material_id, technology)``: no resin part made of filament;
* a job refers to ``(printer_id, technology)`` and its lines to ``(part_id, technology)``:
  only parts of the printer's technology go on its plate.

At most one job prints on a printer (a partial unique index); a printer that prints
is never stored as such.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    Sequence,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)

from modellbahn.modules.catalog.contracts.product_scales import (
    PRODUCT_SCALE_REFERENCE,
    SCALE_REFERENCE,
)
from modellbahn.modules.identity.contracts.accounts import ACCOUNT_REFERENCE
from modellbahn.modules.manufacturing.domain.model import (
    PrinterStatus,
    PrintJobStatus,
    Technology,
)
from modellbahn.platform.db import StrEnumType, metadata

SCHEMA = "manufacturing"

_TECHNOLOGIES = "'fdm', 'resin'"
_PRINTER_STATUSES = "'in_service', 'defective', 'in_repair', 'retired'"

# Readable job numbers (Druck 17), drawn by the repository before a job is planned.
print_job_number_seq = Sequence("print_job_number_seq", schema=SCHEMA, metadata=metadata)

printers = Table(
    "printers",
    metadata,
    Column("id", Uuid, primary_key=True),
    # On the printer's label: unique, upper case.
    Column("code", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("model", Text, nullable=False, server_default=text("''")),
    Column("technology", StrEnumType(Technology), nullable=False),
    Column("build_x_mm", SmallInteger),
    Column("build_y_mm", SmallInteger),
    Column("build_z_mm", SmallInteger),
    Column("notes", Text, nullable=False, server_default=text("''")),
    Column("status", StrEnumType(PrinterStatus), nullable=False),
    Column("status_note", Text, nullable=False, server_default=text("''")),
    Column("status_changed_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    # Target of the jobs' key on (printer, technology).
    UniqueConstraint("id", "technology"),
    CheckConstraint("code ~ '^[A-Z0-9]{1,8}$'", name="code_format"),
    CheckConstraint(f"technology IN ({_TECHNOLOGIES})", name="technology"),
    CheckConstraint(f"status IN ({_PRINTER_STATUSES})", name="status"),
    CheckConstraint(
        "(build_x_mm IS NULL) = (build_y_mm IS NULL) "
        "AND (build_y_mm IS NULL) = (build_z_mm IS NULL)",
        name="build_volume_complete",
    ),
    CheckConstraint(
        "build_x_mm IS NULL OR (build_x_mm BETWEEN 1 AND 2000 "
        "AND build_y_mm BETWEEN 1 AND 2000 AND build_z_mm BETWEEN 1 AND 2000)",
        name="build_volume_range",
    ),
    schema=SCHEMA,
)

printer_status_reports = Table(
    "printer_status_reports",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("printer_id", Uuid, ForeignKey(printers.c.id, ondelete="CASCADE"), nullable=False),
    Column("from_status", StrEnumType(PrinterStatus)),
    Column("to_status", StrEnumType(PrinterStatus), nullable=False),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("staff_id", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT")),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        f"(from_status IS NULL OR from_status IN ({_PRINTER_STATUSES})) "
        f"AND to_status IN ({_PRINTER_STATUSES})",
        name="statuses",
    ),
    Index("printer_status_reports_printer_idx", "printer_id", "occurred_at"),
    schema=SCHEMA,
)

materials = Table(
    "materials",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False, unique=True),
    Column("technology", StrEnumType(Technology), nullable=False),
    Column("notes", Text, nullable=False, server_default=text("''")),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    # Target of the parts' key on (material, technology).
    UniqueConstraint("id", "technology"),
    CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="name_length"),
    CheckConstraint(f"technology IN ({_TECHNOLOGIES})", name="technology"),
    schema=SCHEMA,
)

parts = Table(
    "parts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("part_number", Text, nullable=False, unique=True),
    Column("name", Text, nullable=False),
    Column("scale_code", Text, ForeignKey(SCALE_REFERENCE, ondelete="RESTRICT"), nullable=False),
    Column("technology", StrEnumType(Technology), nullable=False),
    Column("material_id", Uuid),
    Column("layer_height_um", SmallInteger),
    Column("plate_minutes", Integer),
    Column("parts_per_plate", SmallInteger, nullable=False, server_default=text("1")),
    # Grams of filament or millilitres of resin for one part.
    Column("material_per_part", Numeric(8, 2)),
    Column("notes", Text, nullable=False, server_default=text("''")),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["material_id", "technology"],
        [materials.c.id, materials.c.technology],
        ondelete="RESTRICT",
    ),
    # Targets of the keys of bill of materials lines and job lines.
    UniqueConstraint("id", "scale_code"),
    UniqueConstraint("id", "technology"),
    CheckConstraint(
        "part_number ~ '^[A-Z0-9]+(-[A-Z0-9]+)*$' AND char_length(part_number) <= 40",
        name="part_number_format",
    ),
    CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="name_length"),
    CheckConstraint(f"technology IN ({_TECHNOLOGIES})", name="technology"),
    CheckConstraint(
        "layer_height_um IS NULL OR layer_height_um BETWEEN 10 AND 1000", name="layer_height"
    ),
    CheckConstraint(
        "plate_minutes IS NULL OR plate_minutes BETWEEN 1 AND 10080", name="plate_minutes"
    ),
    CheckConstraint("parts_per_plate BETWEEN 1 AND 1000", name="parts_per_plate"),
    CheckConstraint("material_per_part IS NULL OR material_per_part > 0", name="material_per_part"),
    Index("parts_scale_idx", "scale_code", "part_number"),
    schema=SCHEMA,
)

boms = Table(
    "boms",
    metadata,
    Column("product_scale_id", Uuid, nullable=False),
    Column("scale_code", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("updated_by", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT")),
    PrimaryKeyConstraint("product_scale_id"),
    ForeignKeyConstraint(
        ["product_scale_id", "scale_code"], list(PRODUCT_SCALE_REFERENCE), ondelete="RESTRICT"
    ),
    # Target of the lines' key on (bill of materials, scale).
    UniqueConstraint("product_scale_id", "scale_code"),
    schema=SCHEMA,
)

bom_lines = Table(
    "bom_lines",
    metadata,
    Column("product_scale_id", Uuid, nullable=False),
    Column("part_id", Uuid, nullable=False),
    Column("scale_code", Text, nullable=False),
    Column("quantity", SmallInteger, nullable=False),
    Column("position", SmallInteger, nullable=False),
    PrimaryKeyConstraint("product_scale_id", "part_id"),
    ForeignKeyConstraint(
        ["product_scale_id", "scale_code"],
        [boms.c.product_scale_id, boms.c.scale_code],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["part_id", "scale_code"], [parts.c.id, parts.c.scale_code], ondelete="RESTRICT"
    ),
    CheckConstraint("quantity BETWEEN 1 AND 999", name="quantity"),
    CheckConstraint("position >= 0", name="position_non_negative"),
    Index("bom_lines_part_idx", "part_id"),
    schema=SCHEMA,
)

print_jobs = Table(
    "print_jobs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("number", Integer, nullable=False, unique=True),
    Column("printer_id", Uuid, nullable=False),
    Column("technology", StrEnumType(Technology), nullable=False),
    Column("status", StrEnumType(PrintJobStatus), nullable=False),
    Column("planned_minutes", Integer),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("failure_reason", Text, nullable=False, server_default=text("''")),
    Column("created_by", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("started_by", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT")),
    Column("printed_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("finished_by", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT")),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(
        ["printer_id", "technology"],
        [printers.c.id, printers.c.technology],
        ondelete="RESTRICT",
    ),
    # Target of the lines' key on (job, technology).
    UniqueConstraint("id", "technology"),
    CheckConstraint(f"technology IN ({_TECHNOLOGIES})", name="technology"),
    CheckConstraint(
        "status IN ('queued', 'printing', 'post_processing', 'done', 'failed', 'cancelled')",
        name="status",
    ),
    CheckConstraint(
        "planned_minutes IS NULL OR planned_minutes BETWEEN 1 AND 10080", name="planned_minutes"
    ),
    # Started exactly when it got past the queue.
    CheckConstraint(
        "(status IN ('queued', 'cancelled')) = (started_at IS NULL)", name="started_at"
    ),
    CheckConstraint(
        "status NOT IN ('post_processing', 'done') OR printed_at IS NOT NULL", name="printed_at"
    ),
    CheckConstraint(
        "(status IN ('done', 'failed', 'cancelled')) = (finished_at IS NOT NULL)",
        name="finished_at",
    ),
    CheckConstraint("status = 'failed' OR failure_reason = ''", name="failure_reason"),
    # One plate at a time on a printer.
    Index(
        "print_jobs_one_printing_idx",
        "printer_id",
        unique=True,
        postgresql_where=text("status = 'printing'"),
    ),
    # The queues of the printer hall.
    Index(
        "print_jobs_open_idx",
        "printer_id",
        "created_at",
        postgresql_where=text("status IN ('queued', 'printing', 'post_processing')"),
    ),
    Index("print_jobs_printer_idx", "printer_id", "created_at"),
    schema=SCHEMA,
)

print_job_lines = Table(
    "print_job_lines",
    metadata,
    Column("job_id", Uuid, nullable=False),
    Column("part_id", Uuid, nullable=False),
    Column("technology", StrEnumType(Technology), nullable=False),
    Column("quantity", SmallInteger, nullable=False),
    Column("good", SmallInteger, nullable=False, server_default=text("0")),
    Column("failed", SmallInteger, nullable=False, server_default=text("0")),
    Column("position", SmallInteger, nullable=False),
    PrimaryKeyConstraint("job_id", "part_id"),
    ForeignKeyConstraint(
        ["job_id", "technology"],
        [print_jobs.c.id, print_jobs.c.technology],
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["part_id", "technology"], [parts.c.id, parts.c.technology], ondelete="RESTRICT"
    ),
    CheckConstraint("quantity BETWEEN 1 AND 1000", name="quantity"),
    CheckConstraint("good >= 0 AND failed >= 0", name="counts_non_negative"),
    # Never more good and failed parts than were planned.
    CheckConstraint("good + failed <= quantity", name="counts_within_quantity"),
    CheckConstraint("position >= 0", name="position_non_negative"),
    Index("print_job_lines_part_idx", "part_id"),
    schema=SCHEMA,
)
