"""Every model is made again when the shelves run short (ADR 0029).

Written by hand like the migrations before; constraint names follow the naming
convention of ``modellbahn.platform.db``.

- ``catalog.production_settings``: one row with the shop's lead time for pieces made
  again, two to four weeks to begin with. A variant without its own lead time follows it
  at read time, so changing it changes them all.
- ``catalog.variants.allow_backorder`` is on for every variant and by default: what is
  missing is made. A lead time a variant had while made to order stays as its own.
  Lead times of variants that were *not* made to order were never shown or used; they
  go, so those variants follow the shop's lead time like every other.
- A variant not made again (a one-off, a model no longer made) has no lead time of its
  own; one made again no longer needs one.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "production_settings",
        sa.Column("id", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("default_lead_time_min_weeks", sa.SmallInteger(), nullable=False),
        sa.Column("default_lead_time_max_weeks", sa.SmallInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_production_settings_single_row"),
        sa.CheckConstraint(
            "default_lead_time_min_weeks BETWEEN 1 AND 52 "
            "AND default_lead_time_max_weeks BETWEEN default_lead_time_min_weeks AND 52",
            name="ck_production_settings_default_lead_time_range",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_production_settings"),
        schema="catalog",
    )
    # Two to four weeks to begin with.
    op.execute(
        "INSERT INTO catalog.production_settings "
        "(id, default_lead_time_min_weeks, default_lead_time_max_weeks, updated_at) "
        "VALUES (1, 2, 4, now())"
    )
    op.drop_constraint(
        "ck_variants_made_to_order_lead_time", "variants", schema="catalog", type_="check"
    )
    op.execute(
        "UPDATE catalog.variants SET lead_time_min_weeks = NULL, lead_time_max_weeks = NULL "
        "WHERE NOT allow_backorder"
    )
    op.execute("UPDATE catalog.variants SET allow_backorder = true WHERE NOT allow_backorder")
    op.alter_column("variants", "allow_backorder", server_default=sa.text("true"), schema="catalog")
    op.create_check_constraint(
        "ck_variants_lead_time_only_made_again",
        "variants",
        "allow_backorder OR lead_time_min_weeks IS NULL",
        schema="catalog",
    )


def downgrade() -> None:
    # The older model knows no shop lead time: variants made again without their own get
    # a copy of it, so they stay made to order as they are now.
    op.drop_constraint(
        "ck_variants_lead_time_only_made_again", "variants", schema="catalog", type_="check"
    )
    op.execute(
        "UPDATE catalog.variants v SET "
        "lead_time_min_weeks = s.default_lead_time_min_weeks, "
        "lead_time_max_weeks = s.default_lead_time_max_weeks "
        "FROM catalog.production_settings s "
        "WHERE v.allow_backorder AND v.lead_time_min_weeks IS NULL"
    )
    op.alter_column(
        "variants", "allow_backorder", server_default=sa.text("false"), schema="catalog"
    )
    op.create_check_constraint(
        "ck_variants_made_to_order_lead_time",
        "variants",
        "NOT allow_backorder OR lead_time_min_weeks IS NOT NULL",
        schema="catalog",
    )
    op.drop_table("production_settings", schema="catalog")
