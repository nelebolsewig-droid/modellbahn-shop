"""Catalogue use cases against the database: categories, products, galleries, the shop."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from modellbahn.modules.catalog.application.ports import ProductOrder
from modellbahn.modules.catalog.application.services import (
    CatalogService,
    ProductDetails,
    QuickEntry,
)
from modellbahn.modules.catalog.domain.errors import (
    CategoryCycleError,
    CategoryNotFoundError,
    InvalidFieldError,
    ProductNotDeletableError,
    ProductNotFoundError,
    ProductNotPublishableError,
    PublishBlocker,
    ScaleAlreadyAddedError,
    SlugLockedError,
    SlugTakenError,
    UnknownReferenceError,
    VariantAlreadyExistsError,
    VersionMismatchError,
)
from modellbahn.modules.catalog.domain.model import (
    Dimensions,
    GalleryEntry,
    MediaRole,
    ProductStatus,
    ean13_check_digit,
)
from modellbahn.modules.media.application.services import MediaService
from modellbahn.platform.clock import FixedClock
from modellbahn.platform.outbox import outbox_table
from tests.conftest import Deliver
from tests.media_support import InMemoryMediaStorage, photo, ready_image, uploaded_image


async def draft(catalog: CatalogService, name: str = "Stellwerk Altenau") -> ProductDetails:
    return await catalog.create_product(name=name)


async def with_variant(catalog: CatalogService, details: ProductDetails) -> ProductDetails:
    product = details.product
    details = await catalog.add_scale(
        product.id, expected_version=None, scale_code="H0", dimensions=Dimensions()
    )
    scale = details.product.scales[0]
    return await catalog.add_variant(
        scale.id, expected_version=None, finish_code="painted", price_cents=4990
    )


async def sellable(
    catalog: CatalogService,
    media: MediaService,
    media_storage: InMemoryMediaStorage,
    deliver: Deliver,
    name: str = "Stellwerk Altenau",
    category_id: UUID | None = None,
) -> ProductDetails:
    """A draft that may be published: category, active variant, ready main image."""
    details = await with_variant(catalog, await draft(catalog, name))
    if category_id is None:
        category_id = (await catalog.create_category(name=f"Kategorie {uuid4().hex[:6]}")).id
    details = await catalog.change_product(
        details.product.id, expected_version=None, primary_category_id=category_id
    )
    image = await ready_image(media, media_storage, deliver, photo(500, 400, colour=_colour()))
    return await catalog.attach_image(details.product.id, asset_id=image.id)


_colours = iter(range(1, 250))


def _colour() -> tuple[int, int, int]:
    # Every sample photo differs, so each upload is a new asset.
    value = next(_colours)
    return (value, 255 - value, (value * 7) % 255)


class TestCategories:
    async def test_tree_with_generated_slugs(self, catalog: CatalogService) -> None:
        buildings = await catalog.create_category(name="Gebäude")
        signal_boxes = await catalog.create_category(name="Stellwerke", parent_id=buildings.id)
        sheds = await catalog.create_category(name="Lokschuppen", parent_id=buildings.id)
        assert (buildings.slug, signal_boxes.slug) == ("gebaeude", "stellwerke")
        assert (signal_boxes.position, sheds.position) == (0, 1)
        with pytest.raises(SlugTakenError):
            await catalog.create_category(name="Gebäude")
        with pytest.raises(UnknownReferenceError):
            await catalog.create_category(name="Waise", parent_id=uuid4())

    async def test_moves_without_cycles(self, catalog: CatalogService) -> None:
        top = await catalog.create_category(name="Gebäude")
        child = await catalog.create_category(name="Stellwerke", parent_id=top.id)
        grandchild = await catalog.create_category(name="Reichsbahn", parent_id=child.id)
        with pytest.raises(CategoryCycleError):
            await catalog.change_category(top.id, parent_id=grandchild.id)
        with pytest.raises(CategoryCycleError):
            await catalog.change_category(top.id, parent_id=top.id)
        moved = await catalog.change_category(grandchild.id, parent_id=None, name="DR-Bauten")
        assert (moved.parent_id, moved.name, moved.slug) == (None, "DR-Bauten", "reichsbahn")
        with pytest.raises(SlugTakenError):
            await catalog.change_category(moved.id, slug="stellwerke")
        with pytest.raises(CategoryNotFoundError):
            await catalog.change_category(uuid4(), name="x")


class TestProducts:
    async def test_numbers_and_slugs(self, catalog: CatalogService) -> None:
        first = (await draft(catalog)).product
        second = (await draft(catalog)).product
        assert second.number == first.number + 1
        assert first.slug == "stellwerk-altenau"
        assert second.slug == f"stellwerk-altenau-{second.number}"
        assert first.status is ProductStatus.DRAFT
        with pytest.raises(SlugTakenError):
            await catalog.create_product(name="Anders", slug="stellwerk-altenau")

    async def test_variants_get_sku_and_internal_ean(self, catalog: CatalogService) -> None:
        details = await with_variant(catalog, await draft(catalog))
        product = details.product
        (variant,) = product.variants
        assert variant.sku == f"MB-{product.number:06d}-H0-F"
        assert variant.gtin.startswith("20")
        assert int(variant.gtin[-1]) == ean13_check_digit(variant.gtin[:12])
        scale = product.scales[0]
        with pytest.raises(VariantAlreadyExistsError):
            await catalog.add_variant(
                scale.id, expected_version=None, finish_code="painted", price_cents=1
            )
        with pytest.raises(ScaleAlreadyAddedError):
            await catalog.add_scale(
                product.id, expected_version=None, scale_code="H0", dimensions=Dimensions()
            )
        with pytest.raises(UnknownReferenceError):
            await catalog.add_scale(
                product.id, expected_version=None, scale_code="QQ", dimensions=Dimensions()
            )
        other = await catalog.add_variant(
            scale.id, expected_version=None, finish_code="unpainted", price_cents=2990
        )
        assert {v.sku[-1] for v in other.product.variants} == {"B", "F"}
        assert len({v.gtin for v in other.product.variants}) == 2

    async def test_every_change_raises_the_version(self, catalog: CatalogService) -> None:
        details = await draft(catalog)
        version = details.product.version
        details = await catalog.add_scale(
            details.product.id,
            expected_version=version,
            scale_code="TT",
            dimensions=Dimensions(length_mm=Decimal("74.5"), weight_g=40),
        )
        assert details.product.version == version + 1
        scale = details.product.scales[0]
        details = await catalog.change_scale(
            scale.id,
            expected_version=details.product.version,
            dimensions=Dimensions(height_mm=Decimal("51.0")),
        )
        assert details.product.version == version + 2
        loaded = await catalog.get_product(details.product.id)
        assert loaded.product.scales[0].height_mm == Decimal("51.0")
        assert loaded.product.scales[0].length_mm is None

    async def test_an_outdated_version_is_refused(self, catalog: CatalogService) -> None:
        details = await draft(catalog)
        version = details.product.version
        await catalog.change_product(details.product.id, expected_version=version, summary="A")
        with pytest.raises(VersionMismatchError):
            await catalog.change_product(details.product.id, expected_version=version, summary="B")
        assert (await catalog.get_product(details.product.id)).product.summary == "A"

    async def test_concurrent_changes_are_serialised(self, catalog: CatalogService) -> None:
        details = await draft(catalog)
        version = details.product.version
        results = await asyncio.gather(
            catalog.change_product(details.product.id, expected_version=version, summary="A"),
            catalog.change_product(details.product.id, expected_version=version, summary="B"),
            return_exceptions=True,
        )
        assert sum(isinstance(r, VersionMismatchError) for r in results) == 1

    async def test_texts_category_and_epochs(self, catalog: CatalogService) -> None:
        category = await catalog.create_category(name="Gebäude")
        details = await draft(catalog)
        details = await catalog.change_product(
            details.product.id,
            expected_version=details.product.version,
            name="  Stellwerk   Altenau ",
            summary="Hebelstellwerk der Bauart Jüdel",
            description="Zeile eins\n\n\nZeile zwei",
            prototype="Altenau (Harz)",
            primary_category_id=category.id,
            epoch_codes=["III", "II"],
        )
        product = details.product
        assert product.name == "Stellwerk Altenau"
        assert product.description == "Zeile eins\n\nZeile zwei"
        assert sorted(product.epoch_codes) == ["II", "III"]
        with pytest.raises(UnknownReferenceError):
            await catalog.change_product(product.id, expected_version=None, epoch_codes=["VII"])
        with pytest.raises(UnknownReferenceError):
            await catalog.change_product(
                product.id, expected_version=None, primary_category_id=uuid4()
            )
        other = await draft(catalog, "Lokschuppen")
        with pytest.raises(SlugTakenError):
            await catalog.change_product(
                other.product.id, expected_version=None, slug="stellwerk-altenau"
            )

    async def test_delete_only_drafts(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        details = await with_variant(catalog, await draft(catalog))
        await catalog.delete_product(details.product.id, expected_version=None)
        with pytest.raises(ProductNotFoundError):
            await catalog.get_product(details.product.id)
        published = await sellable(catalog, media, media_storage, deliver)
        await catalog.publish(published.product.id, expected_version=None)
        with pytest.raises(ProductNotDeletableError):
            await catalog.delete_product(published.product.id, expected_version=None)


class TestGallery:
    async def test_attach_needs_a_completed_upload(
        self, catalog: CatalogService, media: MediaService, media_storage: InMemoryMediaStorage
    ) -> None:
        details = await draft(catalog)
        ticket = await media.request_upload(
            filename="a.jpg",
            mime_type="image/jpeg",
            size_bytes=10,
            sha256="0" * 64,
            uploaded_by=None,
        )
        with pytest.raises(InvalidFieldError) as caught:
            await catalog.attach_image(details.product.id, asset_id=ticket.asset.id)
        assert caught.value.code == "not_uploaded"
        with pytest.raises(UnknownReferenceError):
            await catalog.attach_image(details.product.id, asset_id=uuid4())
        uploaded = await uploaded_image(media, media_storage)
        details = await catalog.attach_image(details.product.id, asset_id=uploaded.id)
        (entry,) = details.product.gallery
        assert entry.asset_id == uploaded.id
        assert details.images[uploaded.id].status.value == "uploaded"
        assert details.blockers[-1] is PublishBlocker.MAIN_IMAGE_NOT_READY

    async def test_parallel_uploads_append_in_turn(
        self, catalog: CatalogService, media: MediaService, media_storage: InMemoryMediaStorage
    ) -> None:
        details = await draft(catalog)
        assets = [
            await uploaded_image(media, media_storage, photo(300, 300, colour=_colour()))
            for _ in range(4)
        ]
        await asyncio.gather(
            *(catalog.attach_image(details.product.id, asset_id=a.id) for a in assets)
        )
        gallery = (await catalog.get_product(details.product.id)).product.gallery
        assert sorted(entry.position for entry in gallery) == [0, 1, 2, 3]
        assert {entry.asset_id for entry in gallery} == {a.id for a in assets}

    async def test_arrange_swaps_positions_in_one_step(
        self, catalog: CatalogService, media: MediaService, media_storage: InMemoryMediaStorage
    ) -> None:
        details = await with_variant(catalog, await draft(catalog))
        first = await uploaded_image(media, media_storage, photo(300, 300, colour=_colour()))
        second = await uploaded_image(media, media_storage, photo(300, 300, colour=_colour()))
        await catalog.attach_image(details.product.id, asset_id=first.id)
        details = await catalog.attach_image(details.product.id, asset_id=second.id)
        details = await catalog.arrange_gallery(
            details.product.id,
            expected_version=details.product.version,
            entries=[
                GalleryEntry(asset_id=second.id, alt_text="Rückseite", scale_code="H0"),
                GalleryEntry(asset_id=first.id, role=MediaRole.DETAIL, finish_code="painted"),
            ],
        )
        loaded = (await catalog.get_product(details.product.id)).product
        assert [(e.asset_id, e.position) for e in loaded.gallery] == [(second.id, 0), (first.id, 1)]
        assert loaded.gallery[0].scale_code == "H0"
        assert loaded.gallery[1].finish_code == "painted"
        with pytest.raises(UnknownReferenceError):
            await catalog.arrange_gallery(
                details.product.id,
                expected_version=None,
                entries=[GalleryEntry(asset_id=first.id, finish_code="vergoldet")],
            )


class TestPublishing:
    async def test_publish_needs_a_ready_main_image(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        category = await catalog.create_category(name="Gebäude")
        details = await with_variant(catalog, await draft(catalog))
        details = await catalog.change_product(
            details.product.id, expected_version=None, primary_category_id=category.id
        )
        image = await uploaded_image(media, media_storage)
        await catalog.attach_image(details.product.id, asset_id=image.id)
        with pytest.raises(ProductNotPublishableError) as caught:
            await catalog.publish(details.product.id, expected_version=None)
        assert caught.value.blockers == [PublishBlocker.MAIN_IMAGE_NOT_READY]
        await deliver()
        details = await catalog.get_product(details.product.id)
        assert details.blockers == []
        published = await catalog.publish(details.product.id, expected_version=None)
        assert published.product.status is ProductStatus.ACTIVE

    async def test_events_of_the_life_cycle(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
        engine: AsyncEngine,
        clock: FixedClock,
    ) -> None:
        details = await sellable(catalog, media, media_storage, deliver)
        product_id = details.product.id
        await catalog.change_product(product_id, expected_version=None, summary="Entwurf")
        await catalog.publish(product_id, expected_version=None)
        await catalog.change_product(product_id, expected_version=None, summary="Neu")
        clock.advance(timedelta(days=1))
        await catalog.archive(product_id, expected_version=None)
        async with engine.connect() as connection:
            rows = await connection.execute(
                select(outbox_table.c.event_type)
                .where(outbox_table.c.aggregate_id == product_id)
                .order_by(outbox_table.c.id)
            )
            types = list(rows.scalars())
        # Changes to a draft announce nothing; changes in the shop do.
        assert types == [
            "catalog.product.published",
            "catalog.product.updated",
            "catalog.product.archived",
        ]

    async def test_a_published_product_keeps_its_slug_and_rules(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        details = await sellable(catalog, media, media_storage, deliver)
        details = await catalog.publish(details.product.id, expected_version=None)
        with pytest.raises(SlugLockedError):
            await catalog.change_product(details.product.id, expected_version=None, slug="neu")
        (variant,) = details.product.variants
        with pytest.raises(ProductNotPublishableError):
            await catalog.change_variant(variant.id, expected_version=None, active=False)
        with pytest.raises(ProductNotPublishableError):
            await catalog.remove_variant(variant.id, expected_version=None)


class TestShop:
    async def test_lists_only_published_products_newest_first(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
        clock: FixedClock,
    ) -> None:
        names = ["Stellwerk Altenau", "Lokschuppen Hörsel", "Wasserturm Bebra"]
        for name in names:
            details = await sellable(catalog, media, media_storage, deliver, name)
            await catalog.publish(details.product.id, expected_version=None)
            clock.advance(timedelta(minutes=1))
        await draft(catalog, "Noch nicht fertig")
        first = await catalog.store_products(limit=2)
        assert [c.product.name for c in first.items] == names[::-1][:2]
        assert first.next_cursor is not None
        assert all(c.main_image is not None and c.main_image.is_ready for c in first.items)
        second = await catalog.store_products(limit=2, cursor=first.next_cursor)
        assert [c.product.name for c in second.items] == [names[0]]
        assert second.next_cursor is None

    async def test_filters_by_scale_category_and_text(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        buildings = await catalog.create_category(name="Gebäude")
        signal_boxes = await catalog.create_category(name="Stellwerke", parent_id=buildings.id)
        accessories = await catalog.create_category(name="Zubehör")
        box = await sellable(
            catalog, media, media_storage, deliver, "Stellwerk Altenau", signal_boxes.id
        )
        await catalog.change_product(
            box.product.id, expected_version=None, summary="Hebelstellwerk mit Treppenhaus"
        )
        await catalog.publish(box.product.id, expected_version=None)
        lamps = await sellable(
            catalog, media, media_storage, deliver, "Bahnsteiglampen", accessories.id
        )
        lamp_scale = lamps.product.scales[0]
        await catalog.remove_scale(lamp_scale.id, expected_version=None)
        lamps = await catalog.add_scale(
            lamps.product.id, expected_version=None, scale_code="N", dimensions=Dimensions()
        )
        await catalog.add_variant(
            lamps.product.scales[0].id,
            expected_version=None,
            finish_code="painted",
            price_cents=990,
        )
        await catalog.publish(lamps.product.id, expected_version=None)

        async def names(**filters: str) -> list[str]:
            page = await catalog.store_products(**filters)  # type: ignore[arg-type]
            return [c.product.name for c in page.items]

        assert await names(category_slug="gebaeude") == ["Stellwerk Altenau"]
        assert await names(category_slug="zubehoer") == ["Bahnsteiglampen"]
        assert await names(scale_code="N") == ["Bahnsteiglampen"]
        assert await names(scale_code="H0") == ["Stellwerk Altenau"]
        assert await names(scale_code="TT") == []
        # German stemming: "Stellwerke" finds "Stellwerk", "Treppenhäuser" the summary.
        assert await names(text="Stellwerke") == ["Stellwerk Altenau"]
        assert await names(text="Treppenhaus") == ["Stellwerk Altenau"]
        assert await names(text="Bahnsteiglampe") == ["Bahnsteiglampen"]
        # Compounds are not split: "Lampe" alone does not find them.
        assert await names(text="Lampe") == []
        with pytest.raises(CategoryNotFoundError):
            await catalog.store_products(category_slug="gibt-es-nicht")
        with pytest.raises(UnknownReferenceError):
            await catalog.store_products(scale_code="QQ")

    async def test_navigation_counts_what_the_shop_shows(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        vehicles = await catalog.create_category(name="Straßenfahrzeuge")
        trucks = await catalog.create_category(name="LKW", parent_id=vehicles.id)
        fire = await catalog.create_category(name="Feuerwehr", parent_id=trucks.id)
        # A fire engine in H0 and 1:24, a tipper in H0, and a draft that does not count.
        engine = await sellable(catalog, media, media_storage, deliver, "Löschfahrzeug", fire.id)
        engine = await catalog.add_scale(
            engine.product.id, expected_version=None, scale_code="124", dimensions=Dimensions()
        )
        big = next(s for s in engine.product.scales if s.scale_code == "124")
        await catalog.add_variant(
            big.id, expected_version=None, finish_code="painted", price_cents=12900
        )
        await catalog.publish(engine.product.id, expected_version=None)
        tipper = await sellable(catalog, media, media_storage, deliver, "Kipper", trucks.id)
        await catalog.publish(tipper.product.id, expected_version=None)
        await sellable(catalog, media, media_storage, deliver, "Entwurf", trucks.id)

        navigation = await catalog.navigation()

        assert navigation.category_counts(fire.id) == {"H0": 1, "124": 1}
        assert navigation.category_counts(trucks.id) == {"H0": 1}
        assert navigation.category_counts(vehicles.id) == {}
        assert navigation.scale_count("H0") == 2
        assert navigation.scale_count("124") == 1
        assert navigation.scale_count("N") == 0
        # Smallest models first: Z (1:220) … G (1:22,5).
        assert [s.code for s in navigation.references.scales] == [
            "Z",
            "N",
            "TT",
            "H0",
            "0",
            "125",
            "124",
            "G",
        ]

    async def test_sorted_by_price_and_name_page_by_page(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        # (name, price of the active variant, price of an inactive one)
        specs = [
            ("Wasserturm", 4990, 990),
            ("Bahnwärterhaus", 2990, None),
            ("Prellbock", 690, None),
        ]
        for name, price, inactive_price in specs:
            details = await sellable(catalog, media, media_storage, deliver, name)
            variant = details.product.scales[0].variants[0]
            await catalog.change_variant(variant.id, expected_version=None, price_cents=price)
            if inactive_price is not None:
                await catalog.add_variant(
                    details.product.scales[0].id,
                    expected_version=None,
                    finish_code="unpainted",
                    price_cents=inactive_price,
                    active=False,
                )
            await catalog.publish(details.product.id, expected_version=None)

        async def all_pages(order: ProductOrder) -> list[str]:
            names: list[str] = []
            cursor = None
            while True:
                page = await catalog.store_products(order=order, cursor=cursor, limit=1)
                names += [card.product.name for card in page.items]
                if page.next_cursor is None:
                    return names
                cursor = page.next_cursor

        # The inactive variant at 9,90 € does not make the water tower the cheapest.
        assert await all_pages(ProductOrder.PRICE_ASC) == [
            "Prellbock",
            "Bahnwärterhaus",
            "Wasserturm",
        ]
        assert await all_pages(ProductOrder.PRICE_DESC) == [
            "Wasserturm",
            "Bahnwärterhaus",
            "Prellbock",
        ]
        assert await all_pages(ProductOrder.NAME) == ["Bahnwärterhaus", "Prellbock", "Wasserturm"]
        with pytest.raises(ValueError, match="publication, price or name"):
            await catalog.store_products(order=ProductOrder.CREATED)

    async def test_filters_by_epoch(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        old = await sellable(catalog, media, media_storage, deliver, "Länderbahn-Stellwerk")
        await catalog.change_product(old.product.id, expected_version=None, epoch_codes=["I", "II"])
        await catalog.publish(old.product.id, expected_version=None)
        new = await sellable(catalog, media, media_storage, deliver, "Spurplanstellwerk")
        await catalog.change_product(new.product.id, expected_version=None, epoch_codes=["IV"])
        await catalog.publish(new.product.id, expected_version=None)
        page = await catalog.store_products(epoch_code="II")
        assert [card.product.name for card in page.items] == ["Länderbahn-Stellwerk"]
        assert (await catalog.store_products(epoch_code="VI")).items == []
        with pytest.raises(UnknownReferenceError):
            await catalog.store_products(epoch_code="IX")

    async def test_product_page(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        top = await catalog.create_category(name="Gebäude")
        child = await catalog.create_category(name="Stellwerke", parent_id=top.id)
        details = await sellable(catalog, media, media_storage, deliver, category_id=child.id)
        pending = await uploaded_image(media, media_storage, photo(300, 300, colour=_colour()))
        await catalog.attach_image(details.product.id, asset_id=pending.id)
        with pytest.raises(ProductNotFoundError):
            await catalog.store_product(details.product.slug)
        await catalog.publish(details.product.id, expected_version=None)
        page = await catalog.store_product(details.product.slug)
        assert [c.slug for c in page.category_path] == ["gebaeude", "stellwerke"]
        # Only ready images reach the shop.
        assert list(page.images) == [details.product.gallery[0].asset_id]
        assert {s.code for s in page.references.scales} == {
            "Z",
            "N",
            "TT",
            "H0",
            "0",
            "125",
            "124",
            "G",
        }


class TestQuickEntry:
    async def test_one_model_off_the_shelf_in_one_step(
        self,
        catalog: CatalogService,
        media: MediaService,
        media_storage: InMemoryMediaStorage,
        deliver: Deliver,
    ) -> None:
        cranes = await catalog.create_category(name="Kranfahrzeuge")
        yellow_photo = await ready_image(
            media, media_storage, deliver, photo(400, 300, colour=_colour())
        )
        first = await catalog.quick_entry(
            product_id=None,
            name="IFA ADK 70 Autokran",
            category_id=cranes.id,
            scale_code="H0",
            finish_code="painted",
            color="gelb",
            price_cents=8000,
            asset_id=yellow_photo.id,
        )
        product = first.details.product
        assert (first.new_product, first.new_variant) == (True, True)
        assert (product.status, product.primary_category_id) == (ProductStatus.DRAFT, cranes.id)
        assert (first.variant.color, first.variant.sku[-2:]) == ("Gelb", "-F")
        (image,) = product.gallery
        assert (image.scale_code, image.finish_code, image.color) == ("H0", "painted", "Gelb")

        # The next box on the shelf: the same model in blue, then the kit.
        blue = await catalog.quick_entry(
            product_id=product.id,
            name=None,
            category_id=None,
            scale_code="H0",
            finish_code="painted",
            color="Blau",
            price_cents=8000,
        )
        assert (blue.new_product, blue.new_variant, blue.variant.sku[-3:]) == (False, True, "-F2")
        kit = await catalog.quick_entry(
            product_id=product.id,
            name=None,
            category_id=None,
            scale_code="H0",
            finish_code="unpainted",
            color="",
            price_cents=4500,
        )
        # Once more in yellow at a new price: no new variant, the price follows.
        again = await catalog.quick_entry(
            product_id=product.id,
            name=None,
            category_id=None,
            scale_code="H0",
            finish_code="painted",
            color="GELB",
            price_cents=8500,
        )
        assert (again.new_variant, again.variant.id) == (False, first.variant.id)
        assert again.variant.price_cents == 8500
        assert [v.finish_code for v in kit.details.product.variants].count("painted") == 2

        published = await catalog.publish_ready()
        assert [p.name for p in published] == ["IFA ADK 70 Autokran"]
        unready = await catalog.quick_entry(
            product_id=None,
            name="KrAZ-250K",
            category_id=None,
            scale_code="H0",
            finish_code="painted",
            color="",
            price_cents=8000,
        )
        assert unready.details.blockers  # no category, no photo: it stays a draft
        assert await catalog.publish_ready() == []

    async def test_names_the_colour_of_the_one_finished_model_without_one(
        self, catalog: CatalogService
    ) -> None:
        async def enter(product_id: UUID | None, color: str) -> QuickEntry:
            return await catalog.quick_entry(
                product_id=product_id,
                name="IFA ADK 80 Autokran" if product_id is None else None,
                category_id=None,
                scale_code="H0",
                finish_code="painted",
                color=color,
                price_cents=8000,
            )

        # The start inventory knows the crane, but not its colour.
        plain = await enter(None, "")
        product_id = plain.details.product.id
        yellow = await enter(product_id, "gelb")
        assert (yellow.new_variant, yellow.variant.id) == (False, plain.variant.id)
        assert (yellow.variant.color, yellow.variant.sku[-2:]) == ("Gelb", "-F")
        # Now it has a named colour: the next one is a variant of its own.
        blue = await enter(product_id, "Blau")
        assert (blue.new_variant, blue.variant.sku[-3:]) == (True, "-F2")
        with pytest.raises(InvalidFieldError) as refused:
            await enter(product_id, "")
        assert (refused.value.field, refused.value.code) == ("color", "required")

    async def test_a_new_product_needs_a_name(self, catalog: CatalogService) -> None:
        with pytest.raises(InvalidFieldError):
            await catalog.quick_entry(
                product_id=None,
                name=" ",
                category_id=None,
                scale_code="H0",
                finish_code="painted",
                color="",
                price_cents=8000,
            )
        with pytest.raises(ProductNotFoundError):
            await catalog.quick_entry(
                product_id=uuid4(),
                name=None,
                category_id=None,
                scale_code="H0",
                finish_code="painted",
                color="",
                price_cents=8000,
            )
