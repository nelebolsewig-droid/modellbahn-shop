"""One code per model (ADR 0027): a label names the model, the scan says how many pieces.

Putting away books ``quantity`` pieces into the chosen location (labelled ones first,
then new ones), booking out takes free ones out with a reason, and undoing either brings
the count back. Model labels are printed without making a unit.
"""

from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application import scanning
from modellbahn.modules.inventory.application.allocation import (
    AllocationService,
    PieceState,
    load_pick_list,
)
from modellbahn.modules.inventory.application.common import (
    UnitOfWorkFactory as InventoryUnitOfWorkFactory,
)
from modellbahn.modules.inventory.application.labels import (
    LabelRequest,
    LabelService,
    VariantLabels,
)
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.ports import Label, LabelSheet
from modellbahn.modules.inventory.application.scanning import UNDONE_NOTE, ScanService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.domain.errors import (
    InvalidFieldError,
    ScanIdReusedError,
    ScanNotUndoableError,
    ScanUndoForbiddenError,
)
from modellbahn.modules.inventory.domain.model import (
    LocationKind,
    MovementReason,
    ScanMode,
    ScrapReason,
    UnitStatus,
)
from modellbahn.modules.inventory.infrastructure.repositories import SqlUnitRepository
from modellbahn.modules.inventory.infrastructure.tables import stock_ledger
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.sales.application.cart import CartService
from modellbahn.modules.sales.application.checkout import CheckoutService
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.events import JsonObject
from modellbahn.platform.outbox import outbox_table
from tests.conftest import Deliver
from tests.inventory_support import COMPARTMENT, scan, staff_member, stock_up, store
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import filled_cart, place, shop_product, variant_id

pytestmark = pytest.mark.usefixtures("clean_database")

SHELF_TWO = "R01-F02"


@pytest.fixture
async def product(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
) -> ProductDetails:
    return await shop_product(catalog, media, media_storage, deliver, made_to_order=False)


@pytest.fixture
def painted(product: ProductDetails) -> UUID:
    return variant_id(product, "H0", "painted")


@pytest.fixture
def gtin(product: ProductDetails, painted: UUID) -> str:
    return next(v.gtin for s in product.product.scales for v in s.variants if v.id == painted)


@pytest.fixture
async def staff(identity: IdentityService) -> UUID:
    return await staff_member(identity)


@pytest.fixture
async def two_places(locations: LocationService) -> None:
    await store(locations)
    await locations.create(parent_code="R01", segment="F02", kind=LocationKind.COMPARTMENT, name="")


async def paid_order(carts: CartService, checkout: CheckoutService, variant: UUID, n: int) -> UUID:
    cart = await filled_cart(carts, (variant, n))
    placed = (await place(checkout, carts, cart)).details.order
    await checkout.pay(public_token=placed.public_token, method="succeeds", idempotency_key=uuid4())
    return placed.id


def effect(answer: JsonObject) -> JsonObject:
    stock_effect = answer["stock_effect"]
    assert isinstance(stock_effect, dict), answer
    return stock_effect


async def statuses(units: UnitService, variant: UUID) -> list[tuple[UnitStatus, str | None]]:
    """Every piece of the variant, oldest first: its state and location."""
    views = (await units.list_units(variant)).views
    return [(v.unit.status, v.location.code if v.location else None) for v in views]


async def ledger_of_scan(engine: AsyncEngine, scan_id: object) -> list[str]:
    async with engine.connect() as connection:
        rows = await connection.execute(
            select(stock_ledger.c.reason)
            .where(stock_ledger.c.scan_id == UUID(str(scan_id)))
            .order_by(stock_ledger.c.id)
        )
        return [str(reason) for (reason,) in rows]


