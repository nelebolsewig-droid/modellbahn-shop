"""What an eBay offer says, written from the catalogue."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from modellbahn.modules.catalog.contracts.listings import ListingSource
from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.marketplace.application.drafts import (
    COLOUR,
    FINISH,
    TITLE_MAX_LENGTH,
    HeldBack,
    build_draft,
    ebay_category,
    group_key,
    title,
)
from modellbahn.modules.marketplace.application.ports import ListingDraft
from modellbahn.modules.marketplace.domain.model import EbayAccount, Listing, Tokens

NOW = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
PRODUCT = uuid4()
BRAND = "adp-Modelle"


def variant(finish: str = "painted", color: str = "", **changes: object) -> SaleVariant:
    base = SaleVariant(
        variant_id=uuid4(),
        gtin="2000000000017",
        product_id=PRODUCT,
        product_slug="ifa-w50-kipper",
        product_name="IFA W50 Kipper",
        scale_code="H0",
        scale_name="H0",
        finish_code=finish,
        finish_name="Bausatz" if finish == "unpainted" else "Fertigmodell",
        color=color,
        sku=f"MB-000042-H0-{'B' if finish == 'unpainted' else 'F'}{color[:2]}",
        price_cents=4990 if finish == "painted" else 2990,
        compare_at_price_cents=None,
        image_asset_id=None,
        purchasable=True,
        allow_backorder=True,
        lead_time_weeks=(1, 2),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def source(*variants: SaleVariant, **changes: object) -> ListingSource:
    base = ListingSource(
        product_id=PRODUCT,
        number=42,
        slug="ifa-w50-kipper",
        name="IFA W50 Kipper",
        summary="Dreiseitenkipper der DDR.",
        description="Erste Zeile.\nZweite Zeile.\n\nNeuer Absatz mit <b>Klammern</b> & Co.",
        prototype="IFA W50 L/K",
        active=True,
        category_ids=(uuid4(), uuid4()),
        epochs=("Epoche IV (1970 bis 1990)",),
        scale_code="H0",
        scale_name="H0",
        ratio="1:87",
        track_gauge_mm=Decimal("16.5"),
        length_mm=Decimal("75.0"),
        width_mm=Decimal("29"),
        height_mm=Decimal("33.5"),
        weight_g=40,
        variants=variants,
        image_ids=(uuid4(),),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def account() -> EbayAccount:
    account = EbayAccount.new(NOW)
    account.connect(
        seller_name="adp-modelle",
        tokens=Tokens("a", NOW + timedelta(hours=2), "r", NOW + timedelta(days=500)),
        now=NOW,
    )
    account.change_settings(
        fulfillment_policy_id="F1",
        payment_policy_id="P1",
        return_policy_id="R1",
        price_markup_percent=10,
        made_to_order_quantity=3,
        now=NOW,
    )
    return account


def draft(
    listing_source: ListingSource,
    *,
    free: dict[UUID, int] | None = None,
    category: str = "180250",
    photos: tuple[str, ...] = ("https://shop.test/medien/a.webp",),
) -> ListingDraft | HeldBack:
    return build_draft(
        source=listing_source,
        listing=Listing.create(
            product_id=PRODUCT, scale_code="H0", group_key=group_key(42, "H0"), now=NOW
        ),
        account=account(),
        category_id=category,
        free_units=free or {},
        gallery_urls=photos,
        variant_urls={},
        brand=BRAND,
    )


def built(listing_source: ListingSource, **kwargs: object) -> ListingDraft:
    result = draft(listing_source, **kwargs)  # type: ignore[arg-type]
    assert isinstance(result, ListingDraft), result
    return result


class TestDraft:
    def test_one_variant_is_one_offer_without_choices(self) -> None:
        result = built(source(variant()))
        assert result.group_key == "MB-000042-H0"
        assert result.varies_by == []
        (offer,) = result.offers
        assert offer.aspects == {FINISH: ["Fertigmodell"]}
        # 10 % markup, and made to order: at least three at once.
        assert offer.price_cents == 5489
        assert offer.quantity == 3

    def test_kit_and_finished_model_differ_in_the_finish(self) -> None:
        result = built(source(variant("unpainted"), variant()))
        assert result.varies_by == [FINISH]

    def test_colours_make_the_kit_unpainted(self) -> None:
        result = built(source(variant("unpainted"), variant(color="Gelb"), variant(color="Rot")))
        assert result.varies_by == [FINISH, COLOUR]
        assert [offer.aspects[COLOUR] for offer in result.offers] == [
            ["Unlackiert"],
            ["Gelb"],
            ["Rot"],
        ]

    def test_stock_counts_for_variants_not_made_to_order(self) -> None:
        on_shelf = variant(allow_backorder=False, lead_time_weeks=None)
        result = built(source(on_shelf), free={on_shelf.variant_id: 2})
        assert result.offers[0].quantity == 2

    def test_variants_not_in_the_shop_stay_away(self) -> None:
        result = built(source(variant("unpainted", purchasable=False), variant()))
        assert [offer.aspects[FINISH] for offer in result.offers] == [["Fertigmodell"]]

    def test_the_item_specifics_come_from_the_catalogue(self) -> None:
        result = built(source(variant()))
        assert result.aspects == {
            "Marke": [BRAND],
            "Maßstab": ["1:87"],
            "Spurweite": ["H0"],
            "Epoche": ["Epoche IV (1970 bis 1990)"],
            "Vorbild": ["IFA W50 L/K"],
        }

    def test_the_description_is_escaped_html(self) -> None:
        html = built(source(variant())).description_html
        assert "&lt;b&gt;Klammern&lt;/b&gt; &amp; Co." in html
        assert "Erste Zeile.<br>Zweite Zeile." in html
        assert "75 x 29 x 33,5 mm" in html
        assert "16,5 mm" in html
        assert "1 bis 2 Wochen" in html
        assert "<script" not in html

    @pytest.mark.parametrize(
        ("listing_source", "kwargs", "code"),
        [
            (source(variant(), active=False), {}, "not_in_shop"),
            (source(variant(purchasable=False)), {}, "no_variant"),
            (source(variant()), {"category": ""}, "no_category"),
            (source(variant()), {"photos": ()}, "no_photo"),
        ],
    )
    def test_what_cannot_go_up_says_why(
        self, listing_source: ListingSource, kwargs: dict[str, object], code: str
    ) -> None:
        result = draft(listing_source, **kwargs)  # type: ignore[arg-type]
        assert isinstance(result, HeldBack)
        assert result.code == code
        assert result.message


class TestTitle:
    def test_name_scale_finishes_and_brand(self) -> None:
        text = title(source(), [variant("unpainted"), variant()], brand=BRAND)
        assert text == "IFA W50 Kipper H0 1:87 Bausatz oder Fertigmodell adp-Modelle"

    def test_long_names_drop_the_tail_first(self) -> None:
        long_name = "Löschgruppenfahrzeug LF 16 TS auf Robur LO 1800 A mit Vorbaupumpe und Leiter"
        text = title(source(name=long_name), [variant()], brand=BRAND)
        assert len(text) <= TITLE_MAX_LENGTH
        assert text.startswith(long_name)

    def test_never_longer_than_eighty(self) -> None:
        text = title(source(name="X" * 120), [variant()], brand=BRAND)
        assert len(text) == TITLE_MAX_LENGTH


def test_the_nearest_mapped_category_counts() -> None:
    leaf, parent = uuid4(), uuid4()
    listing_source = source(variant(), category_ids=(leaf, parent))
    assert ebay_category(listing_source, {parent: "123"}) == "123"
    assert ebay_category(listing_source, {leaf: "456", parent: "123"}) == "456"
    assert ebay_category(listing_source, {}) == ""
