"""The photo studio finishes the photos that were in the shop before it (ADR 0031).

Written by hand like the migrations before.

Migration 0022 left the existing photos as they were. They are now switched over with
the roll-out itself, without a click in the gallery: every finished photo whose studio
is off gets it switched on and is rendered again from its original, exactly as
``Asset.set_studio`` does it (status ``uploaded`` plus a ``media.asset.uploaded`` event).

The worker takes about five seconds and 1.3 GB per photo and handles events one after
the other. So that orders and mails are not held up behind a long row of photos, the
events fall due twenty seconds apart instead of all at once.

It runs once, here. A photo somebody switches off in the gallery afterwards stays off.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        WITH switched AS (
            UPDATE media.assets
            SET studio = true,
                status = 'uploaded',
                attempts = 0,
                failure_code = NULL,
                last_error = NULL,
                updated_at = now(),
                version = version + 1
            WHERE kind = 'image' AND NOT studio AND status IN ('ready', 'failed')
            RETURNING id, created_at
        )
        INSERT INTO platform.outbox
            (id, event_type, aggregate_type, aggregate_id, payload, occurred_at, next_attempt_at)
        SELECT gen_random_uuid(), 'media.asset.uploaded', 'media.asset', id, '{}'::jsonb, now(),
               now() + (row_number() OVER (ORDER BY created_at) - 1)
                       * interval '20 seconds'
        FROM switched
        """
    )


def downgrade() -> None:
    # The photos stay as the studio made them; they can be switched back in the gallery.
    pass
