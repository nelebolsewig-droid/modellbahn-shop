"""Request and response bodies of the inventory API (snake_case JSON)."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.inventory.application.allocation import PickItem, PickList, PieceState
from modellbahn.modules.inventory.application.availability import VariantAvailability
from modellbahn.modules.inventory.application.labels import (
    A4_LABELS_PER_SHEET,
    LABELS_PER_PRINT_MAX,
)
from modellbahn.modules.inventory.application.locations import LocationContents, LocationNode
from modellbahn.modules.inventory.application.ports import LabelSheet
from modellbahn.modules.inventory.application.scanning import (
    LOCATION_CONTEXT,
    ORDER_CONTEXT,
)
from modellbahn.modules.inventory.application.units import (
    HistoryEntry,
    StockLine,
    UnitDetails,
    UnitView,
)
from modellbahn.modules.inventory.domain.availability import Availability
from modellbahn.modules.inventory.domain.codes import format_unit_code
from modellbahn.modules.inventory.domain.model import (
    LOCATION_NAME_MAX_LENGTH,
    SCRAP_NOTE_MAX_LENGTH,
    UNITS_PER_BATCH_MAX,
    Location,
    LocationKind,
    MovementReason,
    ScanMode,
    ScanOutcome,
    UnitStatus,
)
from modellbahn.modules.inventory.domain.scanning import MAX_RAW_LENGTH, CodeKind
from modellbahn.modules.sales.contracts.orders import OrderStatus


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- Locations ------------------------------------------------------------------------


class LocationOut(BaseModel):
    id: UUID
    code: str = Field(examples=["R02-F04-B12"])
    path: str = Field(examples=["LAGER.R02.F04.B12"])
    kind: LocationKind
    name: str
    parent_id: UUID | None
    holds_goods: bool
    depth: int

    @classmethod
    def from_location(cls, location: Location) -> Self:
        return cls(
            id=location.id,
            code=location.code,
            path=location.path,
            kind=location.kind,
            name=location.name,
            parent_id=location.parent_id,
            holds_goods=location.holds_goods,
            depth=location.depth,
        )


class LocationNodeOut(LocationOut):
    unit_count: int = Field(description="Units lying in this location itself.")
    total_count: int = Field(description="Units in this location and everything below it.")

    @classmethod
    def from_node(cls, node: LocationNode) -> Self:
        return cls(
            **LocationOut.from_location(node.location).model_dump(),
            unit_count=node.unit_count,
            total_count=node.total_count,
        )


class LocationTreeOut(BaseModel):
    items: list[LocationNodeOut] = Field(
        description="Path order: every parent before its children."
    )


class LocationCreateIn(_Request):
    parent_code: str | None = Field(
        default=None, max_length=44, description="Empty for a site.", examples=["R02-F04"]
    )
    segment: str = Field(min_length=1, max_length=8, examples=["B12"])
    kind: LocationKind
    name: str = Field(default="", max_length=LOCATION_NAME_MAX_LENGTH)


class LocationPatchIn(_Request):
    name: str = Field(max_length=LOCATION_NAME_MAX_LENGTH)


# --- Units ----------------------------------------------------------------------------


class VariantRefOut(BaseModel):
    """The variant a unit is a piece of, as the catalogue names it now."""

    variant_id: UUID
    product_id: UUID
    product_slug: str
    title: str = Field(examples=["Stellwerk Altenau · H0 · bemalt"])
    sku: str = Field(examples=["MB-000042-H0-B"])
    gtin: str
    allow_backorder: bool

    @classmethod
    def from_variant(cls, variant: SaleVariant) -> Self:
        return cls(
            variant_id=variant.variant_id,
            product_id=variant.product_id,
            product_slug=variant.product_slug,
            title=variant.title,
            sku=variant.sku,
            gtin=variant.gtin,
            allow_backorder=variant.allow_backorder,
        )


class UnitOut(BaseModel):
    id: UUID
    code: str = Field(examples=["7KQ2X9F4MZ"])
    display_code: str = Field(examples=["7KQ2 X9F4 MZ"], description="Grouped for reading.")
    status: UnitStatus
    variant_id: UUID
    variant: VariantRefOut | None
    location: LocationOut | None
    order_id: UUID | None
    order_number: str | None
    scrap_note: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_view(cls, view: UnitView) -> Self:
        unit = view.unit
        return cls(
            id=unit.id,
            code=unit.code,
            display_code=format_unit_code(unit.code),
            status=unit.status,
            variant_id=unit.variant_id,
            variant=VariantRefOut.from_variant(view.variant) if view.variant else None,
            location=LocationOut.from_location(view.location) if view.location else None,
            order_id=view.order_id,
            order_number=view.order_number,
            scrap_note=unit.scrap_note,
            created_at=unit.created_at,
            updated_at=unit.updated_at,
        )


class UnitBatchOut(BaseModel):
    items: list[UnitOut]


class HistoryEntryOut(BaseModel):
    id: int
    reason: MovementReason
    from_status: UnitStatus | None
    to_status: UnitStatus
    from_location_code: str | None
    to_location_code: str | None
    order_number: str | None
    staff_name: str | None
    scan_id: UUID | None
    reverses_id: int | None
    occurred_at: datetime

    @classmethod
    def from_entry(cls, item: HistoryEntry) -> Self:
        entry = item.entry
        if entry.id is None:  # pragma: no cover - entries are read after they were stored
            msg = "journal entry without id"
            raise ValueError(msg)
        return cls(
            id=entry.id,
            reason=entry.reason,
            from_status=entry.from_status,
            to_status=entry.to_status,
            from_location_code=item.from_location.code if item.from_location else None,
            to_location_code=item.to_location.code if item.to_location else None,
            order_number=item.order_number,
            staff_name=item.staff_name,
            scan_id=entry.scan_id,
            reverses_id=entry.reverses_id,
            occurred_at=entry.occurred_at,
        )


class UnitDetailsOut(UnitOut):
    history: list[HistoryEntryOut] = Field(description="Oldest first.")

    @classmethod
    def from_details(cls, details: UnitDetails) -> Self:
        return cls(
            **UnitOut.from_view(details.view).model_dump(),
            history=[HistoryEntryOut.from_entry(item) for item in details.history],
        )


class UnitsCreateIn(_Request):
    variant_id: UUID
    quantity: int = Field(ge=1, le=UNITS_PER_BATCH_MAX)
    location_code: str | None = Field(
        default=None,
        max_length=44,
        description="Put the units away here at once; otherwise they wait for a scan.",
    )


class ScrapIn(_Request):
    note: str = Field(default="", max_length=SCRAP_NOTE_MAX_LENGTH)


class LocatedUnitOut(BaseModel):
    code: str
    display_code: str
    status: UnitStatus
    variant_id: UUID
    title: str | None
    sku: str | None
    location_code: str | None
    order_number: str | None


class LocationContentsOut(BaseModel):
    location: LocationNodeOut
    ancestors: list[LocationOut] = Field(description="From the site down to the parent.")
    children: list[LocationNodeOut]
    units: list[LocatedUnitOut] = Field(description="In this location and below it, oldest first.")

    @classmethod
    def from_contents(cls, contents: LocationContents) -> Self:
        units = []
        for unit in contents.units:
            variant = contents.variants.get(unit.variant_id)
            location = contents.locations.get(unit.location_id) if unit.location_id else None
            units.append(
                LocatedUnitOut(
                    code=unit.code,
                    display_code=format_unit_code(unit.code),
                    status=unit.status,
                    variant_id=unit.variant_id,
                    title=variant.title if variant else None,
                    sku=variant.sku if variant else None,
                    location_code=location.code if location else None,
                    order_number=contents.order_numbers.get(unit.allocation_id)
                    if unit.allocation_id
                    else None,
                )
            )
        return cls(
            location=LocationNodeOut.from_node(contents.node),
            ancestors=[LocationOut.from_location(location) for location in contents.ancestors],
            children=[LocationNodeOut.from_node(child) for child in contents.children],
            units=units,
        )


class StockLineOut(BaseModel):
    variant_id: UUID
    variant: VariantRefOut | None
    labeled: int = Field(description="Labelled, not yet put away.")
    in_stock: int = Field(description="On the shelves and free: what the shop can sell.")
    allocated: int = Field(description="On the shelves, reserved for an order.")
    picked: int = Field(description="Picked for an order, being packed.")
    backordered: int = Field(description="Paid pieces still waiting for a unit.")

    @classmethod
    def from_line(cls, line: StockLine) -> Self:
        return cls(
            variant_id=line.variant_id,
            variant=VariantRefOut.from_variant(line.variant) if line.variant else None,
            labeled=line.labeled,
            in_stock=line.in_stock,
            allocated=line.allocated,
            picked=line.picked,
            backordered=line.backordered,
        )


class StockOut(BaseModel):
    items: list[StockLineOut]


# --- Scans ----------------------------------------------------------------------------


class ScanIn(_Request):
    scan_id: UUID = Field(description="Generated on the device; repeat it when retrying.")
    raw: str = Field(
        min_length=1, max_length=MAX_RAW_LENGTH, examples=["https://shop/u/7KQ2X9F4MZ"]
    )
    mode: ScanMode
    source: Literal["camera", "scanner", "keyboard"]
    context: dict[Literal["location_code", "order_id"], str] = Field(
        default_factory=dict,
        description=f"`{LOCATION_CONTEXT}` when putting away, `{ORDER_CONTEXT}` when picking.",
    )


class ScanResolvedOut(BaseModel):
    kind: CodeKind
    code: str


class ScanUnitOut(BaseModel):
    code: str
    status: UnitStatus
    variant_id: UUID
    title: str | None
    sku: str | None
    location_code: str | None
    order_id: UUID | None
    order_number: str | None


class ScanLocationOut(BaseModel):
    code: str
    name: str
    kind: LocationKind
    holds_goods: bool
    unit_count: int


class ScanVariantOut(BaseModel):
    variant_id: UUID
    title: str
    sku: str
    free_units: int


class ScanEffectOut(BaseModel):
    unit_code: str | None = Field(description="The unit the scan moved.")
    from_status: UnitStatus | None
    to_status: UnitStatus
    from_location: str | None
    to_location: str | None
    reserved_for: str | None = Field(description="Order number a stored unit went to at once.")
    released_unit: str | None = Field(description="Unit given back when another one was picked.")


class ScanProgressOut(BaseModel):
    picked: int
    total: int


class ScanExpectedOut(BaseModel):
    unit_code: str | None
    sku: str
    title: str
    location_code: str | None
    location_name: str | None


ScanMessage = Literal[
    "unknown_code",
    "not_found",
    "unit",
    "location",
    "variant",
    "location_selected",
    "location_required",
    "location_unknown",
    "holds_no_goods",
    "already_there",
    "unit_gone",
    "unit_picked",
    "put_away",
    "move",
    "scan_unit_label",
    "order_unknown",
    "order_not_pickable",
    "picked",
    "already_picked",
    "reserved_for_other_order",
    "variant_complete",
    "not_in_order",
    "unit_not_stored",
    "no_unit_to_store",
    "variant_not_in_stock",
]


class ScanOut(BaseModel):
    """The answer to a scan; the same scan id always gets the same answer."""

    scan_id: UUID
    mode: ScanMode
    outcome: ScanOutcome
    message: ScanMessage = Field(description="Stable code the client turns into text.")
    resolved: ScanResolvedOut | None
    unit: ScanUnitOut | None
    location: ScanLocationOut | None
    variant: ScanVariantOut | None
    effect: ScanEffectOut | None
    progress: ScanProgressOut | None
    next_expected: ScanExpectedOut | None
    undoable: bool
    undone: bool


# --- Picking --------------------------------------------------------------------------


class PickItemOut(BaseModel):
    allocation_id: UUID
    order_line_id: UUID
    position: int
    piece: int
    variant_id: UUID
    sku: str
    title: str
    state: PieceState
    unit_code: str | None
    location: LocationOut | None

    @classmethod
    def from_item(cls, item: PickItem) -> Self:
        return cls(
            allocation_id=item.allocation_id,
            order_line_id=item.order_line_id,
            position=item.position,
            piece=item.piece,
            variant_id=item.variant_id,
            sku=item.sku,
            title=item.title,
            state=item.state,
            unit_code=item.unit_code,
            location=LocationOut.from_location(item.location) if item.location else None,
        )


class PickListOut(BaseModel):
    order_id: UUID
    order_number: str
    order_status: OrderStatus
    ship_recipient: str
    allocated: bool = Field(description="False for an order paid before the workshop allocated.")
    complete: bool = Field(description="Every piece picked: the parcel can be packed.")
    picked: int
    total: int
    items: list[PickItemOut] = Field(description="Walking order: by location, backorders after.")

    @classmethod
    def from_pick_list(cls, pick_list: PickList) -> Self:
        order = pick_list.order
        return cls(
            order_id=order.id,
            order_number=order.number,
            order_status=order.status,
            ship_recipient=order.ship_recipient,
            allocated=pick_list.is_allocated,
            complete=pick_list.is_complete,
            picked=pick_list.picked,
            total=pick_list.total,
            items=[PickItemOut.from_item(item) for item in pick_list.items],
        )


# --- Labels ---------------------------------------------------------------------------


class LabelsIn(_Request):
    unit_codes: list[Annotated[str, Field(max_length=20)]] = Field(
        default_factory=list, max_length=LABELS_PER_PRINT_MAX
    )
    location_codes: list[Annotated[str, Field(max_length=44)]] = Field(
        default_factory=list, max_length=LABELS_PER_PRINT_MAX
    )
    sheet: LabelSheet = Field(
        description="`a4_70x37`: A4 sheet, 3 x 8 labels; `ql_62x29`: Brother QL, 62 mm roll."
    )
    skip: int = Field(
        default=0,
        ge=0,
        lt=A4_LABELS_PER_SHEET,
        description="Labels of a started A4 sheet to leave empty.",
    )


# --- Shop -----------------------------------------------------------------------------


class VariantAvailabilityOut(BaseModel):
    variant_id: UUID
    availability: Availability = Field(
        description="`in_stock`: ships at once; `made_to_order`: printed for the customer; "
        "`unavailable`: not for sale right now."
    )
    free_units: int
    lead_time_min_weeks: int | None = Field(description="Set for variants made to order.")
    lead_time_max_weeks: int | None

    @classmethod
    def from_availability(cls, item: VariantAvailability) -> Self:
        lead_time = item.lead_time_weeks
        return cls(
            variant_id=item.variant_id,
            availability=item.availability,
            free_units=item.free_units,
            lead_time_min_weeks=lead_time[0] if lead_time else None,
            lead_time_max_weeks=lead_time[1] if lead_time else None,
        )


class AvailabilityOut(BaseModel):
    items: list[VariantAvailabilityOut]
