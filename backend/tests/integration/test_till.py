"""The till (ADR 0041) against a real PostgreSQL: SumUp sales book pieces out by themselves."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from modellbahn.modules.catalog.application.services import CatalogService, ProductDetails
from modellbahn.modules.identity.application.services import IdentityService
from modellbahn.modules.inventory.application.common import (
    UnitOfWorkFactory as InventoryUnitOfWorkFactory,
)
from modellbahn.modules.inventory.application.locations import LocationService
from modellbahn.modules.inventory.application.till import TillService
from modellbahn.modules.inventory.application.units import UnitService
from modellbahn.modules.inventory.domain.errors import (
    InvalidFieldError,
    TillLineNotFoundError,
    TillUnavailableError,
)
from modellbahn.modules.inventory.domain.model import SaleChannel, ScrapReason, UnitStatus
from modellbahn.modules.inventory.domain.till import (
    TillLineState,
    TillPayment,
    TillProduct,
    TillSale,
)
from modellbahn.modules.media.application.services import MediaService
from modellbahn.modules.site.application.fairs import FairService
from modellbahn.platform.clock import FixedClock
from tests.conftest import Deliver
from tests.integration.test_site_service import fair_details
from tests.inventory_support import staff_member, stock_up
from tests.media_support import InMemoryMediaStorage
from tests.sales_support import shop_product, variant_id

pytestmark = pytest.mark.usefixtures("clean_database")


class FakeTill:
    """SumUp as the tests want it: sales listed, products per sale, or unreachable."""

    def __init__(self) -> None:
        self.sales: list[TillSale] = []
        self.down = False
        self.asked_for: list[str] = []

    def ring_up(self, code: str, at: datetime, *products: TillProduct, cash: bool = False) -> None:
        self.sales.append(
            TillSale(
                transaction_code=code,
                sold_at=at,
                payment=TillPayment.CASH if cash else TillPayment.CARD,
                total_cents=sum(p.unit_price_cents * p.quantity for p in products),
                products=products,
            )
        )

    async def sales_since(self, since: datetime) -> list[TillSale]:
        if self.down:
            raise TillUnavailableError("SumUp ist nicht erreichbar.")
        return [
            TillSale(s.transaction_code, s.sold_at, s.payment, s.total_cents, ())
            for s in self.sales
            if s.sold_at >= since
        ]

    async def products(self, sale: TillSale) -> tuple[TillProduct, ...]:
        self.asked_for.append(sale.transaction_code)
        return next(s.products for s in self.sales if s.transaction_code == sale.transaction_code)

    async def aclose(self) -> None:
        return


def item(name: str, cents: int, quantity: int = 1) -> TillProduct:
    return TillProduct(name=name, quantity=quantity, unit_price_cents=cents)


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
def sumup() -> FakeTill:
    return FakeTill()


@pytest.fixture
def till(
    inventory_uow: InventoryUnitOfWorkFactory, clock: FixedClock, sumup: FakeTill
) -> TillService:
    return TillService(uow_factory=inventory_uow, clock=clock, gateway=sumup)


@pytest.fixture
async def started(till: TillService, clock: FixedClock) -> datetime:
    """The first run only notes when fetching starts."""
    assert await till.sync() == 0
    start = clock.now()
    clock.advance(timedelta(minutes=5))
    return start


async def unit_states(units: UnitService, codes: list[str]) -> list[UnitStatus]:
    return [(await units.details(code)).view.unit.status for code in codes]


class TestFetching:
    async def test_sales_before_the_start_are_left_alone(
        self, till: TillService, sumup: FakeTill, clock: FixedClock
    ) -> None:
        sumup.ring_up("OLD", clock.now() - timedelta(hours=1), item("EDK 6", 25000))
        assert await till.sync() == 0
        clock.advance(timedelta(minutes=1))
        assert await till.sync() == 0
        overview = await till.overview()
        assert overview.open == []
        assert overview.state is not None
        assert sumup.asked_for == []

    async def test_an_assigned_name_books_the_oldest_free_piece_as_sold(
        self,
        till: TillService,
        sumup: FakeTill,
        clock: FixedClock,
        started: datetime,
        locations: LocationService,
        units: UnitService,
        painted: UUID,
        identity: IdentityService,
    ) -> None:
        codes = await stock_up(locations, units, painted, quantity=2)
        staff = await staff_member(identity)
        await till.assign(
            "EDK 6 Knickausleger TT", variant_id=painted, ignored=False, staff_id=staff
        )

        sumup.ring_up("TAAA1", clock.now(), item("edk 6  Knickausleger tt", 24000), cash=True)
        assert await till.sync() == 1

        assert await unit_states(units, codes) == [UnitStatus.SCRAPPED, UnitStatus.IN_STOCK]
        sold = (await units.details(codes[0])).view.unit
        assert sold.scrap_reason is ScrapReason.SOLD
        assert (sold.sale_channel, sold.sale_price_cents) == (SaleChannel.STORE, 24000)
        assert sold.scrap_note == "SumUp-Kasse, Beleg TAAA1"
        overview = await till.overview()
        assert overview.open == []
        assert overview.booked_today == 1

        # Fetched again (the lookback overlaps): booked once only, not asked again.
        clock.advance(timedelta(minutes=1))
        assert await till.sync() == 0
        assert await unit_states(units, codes) == [UnitStatus.SCRAPPED, UnitStatus.IN_STOCK]
        assert sumup.asked_for == ["TAAA1"]

    async def test_on_a_fair_day_the_channel_is_the_fair(
        self,
        till: TillService,
        sumup: FakeTill,
        clock: FixedClock,
        started: datetime,
        locations: LocationService,
        units: UnitService,
        painted: UUID,
        fairs: FairService,
    ) -> None:
        today = clock.now().astimezone(UTC).date()
        await fairs.create(
            fair_details("Leipzig", today - timedelta(days=1), days=3), published=False
        )
        (code,) = await stock_up(locations, units, painted)
        await till.assign("Stellwerk", variant_id=painted, ignored=False, staff_id=None)
        sumup.ring_up("TAAA2", clock.now(), item("Stellwerk", 9900))
        await till.sync()
        assert (await units.details(code)).view.unit.sale_channel is SaleChannel.FAIR

    async def test_an_unknown_name_waits_and_is_booked_when_assigned(
        self,
        till: TillService,
        sumup: FakeTill,
        clock: FixedClock,
        started: datetime,
        locations: LocationService,
        units: UnitService,
        painted: UUID,
    ) -> None:
        codes = await stock_up(locations, units, painted, quantity=3)
        sumup.ring_up("TAAA3", clock.now(), item("K700 tt", 3000, quantity=2))
        await till.sync()

        (waiting,) = (await till.overview()).open
        assert (waiting.line.name, waiting.line.state) == ("K700 tt", TillLineState.UNASSIGNED)
        assert await unit_states(units, codes) == [UnitStatus.IN_STOCK] * 3

        overview = await till.assign("K700 TT", variant_id=painted, ignored=False, staff_id=None)
        assert overview.open == []
        assert [view.item.name for view in overview.items] == ["K700 TT"]
        assert await unit_states(units, codes) == [
            UnitStatus.SCRAPPED,
            UnitStatus.SCRAPPED,
            UnitStatus.IN_STOCK,
        ]
        assert (await units.details(codes[0])).view.unit.sale_price_cents == 3000

    async def test_too_few_pieces_wait_for_the_rest(
        self,
        till: TillService,
        sumup: FakeTill,
        clock: FixedClock,
        started: datetime,
        locations: LocationService,
        units: UnitService,
        painted: UUID,
    ) -> None:
        (first,) = await stock_up(locations, units, painted)
        await till.assign("Stellwerk", variant_id=painted, ignored=False, staff_id=None)
        sumup.ring_up("TAAA4", clock.now(), item("Stellwerk", 9900, quantity=2))
        await till.sync()
        (short,) = (await till.overview()).open
        assert (short.line.state, short.line.booked) == (TillLineState.SHORT, 1)

        # The second piece comes onto the shelf: the next run books it.
        (second,) = await stock_up(locations, units, painted)
        clock.advance(timedelta(minutes=1))
        await till.sync()
        assert (await till.overview()).open == []
        assert await unit_states(units, [first, second]) == [UnitStatus.SCRAPPED] * 2

    async def test_custom_amounts_and_ignored_names(
        self,
        till: TillService,
        sumup: FakeTill,
        clock: FixedClock,
        started: datetime,
    ) -> None:
        await till.assign("Briefversand", variant_id=None, ignored=True, staff_id=None)
        sumup.ring_up(
            "TAAA5",
            clock.now(),
            item("Individueller Betrag", 4500),
            item("Briefversand", 100),
        )
        await till.sync()
        (custom,) = (await till.overview()).open
        assert custom.line.state is TillLineState.CUSTOM

        # Booked out by hand in the Stellwerk, then marked done.
        assert (await till.settle(custom.line.id)).open == []
        with pytest.raises(TillLineNotFoundError):
            await till.settle(UUID(int=1))
        with pytest.raises(InvalidFieldError):
            await till.assign("Individueller Betrag", variant_id=None, ignored=True, staff_id=None)

    async def test_an_unreachable_till_is_remembered_and_cleared(
        self, till: TillService, sumup: FakeTill, clock: FixedClock, started: datetime
    ) -> None:
        sumup.down = True
        with pytest.raises(TillUnavailableError):
            await till.sync()
        state = (await till.overview()).state
        assert state is not None
        assert state.last_error == "SumUp ist nicht erreichbar."

        sumup.down = False
        clock.advance(timedelta(minutes=1))
        await till.sync()
        state = (await till.overview()).state
        assert state is not None
        assert (state.last_error, state.last_sync_at) == ("", clock.now())
