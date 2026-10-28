"""What other modules may know about the fairs: the next one, for a line in a mail.

A read facade over the site tables inside the caller's transaction.
"""

from datetime import date

from sqlalchemy import select

from modellbahn.modules.site.contracts.next_fair import NextFair
from modellbahn.modules.site.infrastructure.tables import fairs
from modellbahn.platform.uow import UnitOfWork


async def load_next_fair(uow: UnitOfWork, today: date) -> NextFair | None:
    """The first published fair that has not ended before ``today``; None if there is none."""
    row = (
        await uow.session.execute(
            select(
                fairs.c.name,
                fairs.c.city,
                fairs.c.venue,
                fairs.c.booth,
                fairs.c.starts_on,
                fairs.c.ends_on,
            )
            .where(fairs.c.published, fairs.c.ends_on >= today)
            .order_by(fairs.c.starts_on, fairs.c.name)
            .limit(1)
        )
    ).one_or_none()
    return None if row is None else NextFair(*row)
