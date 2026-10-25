"""Use cases of the scales: the staff add scales such as 1:24, correct and remove them.

A scale's code never changes: it is part of every SKU (``MB-000042-H0-B``) and of the
shop's addresses. A scale can be removed only while no product is offered in it and no
photo is tagged with it.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from modellbahn.modules.catalog.application.ports import CatalogUnitOfWork
from modellbahn.modules.catalog.domain.errors import (
    InvalidFieldError,
    ScaleInUseError,
    ScaleNotFoundError,
)
from modellbahn.modules.catalog.domain.model import UNSET, Maybe, Scale
from modellbahn.platform.uow import ForeignKeyViolationError, UniqueViolationError

type UnitOfWorkFactory = Callable[[], CatalogUnitOfWork]

# Two staff members adding the same scale at once: the database decides, the loser
# sees the same answer as if the check had caught it.
_UNIQUE_FIELDS: Final[dict[str, str]] = {"pk_scales": "code", "uq_scales_name": "name"}


@dataclass(frozen=True, slots=True)
class ScaleUsage:
    """A scale and how many products (in any state) are offered in it."""

    scale: Scale
    product_count: int


class ScaleService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory) -> None:
        self._uow = uow_factory

    async def list_scales(self) -> list[ScaleUsage]:
        """Every scale, the smallest models first."""
        async with self._uow() as uow:
            usage = await uow.references.scale_usage()
            return [
                ScaleUsage(scale, usage.get(scale.code, 0))
                for scale in await uow.references.scales()
            ]

    async def create_scale(
        self,
        *,
        code: str,
        name: str,
        ratio_denominator: Decimal,
        track_gauge_mm: Decimal | None,
    ) -> ScaleUsage:
        scale = Scale.create(
            code=code, name=name, ratio_denominator=ratio_denominator, track_gauge_mm=track_gauge_mm
        )
        async with self._uow() as uow:
            if await uow.references.scale_taken(code=scale.code):
                raise _duplicate("code")
            if await uow.references.scale_taken(name=scale.name):
                raise _duplicate("name")
            uow.references.add_scale(scale)
            await _commit(uow)
            return ScaleUsage(scale, 0)

    async def change_scale(
        self,
        code: str,
        *,
        name: Maybe[str] = UNSET,
        ratio_denominator: Maybe[Decimal] = UNSET,
        track_gauge_mm: Maybe[Decimal | None] = UNSET,
    ) -> ScaleUsage:
        async with self._uow() as uow:
            scale = await uow.references.get_scale(code, for_update=True)
            if scale is None:
                raise ScaleNotFoundError
            old_name = scale.name
            scale.change(
                name=name, ratio_denominator=ratio_denominator, track_gauge_mm=track_gauge_mm
            )
            if scale.name != old_name and await uow.references.scale_taken(
                name=scale.name, except_code=scale.code
            ):
                raise _duplicate("name")
            usage = await uow.references.scale_usage()
            await _commit(uow)
            return ScaleUsage(scale, usage.get(scale.code, 0))

    async def delete_scale(self, code: str) -> None:
        async with self._uow() as uow:
            scale = await uow.references.get_scale(code, for_update=True)
            if scale is None:
                raise ScaleNotFoundError
            if await uow.references.scale_in_use(scale.code):
                raise ScaleInUseError
            await uow.references.delete_scale(scale)
            await _commit(uow)


def _duplicate(field: str) -> InvalidFieldError:
    return InvalidFieldError(field, "duplicate", "another scale already uses it")


async def _commit(uow: CatalogUnitOfWork) -> None:
    try:
        await uow.commit()
    except UniqueViolationError as exc:
        field = _UNIQUE_FIELDS.get(exc.constraint or "")
        if field is None:
            raise
        raise _duplicate(field) from exc
    except ForeignKeyViolationError as exc:
        # Offered in the scale by a product saved between the check and the delete.
        raise ScaleInUseError from exc
