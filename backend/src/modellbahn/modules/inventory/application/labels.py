"""Labels for units and locations: what each shows, rendered by a :class:`LabelRenderer`.

Johann's till (SumUp) reads barcodes only, so labels carry barcodes, not QR codes. A
unit's label shows the variant's EAN-13 (the till rings up the article by it), a
Code 128 with the unit's own code, the product and its article number. A location's
label shows a large Code 128 with its code and its name. The workshop's scanner reads
all of them.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from modellbahn.modules.inventory.application.common import UnitOfWorkFactory
from modellbahn.modules.inventory.application.ports import Label, LabelRenderer, LabelSheet
from modellbahn.modules.inventory.domain.codes import format_unit_code, normalize_unit_code
from modellbahn.modules.inventory.domain.errors import InvalidFieldError
from modellbahn.modules.inventory.domain.model import LocationKind

LABELS_PER_PRINT_MAX: Final = 240
A4_LABELS_PER_SHEET: Final = 24

_KIND_NAMES: Final = {
    LocationKind.SITE: "Lager",
    LocationKind.SHELF: "Regal",
    LocationKind.COMPARTMENT: "Fach",
    LocationKind.BOX: "Box",
    LocationKind.STAGING: "Ablage",
}


@dataclass(frozen=True, slots=True)
class LabelRequest:
    unit_codes: Sequence[str]
    location_codes: Sequence[str]
    sheet: LabelSheet
    skip: int = 0
    """Labels of a started A4 sheet to leave empty (0 to 23)."""


class LabelService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, renderer: LabelRenderer) -> None:
        self._uow = uow_factory
        self._renderer = renderer

    async def render(self, request: LabelRequest) -> bytes:
        """A PDF with the labels in the order asked for; unknown codes are an error."""
        count = len(request.unit_codes) + len(request.location_codes)
        if not 0 < count <= LABELS_PER_PRINT_MAX:
            raise InvalidFieldError(
                "unit_codes", "out_of_range", f"between 1 and {LABELS_PER_PRINT_MAX} labels"
            )
        if not 0 <= request.skip < A4_LABELS_PER_SHEET:
            raise InvalidFieldError("skip", "out_of_range", "0 to 23 labels")
        labels: list[Label] = []
        async with self._uow() as uow:
            for index, raw in enumerate(request.unit_codes):
                unit = await uow.units.get_by_code(normalize_unit_code(raw))
                if unit is None:
                    raise InvalidFieldError(f"unit_codes.{index}", "unknown", f"no unit {raw!r}")
                variant = (await uow.catalog.variants([unit.variant_id])).get(unit.variant_id)
                labels.append(
                    Label(
                        caption="Einheit",
                        code128=unit.code,
                        ean13=variant.gtin if variant else None,
                        code_text=format_unit_code(unit.code),
                        title=variant.product_name if variant else "",
                        detail=f"{variant.scale_name} · {variant.finish_name}" if variant else "",
                        reference=variant.sku if variant else "",
                    )
                )
            for index, raw in enumerate(request.location_codes):
                location = await uow.locations.get_by_code(raw.strip().upper())
                if location is None:
                    raise InvalidFieldError(
                        f"location_codes.{index}", "unknown", f"no location {raw!r}"
                    )
                kind = _KIND_NAMES[location.kind]
                labels.append(
                    Label(
                        caption="Lagerplatz",
                        code128=location.code,
                        code_text=location.code,
                        title=location.name or kind,
                        detail=kind,
                        reference=location.path.replace(".", " / "),
                    )
                )
        skip = request.skip if request.sheet is LabelSheet.A4_70X37 else 0
        return self._renderer.render(labels, sheet=request.sheet, skip=skip)
