"""Manufacturing: printers and their state, materials, parts, bills of materials, print jobs.

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``catalog.product_scales`` gets a unique key on ``(id, scale_code)``: the bills of
  materials refer to it, so their parts fit the scale.
- ``manufacturing.print_job_number_seq`` numbers the jobs for people (Druck 17).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TECHNOLOGIES = "'fdm', 'resin'"
_PRINTER_STATUSES = "'in_service', 'defective', 'in_repair', 'retired'"


def upgrade() -> None:
    op.execute("CREATE SCHEMA manufacturing")
    op.execute("CREATE SEQUENCE manufacturing.print_job_number_seq")
    op.create_unique_constraint(
        "uq_product_scales_id_scale_code", "product_scales", ["id", "scale_code"], schema="catalog"
    )
    _create_printers()
    _create_materials()
    _create_parts()
    _create_boms()
    _create_print_jobs()


def _create_printers() -> None:
    op.create_table(
        "printers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("model", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("technology", sa.Text(), nullable=False),
        sa.Column("build_x_mm", sa.SmallInteger(), nullable=True),
        sa.Column("build_y_mm", sa.SmallInteger(), nullable=True),
        sa.Column("build_z_mm", sa.SmallInteger(), nullable=True),
        sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        # Why it is in this state: "Düse verstopft", "Ersatzteil bestellt".
        sa.Column("status_note", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_printers"),
        sa.UniqueConstraint("code", name="uq_printers_code"),
        sa.UniqueConstraint("id", "technology", name="uq_printers_id_technology"),
        sa.CheckConstraint("code ~ '^[A-Z0-9]{1,8}$'", name="ck_printers_code_format"),
        sa.CheckConstraint(f"technology IN ({_TECHNOLOGIES})", name="ck_printers_technology"),
        sa.CheckConstraint(f"status IN ({_PRINTER_STATUSES})", name="ck_printers_status"),
        sa.CheckConstraint(
            "(build_x_mm IS NULL) = (build_y_mm IS NULL) "
            "AND (build_y_mm IS NULL) = (build_z_mm IS NULL)",
            name="ck_printers_build_volume_complete",
        ),
        sa.CheckConstraint(
            "build_x_mm IS NULL OR (build_x_mm BETWEEN 1 AND 2000 "
            "AND build_y_mm BETWEEN 1 AND 2000 AND build_z_mm BETWEEN 1 AND 2000)",
            name="ck_printers_build_volume_range",
        ),
        schema="manufacturing",
    )
    op.create_table(
        "printer_status_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("printer_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("staff_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_printer_status_reports"),
        sa.ForeignKeyConstraint(
            ["printer_id"],
            ["manufacturing.printers.id"],
            name="fk_printer_status_reports_printer_id_printers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["identity.accounts.id"],
            name="fk_printer_status_reports_staff_id_accounts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            f"(from_status IS NULL OR from_status IN ({_PRINTER_STATUSES})) "
            f"AND to_status IN ({_PRINTER_STATUSES})",
            name="ck_printer_status_reports_statuses",
        ),
        schema="manufacturing",
    )
    op.create_index(
        "printer_status_reports_printer_idx",
        "printer_status_reports",
        ["printer_id", "occurred_at"],
        schema="manufacturing",
    )


def _create_materials() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("technology", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_materials"),
        sa.UniqueConstraint("name", name="uq_materials_name"),
        sa.UniqueConstraint("id", "technology", name="uq_materials_id_technology"),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 60", name="ck_materials_name_length"),
        sa.CheckConstraint(f"technology IN ({_TECHNOLOGIES})", name="ck_materials_technology"),
        schema="manufacturing",
    )


def _create_parts() -> None:
    op.create_table(
        "parts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("part_number", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("scale_code", sa.Text(), nullable=False),
        sa.Column("technology", sa.Text(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=True),
        sa.Column("layer_height_um", sa.SmallInteger(), nullable=True),
        sa.Column("plate_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "parts_per_plate", sa.SmallInteger(), server_default=sa.text("1"), nullable=False
        ),
        # Grams of filament or millilitres of resin for one part, supports included.
        sa.Column("material_per_part", sa.Numeric(8, 2), nullable=True),
        sa.Column("notes", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_parts"),
        sa.UniqueConstraint("part_number", name="uq_parts_part_number"),
        sa.UniqueConstraint("id", "scale_code", name="uq_parts_id_scale_code"),
        sa.UniqueConstraint("id", "technology", name="uq_parts_id_technology"),
        sa.ForeignKeyConstraint(
            ["scale_code"],
            ["catalog.scales.code"],
            name="fk_parts_scale_code_scales",
            ondelete="RESTRICT",
        ),
        # No resin part made of filament.
        sa.ForeignKeyConstraint(
            ["material_id", "technology"],
            ["manufacturing.materials.id", "manufacturing.materials.technology"],
            name="fk_parts_material_id_technology_materials",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "part_number ~ '^[A-Z0-9]+(-[A-Z0-9]+)*$' AND char_length(part_number) <= 40",
            name="ck_parts_part_number_format",
        ),
        sa.CheckConstraint("char_length(name) BETWEEN 1 AND 120", name="ck_parts_name_length"),
        sa.CheckConstraint(f"technology IN ({_TECHNOLOGIES})", name="ck_parts_technology"),
        sa.CheckConstraint(
            "layer_height_um IS NULL OR layer_height_um BETWEEN 10 AND 1000",
            name="ck_parts_layer_height",
        ),
        sa.CheckConstraint(
            "plate_minutes IS NULL OR plate_minutes BETWEEN 1 AND 10080",
            name="ck_parts_plate_minutes",
        ),
        sa.CheckConstraint("parts_per_plate BETWEEN 1 AND 1000", name="ck_parts_parts_per_plate"),
        sa.CheckConstraint(
            "material_per_part IS NULL OR material_per_part > 0",
            name="ck_parts_material_per_part",
        ),
        schema="manufacturing",
    )
    op.create_index(
        "parts_scale_idx", "parts", ["scale_code", "part_number"], schema="manufacturing"
    )


def _create_boms() -> None:
    op.create_table(
        "boms",
        sa.Column("product_scale_id", sa.Uuid(), nullable=False),
        sa.Column("scale_code", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("product_scale_id", name="pk_boms"),
        sa.UniqueConstraint(
            "product_scale_id", "scale_code", name="uq_boms_product_scale_id_scale_code"
        ),
        # The catalogue cannot drop the scale from the product while this exists.
        sa.ForeignKeyConstraint(
            ["product_scale_id", "scale_code"],
            ["catalog.product_scales.id", "catalog.product_scales.scale_code"],
            name="fk_boms_product_scale_id_scale_code_product_scales",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["identity.accounts.id"],
            name="fk_boms_updated_by_accounts",
            ondelete="RESTRICT",
        ),
        schema="manufacturing",
    )
    op.create_table(
        "bom_lines",
        sa.Column("product_scale_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("scale_code", sa.Text(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("product_scale_id", "part_id", name="pk_bom_lines"),
        sa.ForeignKeyConstraint(
            ["product_scale_id", "scale_code"],
            ["manufacturing.boms.product_scale_id", "manufacturing.boms.scale_code"],
            name="fk_bom_lines_product_scale_id_scale_code_boms",
            ondelete="CASCADE",
        ),
        # Only parts of the kit's scale.
        sa.ForeignKeyConstraint(
            ["part_id", "scale_code"],
            ["manufacturing.parts.id", "manufacturing.parts.scale_code"],
            name="fk_bom_lines_part_id_scale_code_parts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity BETWEEN 1 AND 999", name="ck_bom_lines_quantity"),
        sa.CheckConstraint("position >= 0", name="ck_bom_lines_position_non_negative"),
        schema="manufacturing",
    )
    op.create_index("bom_lines_part_idx", "bom_lines", ["part_id"], schema="manufacturing")


def _create_print_jobs() -> None:
    op.create_table(
        "print_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("printer_id", sa.Uuid(), nullable=False),
        sa.Column("technology", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("planned_minutes", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("failure_reason", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by", sa.Uuid(), nullable=True),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_print_jobs"),
        sa.UniqueConstraint("number", name="uq_print_jobs_number"),
        sa.UniqueConstraint("id", "technology", name="uq_print_jobs_id_technology"),
        # Only on a printer of the job's technology.
        sa.ForeignKeyConstraint(
            ["printer_id", "technology"],
            ["manufacturing.printers.id", "manufacturing.printers.technology"],
            name="fk_print_jobs_printer_id_technology_printers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["identity.accounts.id"],
            name="fk_print_jobs_created_by_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["started_by"],
            ["identity.accounts.id"],
            name="fk_print_jobs_started_by_accounts",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["finished_by"],
            ["identity.accounts.id"],
            name="fk_print_jobs_finished_by_accounts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"technology IN ({_TECHNOLOGIES})", name="ck_print_jobs_technology"),
        sa.CheckConstraint(
            "status IN ('queued', 'printing', 'post_processing', 'done', 'failed', 'cancelled')",
            name="ck_print_jobs_status",
        ),
        sa.CheckConstraint(
            "planned_minutes IS NULL OR planned_minutes BETWEEN 1 AND 10080",
            name="ck_print_jobs_planned_minutes",
        ),
        sa.CheckConstraint(
            "(status IN ('queued', 'cancelled')) = (started_at IS NULL)",
            name="ck_print_jobs_started_at",
        ),
        sa.CheckConstraint(
            "status NOT IN ('post_processing', 'done') OR printed_at IS NOT NULL",
            name="ck_print_jobs_printed_at",
        ),
        sa.CheckConstraint(
            "(status IN ('done', 'failed', 'cancelled')) = (finished_at IS NOT NULL)",
            name="ck_print_jobs_finished_at",
        ),
        sa.CheckConstraint(
            "status = 'failed' OR failure_reason = ''", name="ck_print_jobs_failure_reason"
        ),
        schema="manufacturing",
    )
    # One plate at a time on a printer.
    op.create_index(
        "print_jobs_one_printing_idx",
        "print_jobs",
        ["printer_id"],
        unique=True,
        schema="manufacturing",
        postgresql_where=sa.text("status = 'printing'"),
    )
    op.create_index(
        "print_jobs_open_idx",
        "print_jobs",
        ["printer_id", "created_at"],
        schema="manufacturing",
        postgresql_where=sa.text("status IN ('queued', 'printing', 'post_processing')"),
    )
    op.create_index(
        "print_jobs_printer_idx", "print_jobs", ["printer_id", "created_at"], schema="manufacturing"
    )
    op.create_table(
        "print_job_lines",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("part_id", sa.Uuid(), nullable=False),
        sa.Column("technology", sa.Text(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("good", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("failed", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("job_id", "part_id", name="pk_print_job_lines"),
        sa.ForeignKeyConstraint(
            ["job_id", "technology"],
            ["manufacturing.print_jobs.id", "manufacturing.print_jobs.technology"],
            name="fk_print_job_lines_job_id_technology_print_jobs",
            ondelete="CASCADE",
        ),
        # Only parts of the printer's technology on its plate.
        sa.ForeignKeyConstraint(
            ["part_id", "technology"],
            ["manufacturing.parts.id", "manufacturing.parts.technology"],
            name="fk_print_job_lines_part_id_technology_parts",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("quantity BETWEEN 1 AND 1000", name="ck_print_job_lines_quantity"),
        sa.CheckConstraint(
            "good >= 0 AND failed >= 0", name="ck_print_job_lines_counts_non_negative"
        ),
        sa.CheckConstraint(
            "good + failed <= quantity", name="ck_print_job_lines_counts_within_quantity"
        ),
        sa.CheckConstraint("position >= 0", name="ck_print_job_lines_position_non_negative"),
        schema="manufacturing",
    )
    op.create_index(
        "print_job_lines_part_idx", "print_job_lines", ["part_id"], schema="manufacturing"
    )


def downgrade() -> None:
    op.drop_table("print_job_lines", schema="manufacturing")
    op.drop_table("print_jobs", schema="manufacturing")
    op.drop_table("bom_lines", schema="manufacturing")
    op.drop_table("boms", schema="manufacturing")
    op.drop_table("parts", schema="manufacturing")
    op.drop_table("materials", schema="manufacturing")
    op.drop_table("printer_status_reports", schema="manufacturing")
    op.drop_table("printers", schema="manufacturing")
    op.drop_constraint("uq_product_scales_id_scale_code", "product_scales", schema="catalog")
    op.execute("DROP SEQUENCE manufacturing.print_job_number_seq")
    op.execute("DROP SCHEMA manufacturing")