async def stock_events(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        count = await connection.scalar(
            select(func.count())
            .select_from(outbox_table)
            .where(outbox_table.c.event_type == "inventory.stock.changed")
        )
        return int(count or 0)


class TestPuttingAwayWithAQuantity:
    async def test_labelled_pieces_first_oldest_first_then_new_ones(
        self,
        units: UnitService,
        scans: ScanService,
        engine: AsyncEngine,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        older = await units.label_units(
            variant_id=painted, quantity=2, location_code=None, staff_id=None
        )
        await units.label_units(
            variant_id=painted, quantity=2, location_code=SHELF_TWO, staff_id=None
        )
        events = await stock_events(engine)

        answer = await scan(
            scans,
            staff,
            gtin,
            ScanMode.PUT_AWAY,
            context={"location_code": COMPARTMENT},
            quantity=7,
        )

        assert (answer["outcome"], answer["message"], answer["quantity"]) == (
            "applied",
            "booked_in",
            7,
        )
        assert effect(answer) == {
            "quantity": 7,
            "location": COMPARTMENT,
            "in_location": 7,
            "stored": 2,
            "created": 5,
            "reserved": 0,
            "reserved_for": [],
            "reason": None,
            "from_locations": [],
        }
        assert answer["variant"]["free_units"] == 9  # type: ignore[index,call-overload]
        assert answer["location"]["unit_count"] == 7  # type: ignore[index,call-overload]
        for view in older:
            assert (await units.details(view.unit.code)).view.unit.status is UnitStatus.IN_STOCK
        assert sorted(await statuses(units, painted), key=str) == sorted(
            [(UnitStatus.IN_STOCK, COMPARTMENT)] * 7 + [(UnitStatus.IN_STOCK, SHELF_TWO)] * 2,
            key=str,
        )
        # One scan holds all its movements; one live event per movement.
        reasons = await ledger_of_scan(engine, answer["scan_id"])
        assert sorted(reasons) == sorted(["put_away"] * 7 + ["label"] * 5)
        assert await stock_events(engine) == events + 12

    async def test_new_pieces_go_to_the_orders_waiting_for_them(
        self,
        units: UnitService,
        scans: ScanService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        await catalog.change_variant(painted, expected_version=None, allow_backorder=True)
        waiting = await paid_order(carts, checkout, painted, 2)
        await deliver()
        number = (await allocation.pick_list(waiting)).order.number

        answer = await scan(
            scans,
            staff,
            gtin,
            ScanMode.PUT_AWAY,
            context={"location_code": COMPARTMENT},
            quantity=3,
        )

        assert (effect(answer)["reserved"], effect(answer)["reserved_for"]) == (2, [number])
        assert effect(answer)["in_location"] == 3
        assert answer["variant"]["free_units"] == 1  # type: ignore[index,call-overload]
        assert {i.state for i in (await allocation.pick_list(waiting)).items} == {
            PieceState.RESERVED
        }

    async def test_an_old_unit_code_of_a_piece_in_stock_counts_one_more(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        two_places: None,
        painted: UUID,
        staff: UUID,
    ) -> None:
        (code,) = await stock_up(locations, units, painted)
        answer = await scan(
            scans,
            staff,
            code,
            ScanMode.PUT_AWAY,
            context={"location_code": COMPARTMENT},
            quantity=2,
        )
        assert (effect(answer)["created"], effect(answer)["in_location"]) == (2, 3)
        # It is no move: the piece of that code stays where it lay.
        elsewhere = await scan(
            scans, staff, code, ScanMode.PUT_AWAY, context={"location_code": SHELF_TWO}
        )
        assert effect(elsewhere)["in_location"] == 1
        lying = (await units.details(code)).view.location
        assert lying is not None
        assert lying.code == COMPARTMENT

    async def test_a_repeated_scan_must_bring_the_same_quantity(
        self,
        units: UnitService,
        scans: ScanService,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        scan_id = uuid4()
        context = {"location_code": COMPARTMENT}
        first = await scan(
            scans, staff, gtin, ScanMode.PUT_AWAY, context=context, quantity=4, scan_id=scan_id
        )
        again = await scan(
            scans, staff, gtin, ScanMode.PUT_AWAY, context=context, quantity=4, scan_id=scan_id
        )
        assert again == first
        assert len(await statuses(units, painted)) == 4
        with pytest.raises(ScanIdReusedError):
            await scan(
                scans, staff, gtin, ScanMode.PUT_AWAY, context=context, quantity=5, scan_id=scan_id
            )

    async def test_without_the_right_to_add_pieces_only_labelled_ones_go_in(
        self,
        units: UnitService,
        scans: ScanService,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        (older,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        context = {"location_code": COMPARTMENT}
        # A packer's scan: three would need two new pieces, so none goes in.
        refused = await scan(
            scans, staff, gtin, ScanMode.PUT_AWAY, context=context, quantity=3, may_add_units=False
        )
        assert (refused["outcome"], refused["message"]) == ("rejected", "book_in_not_allowed")
        assert refused["undoable"] is False
        assert await statuses(units, painted) == [(UnitStatus.LABELED, None)]
        stored = await scan(
            scans, staff, gtin, ScanMode.PUT_AWAY, context=context, may_add_units=False
        )
        assert (stored["message"], effect(stored)["stored"]) == ("booked_in", 1)
        assert (await units.details(older.unit.code)).view.unit.status is UnitStatus.IN_STOCK

    async def test_a_labelled_piece_taken_meanwhile_is_replaced_by_the_next_one(
        self,
        units: UnitService,
        scans: ScanService,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        gone, first, second = await units.label_units(
            variant_id=painted, quantity=3, location_code=None, staff_id=None
        )
        await units.scrap(gone.unit.code, note="", staff_id=None, reason=ScrapReason.MISTAKE)
        stale_first_look(monkeypatch, [gone.unit.id, first.unit.id])

        answer = await scan(
            scans,
            staff,
            gtin,
            ScanMode.PUT_AWAY,
            context={"location_code": COMPARTMENT},
            quantity=2,
        )

        # Not a new piece while a labelled one is left: both labelled ones went in.
        assert (effect(answer)["stored"], effect(answer)["created"]) == (2, 0)
        for view in (first, second):
            assert (await units.details(view.unit.code)).view.unit.status is UnitStatus.IN_STOCK

    @pytest.mark.parametrize("quantity", [0, 201])
    async def test_the_quantity_has_bounds(
        self, scans: ScanService, two_places: None, gtin: str, staff: UUID, quantity: int
    ) -> None:
        with pytest.raises(InvalidFieldError, match="quantity"):
            await scan(
                scans,
                staff,
                gtin,
                ScanMode.PUT_AWAY,
                context={"location_code": COMPARTMENT},
                quantity=quantity,
            )


def stale_first_look(monkeypatch: pytest.MonkeyPatch, ids: list[UUID]) -> None:
    """The first search for units finds ``ids``, as it would have a moment earlier."""
    real = SqlUnitRepository.oldest
    calls = 0

    async def oldest(self: SqlUnitRepository, *args: object, **kwargs: object) -> list[UUID]:
        nonlocal calls
        calls += 1
        return list(ids) if calls == 1 else await real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(SqlUnitRepository, "oldest", oldest)


class TestUndoingAPutAway:
    async def test_the_count_comes_back(
        self,
        units: UnitService,
        scans: ScanService,
        engine: AsyncEngine,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        (older,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=None, staff_id=None
        )
        await units.label_units(
            variant_id=painted, quantity=1, location_code=SHELF_TWO, staff_id=None
        )
        answer = await scan(
            scans,
            staff,
            gtin,
            ScanMode.PUT_AWAY,
            context={"location_code": COMPARTMENT},
            quantity=3,
        )

        undone = await scans.undo(UUID(str(answer["scan_id"])), staff_id=staff)

        assert undone["undone"] is True
        # The labelled piece waits again; the two the scan made never existed.
        assert (await units.details(older.unit.code)).view.unit.status is UnitStatus.LABELED
        lines = {line.variant_id: line for line in await units.stock()}
        assert (lines[painted].labeled, lines[painted].in_stock) == (1, 1)
        made = (await units.list_units(painted, statuses={UnitStatus.SCRAPPED})).views
        assert [(v.unit.scrap_reason, v.unit.scrap_note) for v in made] == [
            (ScrapReason.MISTAKE, UNDONE_NOTE)
        ] * 2
        history = [e.entry.reason for e in (await units.details(made[0].unit.code)).history]
        assert history == [
            MovementReason.LABEL,
            MovementReason.PUT_AWAY,
            MovementReason.UNDO,
            MovementReason.SCRAP,
        ]
        assert len(await ledger_of_scan(engine, answer["scan_id"])) == 5

    async def test_a_waiting_order_waits_again(
        self,
        units: UnitService,
        scans: ScanService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        await catalog.change_variant(painted, expected_version=None, allow_backorder=True)
        waiting = await paid_order(carts, checkout, painted, 1)
        await deliver()
        answer = await scan(
            scans,
            staff,
            gtin,
            ScanMode.PUT_AWAY,
            context={"location_code": COMPARTMENT},
            quantity=2,
        )
        assert effect(answer)["reserved"] == 1

        await scans.undo(UUID(str(answer["scan_id"])), staff_id=staff)

        assert [i.state for i in (await allocation.pick_list(waiting)).items] == [
            PieceState.BACKORDERED
        ]
        assert {status for status, _ in await statuses(units, painted)} == {UnitStatus.SCRAPPED}

    async def test_not_once_a_piece_it_made_was_picked(
        self,
        units: UnitService,
        scans: ScanService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        await catalog.change_variant(painted, expected_version=None, allow_backorder=True)
        waiting = await paid_order(carts, checkout, painted, 1)
        await deliver()
        answer = await scan(
            scans,
            staff,
            gtin,
            ScanMode.PUT_AWAY,
            context={"location_code": COMPARTMENT},
            quantity=2,
        )
        picked = await scan(scans, staff, gtin, ScanMode.PICK, context={"order_id": str(waiting)})
        assert picked["message"] == "picked"

        with pytest.raises(ScanNotUndoableError, match="changed_since"):
            await scans.undo(UUID(str(answer["scan_id"])), staff_id=staff)
        # Nothing was booked back: both pieces are still there.
        assert sorted(status for status, _ in await statuses(units, painted)) == sorted(
            [UnitStatus.PICKED, UnitStatus.IN_STOCK]
        )


class TestBookingOut:
    async def test_from_the_chosen_place_with_a_reason(
        self,
        units: UnitService,
        scans: ScanService,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        await units.label_units(
            variant_id=painted, quantity=3, location_code=COMPARTMENT, staff_id=None
        )
        await units.label_units(
            variant_id=painted, quantity=2, location_code=SHELF_TWO, staff_id=None
        )
        chosen = await scan(scans, staff, SHELF_TWO, ScanMode.SCRAP)
        assert chosen["outcome"] == "selected"

        answer = await scan(
            scans,
            staff,
            gtin,
            ScanMode.SCRAP,
            context={"location_code": SHELF_TWO, "reason": "damaged"},
            quantity=2,
        )

        assert (answer["outcome"], answer["message"]) == ("applied", "booked_out")
        assert effect(answer) == {
            "quantity": 2,
            "location": SHELF_TWO,
            "in_location": 0,
            "stored": 0,
            "created": 0,
            "reserved": 0,
            "reserved_for": [],
            "reason": "damaged",
            "from_locations": [{"code": SHELF_TWO, "quantity": 2}],
        }
        assert answer["variant"]["free_units"] == 3  # type: ignore[index,call-overload]
        out = (await units.list_units(painted, statuses={UnitStatus.SCRAPPED})).views
        assert [v.unit.scrap_reason for v in out] == [ScrapReason.DAMAGED] * 2

    async def test_sold_by_default_and_the_oldest_anywhere(
        self,
        units: UnitService,
        scans: ScanService,
        clock: FixedClock,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        oldest = await units.label_units(
            variant_id=painted, quantity=1, location_code=SHELF_TWO, staff_id=None
        )
        clock.advance(timedelta(minutes=1))
        await units.label_units(
            variant_id=painted, quantity=2, location_code=COMPARTMENT, staff_id=None
        )

        answer = await scan(scans, staff, gtin, ScanMode.SCRAP, quantity=2)

        assert effect(answer)["reason"] == "sold"
        assert effect(answer)["location"] is None
        assert effect(answer)["in_location"] is None
        assert effect(answer)["from_locations"] == [
            {"code": COMPARTMENT, "quantity": 1},
            {"code": SHELF_TWO, "quantity": 1},
        ]
        assert (await units.details(oldest[0].unit.code)).view.unit.scrap_reason is (
            ScrapReason.SOLD
        )

    async def test_reserved_pieces_are_not_free_and_fewer_refuse_it_all(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        carts: CartService,
        checkout: CheckoutService,
        deliver: Deliver,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        await stock_up(locations, units, painted, quantity=3)
        await paid_order(carts, checkout, painted, 1)
        await deliver()

        here = await scan(
            scans, staff, gtin, ScanMode.SCRAP, context={"location_code": COMPARTMENT}, quantity=3
        )
        anywhere = await scan(scans, staff, gtin, ScanMode.SCRAP, quantity=3)

        assert (here["outcome"], here["message"]) == ("rejected", "not_enough_free")
        assert (here["variant"]["free_units"], here["variant"]["free_here"]) == (2, 2)  # type: ignore[index,call-overload]
        assert anywhere["message"] == "not_enough_free"
        assert anywhere["variant"]["free_here"] is None  # type: ignore[index,call-overload]
        assert here["undoable"] is False
        empty = await scan(scans, staff, gtin, ScanMode.SCRAP, context={"location_code": SHELF_TWO})
        assert (empty["message"], empty["variant"]["free_here"]) == ("not_enough_free", 0)  # type: ignore[index,call-overload]
        assert sorted(status for status, _ in await statuses(units, painted)) == sorted(
            [UnitStatus.IN_STOCK, UnitStatus.IN_STOCK, UnitStatus.ALLOCATED]
        )

    async def test_a_piece_taken_meanwhile_is_replaced_by_the_next_free_one(
        self,
        units: UnitService,
        scans: ScanService,
        clock: FixedClock,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        (sold,) = await units.label_units(
            variant_id=painted, quantity=1, location_code=COMPARTMENT, staff_id=None
        )
        clock.advance(timedelta(minutes=1))
        older, _newer = await units.label_units(
            variant_id=painted, quantity=2, location_code=COMPARTMENT, staff_id=None
        )
        await units.scrap(sold.unit.code, note="", staff_id=None, reason=ScrapReason.SOLD)
        stale_first_look(monkeypatch, [sold.unit.id, older.unit.id])

        answer = await scan(scans, staff, gtin, ScanMode.SCRAP, quantity=2)

        assert (answer["message"], effect(answer)["quantity"]) == ("booked_out", 2)
        assert await statuses(units, painted) == [(UnitStatus.SCRAPPED, None)] * 3

    async def test_undo_brings_them_back_where_they_lay(
        self,
        units: UnitService,
        scans: ScanService,
        catalog: CatalogService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        await units.label_units(
            variant_id=painted, quantity=2, location_code=SHELF_TWO, staff_id=None
        )
        answer = await scan(scans, staff, gtin, ScanMode.SCRAP, quantity=2)
        # Sold out in the shop meanwhile, an order waits for the workshop.
        await catalog.change_variant(painted, expected_version=None, allow_backorder=True)
        waiting = await paid_order(carts, checkout, painted, 1)
        await deliver()

        # Undoing it books pieces in again: owner and staff only, like booking out.
        with pytest.raises(ScanUndoForbiddenError):
            await scans.undo(UUID(str(answer["scan_id"])), staff_id=staff)
        await scans.undo(UUID(str(answer["scan_id"])), staff_id=staff, may_book_out=True)

        assert sorted(await statuses(units, painted), key=str) == sorted(
            [(UnitStatus.IN_STOCK, SHELF_TWO), (UnitStatus.ALLOCATED, SHELF_TWO)], key=str
        )
        assert [i.state for i in (await allocation.pick_list(waiting)).items] == [
            PieceState.RESERVED
        ]
        for view in (await units.list_units(painted)).views:
            assert (view.unit.scrap_reason, view.unit.scrap_note) == (None, "")

    async def test_what_else_a_scan_means_here(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
    ) -> None:
        (code,) = await stock_up(locations, units, painted)
        answers = [
            await scan(scans, staff, "R01", ScanMode.SCRAP),
            await scan(scans, staff, gtin, ScanMode.SCRAP, context={"location_code": "R77"}),
            await scan(scans, staff, gtin, ScanMode.SCRAP, context={"location_code": "R01"}),
        ]
        assert [a["message"] for a in answers] == [
            "holds_no_goods",
            "location_unknown",
            "holds_no_goods",
        ]
        # An older unit code books out a piece of its model, not necessarily that one.
        out = await scan(scans, staff, code, ScanMode.SCRAP)
        assert (out["message"], effect(out)["quantity"]) == ("booked_out", 1)
        with pytest.raises(InvalidFieldError, match="reason"):
            await scan(scans, staff, gtin, ScanMode.SCRAP, context={"reason": "verschenkt"})


class TestPicking:
    async def test_a_pick_list_read_before_another_pick_takes_the_next_piece(
        self,
        locations: LocationService,
        units: UnitService,
        scans: ScanService,
        carts: CartService,
        checkout: CheckoutService,
        allocation: AllocationService,
        deliver: Deliver,
        two_places: None,
        painted: UUID,
        gtin: str,
        staff: UUID,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await stock_up(locations, units, painted, quantity=2)
        order_id = await paid_order(carts, checkout, painted, 2)
        await deliver()
        context = {"order_id": str(order_id)}
        before = await allocation.pick_list(order_id)
        first = await scan(scans, staff, gtin, ScanMode.PICK, context=context)
        assert first["message"] == "picked"

        # The second scan reads the pick list as it was before the first one booked.
        real = load_pick_list
        calls = 0

        async def stale(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            return before if calls == 1 else await real(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(scanning, "load_pick_list", stale)
        second = await scan(scans, staff, gtin, ScanMode.PICK, context=context)

        assert second["message"] == "picked"
        assert second["unit"]["code"] != first["unit"]["code"]  # type: ignore[index,call-overload]
        assert {i.state for i in (await allocation.pick_list(order_id)).items} == {
            PieceState.PICKED
        }


class TestModelLabels:
    class Capturing:
        def __init__(self) -> None:
            self.labels: list[Label] = []

        def render(
            self, labels: Sequence[Label], *, sheet: LabelSheet, skip: int, title: str = ""
        ) -> bytes:
            self.labels = list(labels)
            return b"%PDF"

    async def test_as_many_as_asked_without_a_unit_and_a_units_label_is_the_same(
        self,
        locations: LocationService,
        units: UnitService,
        inventory_uow: InventoryUnitOfWorkFactory,
        product: ProductDetails,
        painted: UUID,
        gtin: str,
    ) -> None:
        renderer = self.Capturing()
        service = LabelService(uow_factory=inventory_uow, renderer=renderer)
        printed = await service.render(
            LabelRequest(
                unit_codes=[],
                location_codes=[],
                sheet=LabelSheet.QL_62X29,
                variants=[VariantLabels(variant_id=painted, quantity=3)],
            )
        )
        assert await units.stock() == []
        assert len(renderer.labels) == 3
        label = renderer.labels[0]
        assert (label.caption, label.ean13, label.code128, label.code_text) == (
            "Modell",
            gtin,
            "",
            "",
        )
        assert label.reference.startswith("MB-")
        assert len(set(printed.names)) == 1
        assert printed.names[0] == printed.name

        (code,) = await stock_up(locations, units, painted)
        await service.render(
            LabelRequest(unit_codes=[code], location_codes=[], sheet=LabelSheet.A4_70X37)
        )
        assert renderer.labels == [label]

    async def test_refusals(self, inventory_uow: InventoryUnitOfWorkFactory, painted: UUID) -> None:
        service = LabelService(uow_factory=inventory_uow, renderer=self.Capturing())

        async def labels(*wanted: VariantLabels) -> None:
            await service.render(
                LabelRequest(
                    unit_codes=[], location_codes=[], sheet=LabelSheet.A4_70X37, variants=wanted
                )
            )

        with pytest.raises(InvalidFieldError, match=r"variants\.0\.variant_id"):
            await labels(VariantLabels(variant_id=uuid4(), quantity=1))
        with pytest.raises(InvalidFieldError, match=r"variants\.1\.quantity"):
            await labels(VariantLabels(painted, 1), VariantLabels(painted, 0))
        with pytest.raises(InvalidFieldError, match="unit_codes"):
            await labels(VariantLabels(painted, 200), VariantLabels(painted, 41))
