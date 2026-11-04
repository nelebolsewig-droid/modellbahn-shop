"""SQLAlchemy Core tables of the ``inventory`` schema.

They mirror migrations ``0005_inventory`` and ``0011_part_stock`` exactly, including
constraint names; ``tests/integration/test_migrations.py`` compares both.

Units refer to catalogue variants with a ``RESTRICT`` key: a variant that has ever had a
unit keeps existing (it can be deactivated). Allocations refer to the order, the
aggregate root, and name the order line and variant without a key, like sales does.
The parts store refers to the manufacturing module's parts the same way, and a receipt
to the line of the plate its parts came off.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from modellbahn.modules.catalog.contracts.variants import VARIANT_REFERENCE
from modellbahn.modules.identity.contracts.accounts import ACCOUNT_REFERENCE
from modellbahn.modules.inventory.domain.model import (
    AllocationStatus,
    LocationKind,
    MovementReason,
    ScanMode,
    ScanOutcome,
    UnitStatus,
)
from modellbahn.modules.inventory.domain.parts import PartMovementReason
from modellbahn.modules.manufacturing.contracts.parts import (
    PART_REFERENCE,
    PRINT_JOB_LINE_REFERENCE,
)
from modellbahn.modules.sales.contracts.orders import ORDER_REFERENCE
from modellbahn.platform.db import Ltree, StrEnumType, metadata

SCHEMA = "inventory"

_UNIT_STATUSES = "'labeled', 'in_stock', 'allocated', 'picked', 'shipped', 'scrapped'"

locations = Table(
    "locations",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("parent_id", Uuid, ForeignKey("inventory.locations.id", ondelete="RESTRICT")),
    # Printed on the label: unique, upper case, never changed.
    Column("code", Text, nullable=False, unique=True),
    Column("path", Ltree, nullable=False, unique=True),
    Column("kind", StrEnumType(LocationKind), nullable=False),
    Column("name", Text, nullable=False, server_default=text("''")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("kind IN ('site', 'shelf', 'compartment', 'box', 'staging')", name="kind"),
    CheckConstraint("code ~ '^[A-Z0-9]{1,8}(-[A-Z0-9]{1,8}){0,4}$'", name="code_format"),
    # Only a site stands on its own; everything else lies somewhere.
    CheckConstraint("(kind = 'site') = (parent_id IS NULL)", name="site_is_root"),
    Index("locations_path_idx", "path", postgresql_using="gist"),
    Index("locations_parent_idx", "parent_id"),
    schema=SCHEMA,
)

allocations = Table(
    "allocations",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("order_id", Uuid, ForeignKey(ORDER_REFERENCE, ondelete="RESTRICT"), nullable=False),
    Column("order_line_id", Uuid, nullable=False),
    Column("variant_id", Uuid, nullable=False),
    Column("piece", SmallInteger, nullable=False),
    Column("status", StrEnumType(AllocationStatus), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("status IN ('open', 'shipped', 'released')", name="status"),
    CheckConstraint("piece >= 0", name="piece_non_negative"),
    UniqueConstraint("order_line_id", "piece"),
    Index("allocations_order_idx", "order_id"),
    # Backorders are served first come, first served.
    Index(
        "allocations_open_idx",
        "variant_id",
        "created_at",
        postgresql_where=text("status = 'open'"),
    ),
    schema=SCHEMA,
)

units = Table(
    "units",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("code", Text, nullable=False, unique=True),
    Column("variant_id", Uuid, ForeignKey(VARIANT_REFERENCE, ondelete="RESTRICT"), nullable=False),
    Column("status", StrEnumType(UnitStatus), nullable=False),
    Column("location_id", Uuid, ForeignKey(locations.c.id, ondelete="RESTRICT")),
    Column("allocation_id", Uuid, ForeignKey(allocations.c.id, ondelete="RESTRICT")),
    Column("scrap_note", Text, nullable=False, server_default=text("''")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(f"status IN ({_UNIT_STATUSES})", name="status"),
    # Crockford Base32: no I, L, O or U.
    CheckConstraint("code ~ '^[0-9A-HJKMNP-TV-Z]{10}$'", name="code_format"),
    CheckConstraint(
        "(status IN ('in_stock', 'allocated')) = (location_id IS NOT NULL)", name="on_shelf"
    ),
    CheckConstraint(
        "(status IN ('allocated', 'picked', 'shipped')) = (allocation_id IS NOT NULL)",
        name="serves_allocation",
    ),
    # One unit per allocation, checked at commit: handing an allocation from one unit to
    # another (picking a different piece of the same article) is a single step.
    UniqueConstraint("allocation_id", deferrable=True, initially="DEFERRED"),
    Index("units_variant_status_idx", "variant_id", "status", "created_at"),
    Index("units_location_idx", "location_id", postgresql_where=text("location_id IS NOT NULL")),
    schema=SCHEMA,
)

scans = Table(
    "scans",
    metadata,
    # Generated by the device: a scan sent again is recognised by it.
    Column("id", Uuid, primary_key=True),
    Column("staff_id", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT"), nullable=False),
    Column("mode", StrEnumType(ScanMode), nullable=False),
    Column("raw", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("context", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("outcome", StrEnumType(ScanOutcome), nullable=False),
    # The answer given; a repeated request gets it again without booking anything.
    Column("response", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("undone_at", DateTime(timezone=True)),
    CheckConstraint("mode IN ('put_away', 'pick', 'lookup')", name="mode"),
    CheckConstraint(
        "outcome IN ('applied', 'selected', 'info', 'rejected', 'unknown')", name="outcome"
    ),
    CheckConstraint("source IN ('camera', 'scanner', 'keyboard')", name="source"),
    CheckConstraint("length(raw) BETWEEN 1 AND 300", name="raw_length"),
    CheckConstraint("undone_at IS NULL OR outcome = 'applied'", name="undo_needs_booking"),
    Index("scans_staff_idx", "staff_id", "created_at"),
    schema=SCHEMA,
)

stock_ledger = Table(
    "stock_ledger",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("unit_id", Uuid, ForeignKey(units.c.id, ondelete="RESTRICT"), nullable=False),
    Column("variant_id", Uuid, nullable=False),
    Column("reason", StrEnumType(MovementReason), nullable=False),
    Column("from_status", StrEnumType(UnitStatus)),
    Column("to_status", StrEnumType(UnitStatus), nullable=False),
    Column("from_location_id", Uuid, ForeignKey(locations.c.id, ondelete="RESTRICT")),
    Column("to_location_id", Uuid, ForeignKey(locations.c.id, ondelete="RESTRICT")),
    Column("allocation_id", Uuid, ForeignKey(allocations.c.id, ondelete="RESTRICT")),
    Column("scan_id", Uuid, ForeignKey(scans.c.id, ondelete="RESTRICT")),
    Column("staff_id", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT")),
    # An undo books the movement backwards and names the entry it reverses, once.
    Column(
        "reverses_id",
        BigInteger,
        ForeignKey("inventory.stock_ledger.id", ondelete="RESTRICT"),
        unique=True,
    ),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "reason IN ('label', 'put_away', 'move', 'allocate', 'release', 'pick', 'ship', "
        "'scrap', 'undo')",
        name="reason",
    ),
    CheckConstraint(
        f"(from_status IS NULL OR from_status IN ({_UNIT_STATUSES})) "
        f"AND to_status IN ({_UNIT_STATUSES})",
        name="statuses",
    ),
    # Only labelling starts a unit's history; every later entry knows where it came from.
    CheckConstraint("(reason = 'label') = (from_status IS NULL)", name="label_starts"),
    CheckConstraint("(reason = 'undo') = (reverses_id IS NOT NULL)", name="undo_reverses"),
    Index("stock_ledger_unit_idx", "unit_id", "id"),
    Index("stock_ledger_scan_idx", "scan_id", postgresql_where=text("scan_id IS NOT NULL")),
    schema=SCHEMA,
)


# --- Parts store ----------------------------------------------------------------------

part_stock = Table(
    "part_stock",
    metadata,
    Column("part_id", Uuid, ForeignKey(PART_REFERENCE, ondelete="RESTRICT"), nullable=False),
    Column("location_id", Uuid, ForeignKey(locations.c.id, ondelete="RESTRICT"), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("part_id", "location_id"),
    # An emptied box keeps its row at 0 until something goes in again.
    CheckConstraint("quantity >= 0", name="quantity_non_negative"),
    Index("part_stock_location_idx", "location_id"),
    schema=SCHEMA,
)

part_receipts = Table(
    "part_receipts",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("print_job_id", Uuid, nullable=False),
    Column("part_id", Uuid, nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("stored", Integer, nullable=False, server_default=text("0")),
    Column("written_off", Integer, nullable=False, server_default=text("0")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    # The parts came off a line of that plate; a plate yields one receipt per part.
    ForeignKeyConstraint(
        ["print_job_id", "part_id"], list(PRINT_JOB_LINE_REFERENCE), ondelete="RESTRICT"
    ),
    UniqueConstraint("print_job_id", "part_id"),
    CheckConstraint("quantity > 0", name="quantity_positive"),
    CheckConstraint("stored >= 0 AND written_off >= 0", name="counts_non_negative"),
    # Never more parts stored and written off than came off the plate.
    CheckConstraint("stored + written_off <= quantity", name="counts_within_quantity"),
    # The receiving area: what still waits for a box, first come first served.
    Index(
        "part_receipts_open_idx",
        "part_id",
        "created_at",
        postgresql_where=text("stored + written_off < quantity"),
    ),
    schema=SCHEMA,
)

part_ledger = Table(
    "part_ledger",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("part_id", Uuid, ForeignKey(PART_REFERENCE, ondelete="RESTRICT"), nullable=False),
    Column("reason", StrEnumType(PartMovementReason), nullable=False),
    Column("quantity", Integer, nullable=False),
    Column("from_location_id", Uuid, ForeignKey(locations.c.id, ondelete="RESTRICT")),
    Column("to_location_id", Uuid, ForeignKey(locations.c.id, ondelete="RESTRICT")),
    Column("receipt_id", Uuid, ForeignKey(part_receipts.c.id, ondelete="RESTRICT")),
    # The unit an assembly made: every kit knows the boxes its parts came from.
    Column("unit_id", Uuid, ForeignKey(units.c.id, ondelete="RESTRICT")),
    Column("note", Text, nullable=False, server_default=text("''")),
    Column("scan_id", Uuid, ForeignKey(scans.c.id, ondelete="RESTRICT")),
    Column("staff_id", Uuid, ForeignKey(ACCOUNT_REFERENCE, ondelete="RESTRICT")),
    Column(
        "reverses_id",
        BigInteger,
        ForeignKey("inventory.part_ledger.id", ondelete="RESTRICT"),
        unique=True,
    ),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "reason IN ('receive', 'assemble', 'count', 'write_off', 'undo')", name="reason"
    ),
    CheckConstraint("quantity > 0", name="quantity_positive"),
    # Where each kind of movement comes from and goes to.
    CheckConstraint(
        "CASE reason "
        "WHEN 'receive' THEN receipt_id IS NOT NULL "
        "AND from_location_id IS NULL AND to_location_id IS NOT NULL "
        "WHEN 'assemble' THEN unit_id IS NOT NULL "
        "AND from_location_id IS NOT NULL AND to_location_id IS NULL "
        "WHEN 'count' THEN (from_location_id IS NULL) <> (to_location_id IS NULL) "
        "WHEN 'write_off' THEN receipt_id IS NOT NULL "
        "AND from_location_id IS NULL AND to_location_id IS NULL "
        "ELSE from_location_id IS DISTINCT FROM to_location_id END",
        name="shape",
    ),
    CheckConstraint("unit_id IS NULL OR reason = 'assemble'", name="unit_for_assembly"),
    CheckConstraint("(reason = 'undo') = (reverses_id IS NOT NULL)", name="undo_reverses"),
    Index("part_ledger_part_idx", "part_id", "id"),
    Index("part_ledger_unit_idx", "unit_id", postgresql_where=text("unit_id IS NOT NULL")),
    Index("part_ledger_scan_idx", "scan_id", postgresql_where=text("scan_id IS NOT NULL")),
    schema=SCHEMA,
)
