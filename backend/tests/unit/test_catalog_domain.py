"""The catalogue model without a database: texts, numbers, the product's rules."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from modellbahn.modules.catalog.application.cursors import decode_cursor, encode_cursor
from modellbahn.modules.catalog.application.ports import ProductCursor
from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.catalog.domain.errors import (
    InvalidFieldError,
    InvalidProductStateError,
    ProductNotDeletableError,
    ProductNotPublishableError,
    PublishBlocker,
    ScaleAlreadyAddedError,
    SlugLockedError,
    UnknownReferenceError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from modellbahn.modules.catalog.domain.events import ProductArchived, ProductPublished
from modellbahn.modules.catalog.domain.model import (
    Dimensions,
    Finish,
    GalleryEntry,
    MediaRole,
    Product,
    ProductStatus,
    Scale,
    Variant,
    VariantDraft,
    check_price,
    ean13_check_digit,
    internal_gtin,
    variant_sku,
)
from modellbahn.modules.catalog.domain.text import check_slug, multi_line, single_line, slugify
from tests.support import NOW

H0 = Scale(code="H0", name="H0", ratio_denominator=Decimal(87), track_gauge_mm=Decimal("16.5"))
N = Scale(code="N", name="N", ratio_denominator=Decimal(160), track_gauge_mm=Decimal("9.0"))
UNPAINTED = Finish(code="unpainted", name="Bausatz", sku_letter="B", position=1)
PAINTED = Finish(code="painted", name="Fertigmodell", sku_letter="F", position=2, colored=True)
PRIMED = Finish(code="primed", name="grundiert", sku_letter="G", position=3, offered=False)


def product(number: int = 42) -> Product:
    return Product.create(
        number=number, name="Stellwerk Altenau", slug="stellwerk-altenau", now=NOW
    )


def sellable() -> Product:
    """A draft that satisfies every rule of the shop (with a ready main image)."""
    item = product()
    item.change_details(primary_category_id=uuid4(), now=NOW)
    scale = item.add_scale(H0, Dimensions(), NOW)
    item.add_variant(scale.id, VariantDraft(finish=PAINTED, price_cents=4990), gtin="x", now=NOW)
    item.attach_image(uuid4(), alt_text="", now=NOW)
    return item


class TestTexts:
    @pytest.mark.parametrize(
        ("name", "slug"),
        [
            ("Stellwerk Altenau (H0)", "stellwerk-altenau-h0"),
            ("Güterschuppen Hörsel", "gueterschuppen-hoersel"),
            ("Straßenbrücke   Süd", "strassenbruecke-sued"),
            ("Café-Haus «Élise»", "cafe-haus-elise"),
        ],
    )
    def test_slugs_from_german_names(self, name: str, slug: str) -> None:
        assert slugify(name) == slug

    def test_slug_rules(self) -> None:
        assert len(slugify("x" * 200)) == 80
        with pytest.raises(InvalidFieldError):
            slugify("!!!")
        assert check_slug("bw-12") == "bw-12"
        for invalid in ("Groß", "a--b", "-a", "a b", "a" * 81):
            with pytest.raises(InvalidFieldError):
                check_slug(invalid)

    def test_single_line_collapses_whitespace_and_controls(self) -> None:
        assert single_line("  Lok\tschuppen \n mit\u200b Tor ", field="f", max_length=50) == (
            "Lokschuppen mit Tor"
        )
        with pytest.raises(InvalidFieldError) as caught:
            single_line("   ", field="name", max_length=10)
        assert caught.value.code == "required"
        assert single_line("", field="summary", max_length=10, required=False) == ""

    def test_multi_line_keeps_paragraphs(self) -> None:
        text = "Erste Zeile  \r\nZweite\x07 Zeile\n\n\n\nNeuer Absatz\n"
        assert multi_line(text, field="d", max_length=100) == (
            "Erste Zeile\nZweite Zeile\n\nNeuer Absatz"
        )
        with pytest.raises(InvalidFieldError):
            multi_line("x" * 11, field="d", max_length=10)


class TestNumbers:
    def test_ean13_check_digit(self) -> None:
        # Printed on a well-known product: 4 006381 33393 1.
        assert ean13_check_digit("400638133393") == 1
        with pytest.raises(ValueError, match="twelve"):
            ean13_check_digit("123")

    def test_internal_gtins_use_prefix_20(self) -> None:
        gtin = internal_gtin(42)
        assert gtin.startswith("2000000000")
        assert len(gtin) == 13
        assert int(gtin[-1]) == ean13_check_digit(gtin[:12])
        with pytest.raises(ValueError, match="digits"):
            internal_gtin(10**10)

    def test_sku(self) -> None:
        assert variant_sku(42, "h0", PAINTED) == "MB-000042-H0-F"
        assert variant_sku(42, "h0", PAINTED, 3) == "MB-000042-H0-F3"

    def test_prices(self) -> None:
        check_price(0, None)
        check_price(4990, 5990)
        with pytest.raises(InvalidFieldError):
            check_price(-1, None)
        with pytest.raises(InvalidFieldError) as caught:
            check_price(4990, 4990)
        assert caught.value.field == "compare_at_price_cents"

    def test_dimensions(self) -> None:
        Dimensions(length_mm=Decimal("112.5"), weight_g=80)
        with pytest.raises(InvalidFieldError):
            Dimensions(height_mm=Decimal(0))
        with pytest.raises(InvalidFieldError):
            Dimensions(weight_g=0)

    def test_cursors_round_trip(self) -> None:
        cursor = ProductCursor(id=uuid4(), published_at=NOW)
        assert decode_cursor(encode_cursor(cursor)) == cursor
        plain = ProductCursor(id=uuid4())
        assert decode_cursor(encode_cursor(plain)) == plain
        for broken in ("", "nicht-base64!", encode_cursor(cursor)[:-3], "eyJwIjoiMjAyNiJ9"):
            with pytest.raises(InvalidFieldError):
                decode_cursor(broken)


def weeks(variant: Variant) -> tuple[int, int] | None:
    """The lead time, read afresh (an earlier assert must not narrow it for mypy)."""
    return variant.lead_time_weeks


class TestGaugesAndVariants:
    def test_each_scale_once_and_each_finish_once_per_scale(self) -> None:
        item = product()
        scale = item.add_scale(H0, Dimensions(length_mm=Decimal("98.0")), NOW)
        with pytest.raises(ScaleAlreadyAddedError):
            item.add_scale(H0, Dimensions(), NOW)
        variant = item.add_variant(
            scale.id, VariantDraft(finish=UNPAINTED, price_cents=2990), gtin="2x", now=NOW
        )
        assert variant.sku == "MB-000042-H0-B"
        with pytest.raises(VariantAlreadyExistsError):
            item.add_variant(
                scale.id, VariantDraft(finish=UNPAINTED, price_cents=1), gtin="2y", now=NOW
            )
        item.add_variant(
            scale.id, VariantDraft(finish=PAINTED, price_cents=5990), gtin="2z", now=NOW
        )
        assert [v.finish_code for v in item.variants] == ["unpainted", "painted"]

    def test_a_finished_model_comes_in_colours_a_kit_does_not(self) -> None:
        item = product()
        scale = item.add_scale(H0, Dimensions(), NOW)

        def add(finish: Finish, color: str, gtin: str) -> Variant:
            draft = VariantDraft(finish=finish, price_cents=8000, color=color)
            return item.add_variant(scale.id, draft, gtin=gtin, now=NOW)

        yellow = add(PAINTED, " gelb ", "2a")
        assert (yellow.color, yellow.sku) == ("Gelb", "MB-000042-H0-F")
        blue = add(PAINTED, "Hellblau", "2b")
        assert blue.sku == "MB-000042-H0-F2"
        with pytest.raises(VariantAlreadyExistsError):
            add(PAINTED, "HELLBLAU", "2c")  # the same colour, whatever the case
        with pytest.raises(InvalidFieldError) as kit:
            add(UNPAINTED, "Rot", "2d")
        assert (kit.value.field, kit.value.code) == ("color", "not_colored")
        assert add(UNPAINTED, "", "2e").sku == "MB-000042-H0-B"

        with pytest.raises(VariantAlreadyExistsError):
            item.change_variant(blue.id, color="gelb", colored=True, now=NOW)
        item.change_variant(blue.id, color="Lichtblau", colored=True, now=NOW)
        assert (blue.color, blue.sku) == ("Lichtblau", "MB-000042-H0-F2")  # the SKU stays
        # A further colour after a gap takes the first free number.
        item.remove_variant(yellow.id, NOW)
        assert add(PAINTED, "Grün", "2f").sku == "MB-000042-H0-F"

    def test_one_colour_left_unnamed_or_only_named_colours(self) -> None:
        item = product()
        scale = item.add_scale(H0, Dimensions(), NOW)

        def add(color: str, gtin: str) -> Variant:
            draft = VariantDraft(finish=PAINTED, price_cents=8000, color=color)
            return item.add_variant(scale.id, draft, gtin=gtin, now=NOW)

        plain = add("", "2a")
        # Next to the unnamed one, a second colour could not be chosen in the shop.
        with pytest.raises(InvalidFieldError) as unnamed:
            add("Blau", "2b")
        assert (unnamed.value.field, unnamed.value.code) == ("color", "unnamed_sibling")
        item.change_variant(plain.id, color="Gelb", colored=True, now=NOW)
        add("Blau", "2b")
        with pytest.raises(InvalidFieldError) as required:
            add("", "2c")
        assert (required.value.field, required.value.code) == ("color", "required")
        with pytest.raises(InvalidFieldError):
            item.change_variant(plain.id, color="", colored=True, now=NOW)
        # The kit stays on its own: one per scale, without colour.
        kit = VariantDraft(finish=UNPAINTED, price_cents=2990)
        item.add_variant(scale.id, kit, gtin="2d", now=NOW)

    def test_primed_takes_no_new_variants(self) -> None:
        item = product()
        scale = item.add_scale(H0, Dimensions(), NOW)
        with pytest.raises(InvalidFieldError) as refused:
            item.add_variant(
                scale.id, VariantDraft(finish=PRIMED, price_cents=1990), gtin="2x", now=NOW
            )
        assert refused.value.code == "not_offered"

    def test_change_variant_checks_the_resulting_prices(self) -> None:
        item = product()
        scale = item.add_scale(H0, Dimensions(), NOW)
        variant = item.add_variant(
            scale.id,
            VariantDraft(finish=PAINTED, price_cents=4990, compare_at_price_cents=5990),
            gtin="2x",
            now=NOW,
        )
        with pytest.raises(InvalidFieldError):
            item.change_variant(variant.id, price_cents=6990, now=NOW)
        item.change_variant(variant.id, price_cents=6990, compare_at_price_cents=None, now=NOW)
        assert (variant.price_cents, variant.compare_at_price_cents) == (6990, None)
        with pytest.raises(VariantNotFoundError):
            item.change_variant(uuid4(), active=False, now=NOW)

    def test_made_to_order_always_has_a_lead_time(self) -> None:
        item = product()
        scale = item.add_scale(H0, Dimensions(), NOW)
        stocked = item.add_variant(
            scale.id, VariantDraft(finish=PAINTED, price_cents=4990), gtin="2x", now=NOW
        )
        assert weeks(stocked) is None
        # Switched to made to order without a lead time: the default of 1 to 2 weeks.
        item.change_variant(stocked.id, allow_backorder=True, now=NOW)
        assert weeks(stocked) == (1, 2)
        item.change_variant(stocked.id, lead_time_weeks=(8, 12), now=NOW)
        assert (stocked.lead_time_min_weeks, stocked.lead_time_max_weeks) == (8, 12)
        # Clearing it while made to order brings the default back.
        item.change_variant(stocked.id, lead_time_weeks=None, now=NOW)
        assert weeks(stocked) == (1, 2)
        item.change_variant(stocked.id, allow_backorder=False, lead_time_weeks=None, now=NOW)
        assert weeks(stocked) is None
        made = item.add_variant(
            scale.id,
            VariantDraft(
                finish=UNPAINTED, price_cents=2990, allow_backorder=True, lead_time_weeks=(2, 2)
            ),
            gtin="2y",
            now=NOW,
        )
        assert weeks(made) == (2, 2)

    @pytest.mark.parametrize(
        ("weeks", "field"),
        [
            ((0, 4), "lead_time_min_weeks"),
            ((53, 60), "lead_time_min_weeks"),
            ((6, 4), "lead_time_max_weeks"),
            ((4, 53), "lead_time_max_weeks"),
        ],
    )
    def test_lead_times_stay_within_a_year(self, weeks: tuple[int, int], field: str) -> None:
        item = product()
        scale = item.add_scale(H0, Dimensions(), NOW)
        with pytest.raises(InvalidFieldError) as error:
            item.add_variant(
                scale.id,
                VariantDraft(
                    finish=PAINTED, price_cents=1, allow_backorder=True, lead_time_weeks=weeks
                ),
                gtin="2x",
                now=NOW,
            )
        assert error.value.field == field

    def test_removing_a_scale_untags_its_photos(self) -> None:
        item = product()
        scale = item.add_scale(N, Dimensions(), NOW)
        asset_id = uuid4()
        item.attach_image(asset_id, alt_text="", now=NOW)
        item.arrange_gallery(
            [GalleryEntry(asset_id=asset_id, scale_code="N")], main_image_ready=True, now=NOW
        )
        item.remove_scale(scale.id, NOW)
        assert item.scales == []
        assert item.media[0].scale_code is None


class TestGallery:
    def test_attach_appends_and_ignores_repeats(self) -> None:
        item = product()
        first, second = uuid4(), uuid4()
        item.attach_image(first, alt_text=" Ansicht  von vorn ", now=NOW)
        item.attach_image(second, alt_text="", now=NOW)
        item.attach_image(first, alt_text="anders", now=NOW)
        assert [(m.asset_id, m.position) for m in item.gallery] == [(first, 0), (second, 1)]
        assert item.main_image is not None
        assert item.main_image.alt_text == "Ansicht von vorn"

    def test_arrange_reorders_tags_and_removes(self) -> None:
        item = product()
        item.add_scale(H0, Dimensions(), NOW)
        first, second, third = uuid4(), uuid4(), uuid4()
        for asset_id in (first, second, third):
            item.attach_image(asset_id, alt_text="", now=NOW)
        item.arrange_gallery(
            [
                GalleryEntry(asset_id=third, role=MediaRole.DETAIL, alt_text="Tür"),
                GalleryEntry(asset_id=first, scale_code="H0", finish_code="painted"),
            ],
            main_image_ready=True,
            now=NOW,
        )
        assert [(m.asset_id, m.position, m.role) for m in item.gallery] == [
            (third, 0, MediaRole.DETAIL),
            (first, 1, MediaRole.GALLERY),
        ]
        assert item.gallery[1].scale_code == "H0"

    @pytest.mark.parametrize("problem", ["duplicate", "unknown_asset", "unknown_scale"])
    def test_arrange_refuses_inconsistent_lists(self, problem: str) -> None:
        item = product()
        known = uuid4()
        item.attach_image(known, alt_text="", now=NOW)
        entries = {
            "duplicate": [GalleryEntry(asset_id=known), GalleryEntry(asset_id=known)],
            "unknown_asset": [GalleryEntry(asset_id=uuid4())],
            "unknown_scale": [GalleryEntry(asset_id=known, scale_code="TT")],
        }[problem]
        with pytest.raises(InvalidFieldError) as caught:
            item.arrange_gallery(entries, main_image_ready=True, now=NOW)
        if problem != "duplicate":
            assert isinstance(caught.value, UnknownReferenceError)


class TestLifeCycle:
    def test_publish_lists_everything_missing(self) -> None:
        item = product()
        assert item.publish_blockers(main_image_ready=False) == [
            PublishBlocker.NO_CATEGORY,
            PublishBlocker.NO_ACTIVE_VARIANT,
            PublishBlocker.NO_MAIN_IMAGE,
        ]
        with pytest.raises(ProductNotPublishableError) as caught:
            item.publish(main_image_ready=False, now=NOW)
        assert len(caught.value.blockers) == 3
        ready = sellable()
        assert ready.publish_blockers(main_image_ready=False) == [
            PublishBlocker.MAIN_IMAGE_NOT_READY
        ]
        assert ready.publish_blockers(main_image_ready=True) == []

    def test_publish_archive_and_publish_again(self) -> None:
        item = sellable()
        event = item.publish(main_image_ready=True, now=NOW)
        assert isinstance(event, ProductPublished)
        assert (item.status, item.published_at) == (ProductStatus.ACTIVE, NOW)
        with pytest.raises(InvalidProductStateError):
            item.publish(main_image_ready=True, now=NOW)
        assert isinstance(item.archive(NOW + timedelta(days=1)), ProductArchived)
        assert item.archived_at is not None
        with pytest.raises(InvalidProductStateError):
            item.archive(NOW)
        item.publish(main_image_ready=True, now=NOW + timedelta(days=2))
        # "New in the shop" keeps referring to the first publication.
        assert item.published_at == NOW
        assert item.archived_at is None

    def test_a_product_in_the_shop_keeps_satisfying_the_rules(self) -> None:
        item = sellable()
        item.publish(main_image_ready=True, now=NOW)
        (variant,) = item.variants
        with pytest.raises(ProductNotPublishableError):
            item.change_variant(variant.id, active=False, now=NOW)
        with pytest.raises(ProductNotPublishableError):
            item.change_details(primary_category_id=None, now=NOW)
        with pytest.raises(ProductNotPublishableError):
            item.arrange_gallery([], main_image_ready=False, now=NOW)
        assert item.change_notice(NOW) is not None
        assert product().change_notice(NOW) is None

    def test_the_slug_is_fixed_once_published(self) -> None:
        item = sellable()
        item.change_details(slug="stellwerk-altenau-h0", now=NOW)
        item.publish(main_image_ready=True, now=NOW)
        item.change_details(slug="stellwerk-altenau-h0", name="Neuer Name", now=NOW)
        with pytest.raises(SlugLockedError):
            item.change_details(slug="anders", now=NOW)

    def test_only_unpublished_drafts_can_be_deleted(self) -> None:
        product().ensure_deletable()
        item = sellable()
        item.publish(main_image_ready=True, now=NOW)
        item.archive(NOW)
        with pytest.raises(ProductNotDeletableError):
            item.ensure_deletable()

    def test_epochs_keep_their_rows(self) -> None:
        item = product()
        item.change_details(epoch_codes=["III", "IV", "III"], now=NOW)
        kept = item.epochs[0]
        item.change_details(epoch_codes=["IV", "III", "V"], now=NOW)
        assert sorted(item.epoch_codes) == ["III", "IV", "V"]
        assert kept in item.epochs


def test_the_contract_hands_out_the_domain_events() -> None:
    from modellbahn.modules.catalog.contracts import events  # noqa: PLC0415

    assert events.ProductPublished is ProductPublished
    assert events.ProductArchived is ProductArchived


def test_an_order_line_names_the_colour() -> None:
    sale = SaleVariant(
        variant_id=uuid4(),
        gtin="2000000000428",
        product_id=uuid4(),
        product_slug="ifa-adk-70-autokran",
        product_name="IFA ADK 70 Autokran",
        scale_code="H0",
        scale_name="H0",
        finish_code="painted",
        finish_name="Fertigmodell",
        color="Gelb",
        sku="MB-000042-H0-F",
        price_cents=8000,
        compare_at_price_cents=None,
        image_asset_id=None,
        purchasable=True,
        allow_backorder=False,
        lead_time_weeks=None,
    )
    assert sale.title == "IFA ADK 70 Autokran · H0 · Fertigmodell, Gelb"
    kit = replace(sale, finish_code="unpainted", finish_name="Bausatz", color="")
    assert kit.variant_name == "H0 · Bausatz"
