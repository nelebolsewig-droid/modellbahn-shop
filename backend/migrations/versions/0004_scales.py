"""Scales instead of gauges: decimal ratios, optional track gauge, more scales.

The shop sorts by scale (Maßstab), not by track gauge: road vehicles have a scale but
run on no track, and scales such as G (1:22.5) need a decimal ratio. Scales become
reference data the staff maintain; their order follows the ratio, so ``position`` goes.
Written by hand like the migrations before.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The scales 0002 seeded; downgrading keeps only these.
_GAUGES_OF_0002 = ("H0", "TT", "N")


def upgrade() -> None:
    op.drop_constraint("ck_scales_ratio_positive", "scales", schema="catalog", type_="check")
    op.alter_column(
        "scales",
        "ratio_denominator",
        type_=sa.Numeric(5, 1),
        postgresql_using="ratio_denominator::numeric(5, 1)",
        schema="catalog",
    )
    op.alter_column("scales", "track_gauge_mm", nullable=True, schema="catalog")
    op.drop_column("scales", "position", schema="catalog")
    op.create_check_constraint(
        "ck_scales_ratio_range",
        "scales",
        "ratio_denominator > 1 AND ratio_denominator <= 1000",
        schema="catalog",
    )
    op.create_check_constraint(
        "ck_scales_track_gauge_positive",
        "scales",
        "track_gauge_mm IS NULL OR track_gauge_mm > 0",
        schema="catalog",
    )
    # The code is part of every SKU (MB-000042-H0-B) and of the shop's addresses.
    op.create_check_constraint(
        "ck_scales_code_format", "scales", "code ~ '^[A-Z0-9]{1,4}$'", schema="catalog"
    )
    op.create_unique_constraint("uq_scales_name", "scales", ["name"], schema="catalog")

    scales = sa.table(
        "scales",
        sa.column("code", sa.Text()),
        sa.column("name", sa.Text()),
        sa.column("ratio_denominator", sa.Numeric(5, 1)),
        sa.column("track_gauge_mm", sa.Numeric(4, 1)),
        schema="catalog",
    )
    op.bulk_insert(
        scales,
        [
            {"code": "Z", "name": "Z", "ratio_denominator": 220, "track_gauge_mm": 6.5},
            {"code": "0", "name": "0", "ratio_denominator": 45, "track_gauge_mm": 32.0},
            {"code": "G", "name": "G", "ratio_denominator": 22.5, "track_gauge_mm": 45.0},
            # Road vehicles: a scale without a track.
            {"code": "125", "name": "1:25", "ratio_denominator": 25, "track_gauge_mm": None},
            {"code": "124", "name": "1:24", "ratio_denominator": 24, "track_gauge_mm": None},
        ],
    )


def downgrade() -> None:
    # Fails while a product still uses one of the newer scales: nothing is lost silently.
    op.execute(
        sa.text("DELETE FROM catalog.scales WHERE code NOT IN :codes").bindparams(
            sa.bindparam("codes", value=_GAUGES_OF_0002, expanding=True)
        )
    )
    op.drop_constraint("uq_scales_name", "scales", schema="catalog", type_="unique")
    op.drop_constraint("ck_scales_code_format", "scales", schema="catalog", type_="check")
    op.drop_constraint("ck_scales_track_gauge_positive", "scales", schema="catalog", type_="check")
    op.drop_constraint("ck_scales_ratio_range", "scales", schema="catalog", type_="check")
    op.add_column(
        "scales",
        sa.Column("position", sa.SmallInteger(), nullable=False, server_default="0"),
        schema="catalog",
    )
    op.execute(
        "UPDATE catalog.scales SET position = CASE code "
        "WHEN 'H0' THEN 1 WHEN 'TT' THEN 2 WHEN 'N' THEN 3 ELSE 0 END"
    )
    op.alter_column("scales", "position", server_default=None, schema="catalog")
    op.alter_column("scales", "track_gauge_mm", nullable=False, schema="catalog")
    op.alter_column(
        "scales",
        "ratio_denominator",
        type_=sa.SmallInteger(),
        postgresql_using="round(ratio_denominator)::smallint",
        schema="catalog",
    )
    op.create_check_constraint(
        "ck_scales_ratio_positive", "scales", "ratio_denominator > 0", schema="catalog"
    )
