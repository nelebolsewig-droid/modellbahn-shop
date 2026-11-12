"""Labels for units, locations and parts: what each shows, rendered by a :class:`LabelRenderer`.

Johann's till (SumUp) reads barcodes only, so labels carry barcodes, not QR codes. A
unit's label shows the variant's EAN-13 (the till rings up the article by it), a
Code 128 with the unit's own code, the product and its article number. A location's
label shows a large Code 128 with its code and its name; a part's label, stuck on the
box its parts lie in, the same with the part number. The workshop's scanner reads all
of them.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from modellbahn.modules.inventory.application.common import UnitOfWorkFactory
from modellbahn.modules.inventory.application.ports import Label, LabelRenderer, LabelSheet
from modellbahn.modules.inventory.domain.codes import format_unit_code, normalize_unit_code
from modellbahn.modules.inventory.domain.errors import InvalidFieldError
from modellbahn.modules.inventory.domain.model import LocationKind
from modellbahn.modules.manufacturing.contracts.parts import Technology
from modellbahn.platform.money import format_euro

LABELS_PER_PRINT_MAX: Final = 240
A4_LABELS_PER_SHEET: Final = 24

_KIND_NAMES: Final = {
    LocationKind.SITE: "Lager",
    LocationKind.SHELF: "Regal",
    LocationKind.COMPARTMENT: "Fach",
    LocationKind.BOX: "Box",
    LocationKind.STAGING: "Ablage",
}


_TECHNOLOGY_NAMES: Final = {Technology.FDM: "Filament", Technology.RESIN: "Resin"}

FILE_NAME_MAX_LENGTH: Final = 100
# Characters no file system takes (or Windows doesn't), and control characters.
_NOT_IN_FILE_NAMES: Final = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def file_name(text: str) -> str:
    """``IFA ADK 70 Autokran · H0 · Fertigmodell, Gelb`` → ``IFA ADK 70 Autokran H0
    Fertigmodell Gelb``: a name every system saves as it is (without extension)."""
    cleaned = _NOT_IN_FILE_NAMES.sub(" ", text.replace("·", " ").replace(",", " "))
    return " ".join(cleaned.split())[:FILE_NAME_MAX_LENGTH].strip(" .") or "Etiketten"


def document_name(subjects: Sequence[str]) -> str:
    """What a print of these labels is called: the one model (or place, or part) they
    are for, or the first and how many others."""
    distinct = list(dict.fromkeys(subjects))
    if not distinct:
        return "Etiketten"
    if len(distinct) == 1:
        return file_name(distinct[0])
    return file_name(f"{distinct[0]} und {len(distinct) - 1} weitere")


@dataclass(frozen=True, slots=True)
class PrintedLabels:
    pdf: bytes
    name: str
    """The file name without extension, after what the labels are for (:func:`document_name`)."""
    names: tuple[str, ...]
    """One file name per label, with its code: for one picture per label."""


@dataclass(frozen=True, slots=True)
class LabelRequest:
    unit_codes: Sequence[str]
    location_codes: Sequence[str]
    sheet: LabelSheet
    skip: int = 0
    """Labels of a started A4 sheet to leave empty (0 to 23)."""
    part_numbers: Sequence[str] = ()


class LabelService:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, renderer: LabelRenderer) -> None:
        self._uow = uow_factory
        self._renderer = renderer

    async def render(self, request: LabelRequest) -> PrintedLabels:
        """A PDF with the labels in the order asked for, named after what they are for
        (model and variant, e.g. ``IFA ADK 70 Autokran H0 Fertigmodell Gelb``); unknown
        codes are an error."""
        count = len(request.unit_codes) + len(request.location_codes) + len(request.part_numbers)
        if not 0 < count <= LABELS_PER_PRINT_MAX:
            raise InvalidFieldError(
                "unit_codes", "out_of_range", f"between 1 and {LABELS_PER_PRINT_MAX} labels"
            )
        if not 0 <= request.skip < A4_LABELS_PER_SHEET:
            raise InvalidFieldError("skip", "out_of_range", "0 to 23 labels")
        labels: list[Label] = []
        subjects: list[str] = []
        names: list[str] = []
        async with self._uow() as uow:
            for index, raw in enumerate(request.unit_codes):
                unit = await uow.units.get_by_code(normalize_unit_code(raw))
                if unit is None:
                    raise InvalidFieldError(f"unit_codes.{index}", "unknown", f"no unit {raw!r}")
                variant = (await uow.catalog.variants([unit.variant_id])).get(unit.variant_id)
                subject = file_name(variant.title) if variant else "Etikett"
                subjects.append(subject)
                names.append(file_name(f"{subject} {unit.code}"))
                labels.append(
                    Label(
                        caption="Einheit",
                        code128=unit.code,
                        ean13=variant.gtin if variant else None,
                        code_text=format_unit_code(unit.code),
                        title=variant.product_name if variant else "",
                        detail=variant.variant_name if variant else "",
                        reference=variant.sku if variant else "",
                        price=format_euro(variant.price_cents)
                        if variant and variant.price_cents > 0
                        else "",
                    )
                )
            for index, raw in enumerate(request.location_codes):
                location = await uow.locations.get_by_code(raw.strip().upper())
                if location is None:
                    raise InvalidFieldError(
                        f"location_codes.{index}", "unknown", f"no location {raw!r}"
                    )
                kind = _KIND_NAMES[location.kind]
                subjects.append(file_name(f"Platz {location.code}"))
                names.append(subjects[-1])
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
            for index, raw in enumerate(request.part_numbers):
                part = await uow.manufacturing.part_by_number(raw.strip().upper())
                if part is None:
                    raise InvalidFieldError(f"part_numbers.{index}", "unknown", f"no part {raw!r}")
                subjects.append(file_name(f"Teil {part.part_number} {part.name}"))
                names.append(subjects[-1])
                labels.append(
                    Label(
                        caption="Teil",
                        code128=part.part_number,
                        code_text=part.part_number,
                        title=part.name,
                        detail=part.scale_code,
                        reference=f"{part.scale_code} · {_TECHNOLOGY_NAMES[part.technology]}",
                    )
                )
        skip = request.skip if request.sheet is LabelSheet.A4_70X37 else 0
        name = document_name(subjects)
        pdf = self._renderer.render(labels, sheet=request.sheet, skip=skip, title=name)
        return PrintedLabels(pdf=pdf, name=name, names=tuple(names))
