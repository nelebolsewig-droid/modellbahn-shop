"""What an eBay offer says, written from the catalogue: title, description, item specifics.

Pure functions: the listing service gathers the facts (product, stock, photos, account)
and these turn them into a :class:`ListingDraft`, or into the reason why the product
cannot go up as it is.

The item specifics follow eBay.de's model railway and model vehicle categories: brand,
scale as a ratio (``1:87``) and as a gauge (``H0``), era and prototype. The choices of a
listing differ in their finish (kit or finished model) and, for finished models in
several colours, in their colour.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from html import escape
from typing import Final
from uuid import UUID

from modellbahn.modules.catalog.contracts.listings import ListingSource
from modellbahn.modules.catalog.contracts.variants import SaleVariant
from modellbahn.modules.marketplace.application.ports import ListingDraft, OfferDraft
from modellbahn.modules.marketplace.domain.model import LOCATION_KEY, EbayAccount, Listing

TITLE_MAX_LENGTH: Final = 80
ASPECT_VALUE_MAX_LENGTH: Final = 65
IMAGES_MAX: Final = 24
FINISH: Final = "Ausführung"
COLOUR: Final = "Farbe"
KIT_FINISH: Final = "unpainted"
# The colour of a kit next to coloured finished models: it comes unpainted.
KIT_COLOUR: Final = "Unlackiert"


@dataclass(frozen=True, slots=True)
class HeldBack:
    """Why the product cannot go up on eBay as it is (a code and a German sentence)."""

    code: str
    message: str


def group_key(number: int, scale_code: str) -> str:
    """eBay's key of the listing: ``MB-000042-H0``."""
    return f"MB-{number:06d}-{scale_code}"


def ebay_category(source: ListingSource, category_map: Mapping[UUID, str]) -> str:
    """The eBay category of the product's own category, else of the nearest parent."""
    for category_id in source.category_ids:
        if category_map.get(category_id):
            return category_map[category_id]
    return ""


def build_draft(
    *,
    source: ListingSource,
    listing: Listing,
    account: EbayAccount,
    category_id: str,
    free_units: Mapping[UUID, int],
    gallery_urls: Sequence[str],
    variant_urls: Mapping[UUID, str],
    brand: str,
) -> ListingDraft | HeldBack:
    """The listing as eBay should show it now, or why it cannot go up.

    ``gallery_urls`` are the product's photos for the scale; ``variant_urls`` the photo
    that fits each variant best, shown first when a buyer picks that choice.
    """
    if not source.active:
        return HeldBack("not_in_shop", "Das Produkt ist nicht im Shop veröffentlicht.")
    variants = [variant for variant in source.variants if variant.purchasable]
    if not variants:
        return HeldBack("no_variant", "In diesem Maßstab ist keine Variante im Shop.")
    if not category_id:
        return HeldBack(
            "no_category", "Der Kategorie des Produkts ist keine eBay-Kategorie zugeordnet."
        )
    if not gallery_urls:
        return HeldBack("no_photo", "Das Produkt hat in diesem Maßstab noch kein fertiges Foto.")

    with_colour = any(variant.color for variant in variants)
    offers = [
        OfferDraft(
            sku=variant.sku,
            quantity=account.listing_quantity(
                free_units=free_units.get(variant.variant_id, 0),
                made_to_order=variant.allow_backorder,
            ),
            price_cents=account.listing_price(variant.price_cents),
            aspects=_choice(variant, with_colour=with_colour),
            image_urls=_photos(variant_urls.get(variant.variant_id), gallery_urls),
        )
        for variant in variants
    ]
    varies_by = (
        [name for name in (FINISH, COLOUR) if len({_value(o, name) for o in offers}) > 1]
        if len(offers) > 1
        else []
    )
    return ListingDraft(
        group_key=listing.group_key,
        title=title(source, variants, brand=brand),
        description_html=description(source, variants, brand=brand),
        category_id=category_id,
        aspects=_common_aspects(source, brand=brand),
        image_urls=list(gallery_urls)[:IMAGES_MAX],
        offers=offers,
        varies_by=varies_by,
        fulfillment_policy_id=account.fulfillment_policy_id,
        payment_policy_id=account.payment_policy_id,
        return_policy_id=account.return_policy_id,
        location_key=LOCATION_KEY,
        known_offer_ids=listing.offer_ids,
        previous_external_id=listing.external_id,
        previous_skus=[item.sku for item in listing.items],
    )


def title(source: ListingSource, variants: Sequence[SaleVariant], *, brand: str) -> str:
    """``IFA ADK 70 Autokran H0 1:87 Fertigmodell adp-Modelle``, at most 80 characters."""
    finishes = list(dict.fromkeys(variant.finish_name for variant in variants))
    parts = [source.name, f"{source.scale_name} {source.ratio}", " oder ".join(finishes), brand]
    text = ""
    for part in parts:
        candidate = f"{text} {part}".strip()
        if len(candidate) > TITLE_MAX_LENGTH:
            break
        text = candidate
    return text or source.name[:TITLE_MAX_LENGTH]


def description(source: ListingSource, variants: Sequence[SaleVariant], *, brand: str) -> str:
    """The offer's text as simple HTML (eBay allows no scripts and few styles)."""
    facts = [
        ("Maßstab", f"{source.scale_name} ({source.ratio})"),
        ("Spurweite", _millimetres(source.track_gauge_mm)),
        ("Epoche", ", ".join(source.epochs)),
        ("Vorbild", source.prototype),
        ("Maße (L x B x H)", _dimensions(source)),
        ("Gewicht", f"{source.weight_g} g" if source.weight_g else ""),
    ]
    rows = "".join(
        f'<tr><th style="text-align:left;padding:4px 16px 4px 0;font-weight:600">{escape(k)}</th>'
        f'<td style="padding:4px 0">{escape(v)}</td></tr>'
        for k, v in facts
        if v
    )
    choices = "".join(f"<li>{escape(_choice_line(variant))}</li>" for variant in variants)
    paragraphs = "".join(
        f"<p>{'<br>'.join(escape(line) for line in block.splitlines())}</p>"
        for block in source.description.split("\n\n")
        if block.strip()
    )
    summary = f"<p><strong>{escape(source.summary)}</strong></p>" if source.summary else ""
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;'
        'color:#1c1f24;max-width:860px">'
        f'<h1 style="font-size:24px;margin:0 0 8px">{escape(source.name)}</h1>'
        f"{summary}{paragraphs}"
        f'<h2 style="font-size:18px;margin:24px 0 8px">Ausführungen</h2><ul>{choices}</ul>'
        f'<h2 style="font-size:18px;margin:24px 0 8px">Daten</h2><table>{rows}</table>'
        f'<p style="margin-top:24px;color:#5b6370">{escape(brand)} · Modelle aus eigener '
        "Fertigung</p></div>"
    )


def _choice(variant: SaleVariant, *, with_colour: bool) -> dict[str, list[str]]:
    aspects = {FINISH: [variant.finish_name]}
    if with_colour:
        colour = variant.color or (KIT_COLOUR if variant.finish_code == KIT_FINISH else "")
        if colour:
            aspects[COLOUR] = [colour[:ASPECT_VALUE_MAX_LENGTH]]
    return aspects


def _value(offer: OfferDraft, name: str) -> str:
    return offer.aspects.get(name, [""])[0]


def _choice_line(variant: SaleVariant) -> str:
    finish = f"{variant.finish_name}, {variant.color}" if variant.color else variant.finish_name
    if variant.allow_backorder and variant.lead_time_weeks:
        low, high = variant.lead_time_weeks
        weeks = f"{low} Woche" if low == high == 1 else f"{low} bis {high} Wochen"
        return f"{finish}: wird auf Bestellung gefertigt, wenn nicht vorrätig ({weeks})"
    return finish


def _common_aspects(source: ListingSource, *, brand: str) -> dict[str, list[str]]:
    aspects = {
        "Marke": [brand],
        "Maßstab": [source.ratio],
        "Spurweite": [source.scale_name],
    }
    if source.epochs:
        aspects["Epoche"] = [epoch[:ASPECT_VALUE_MAX_LENGTH] for epoch in source.epochs]
    if source.prototype:
        aspects["Vorbild"] = [source.prototype[:ASPECT_VALUE_MAX_LENGTH]]
    return aspects


def _photos(first: str | None, gallery: Sequence[str]) -> list[str]:
    ordered = [first, *gallery] if first else list(gallery)
    return list(dict.fromkeys(ordered))[:IMAGES_MAX]


def _millimetres(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{value.normalize():f}".replace(".", ",") + " mm"


def _dimensions(source: ListingSource) -> str:
    sizes = (source.length_mm, source.width_mm, source.height_mm)
    if any(size is None for size in sizes):
        return ""
    return " x ".join(f"{size.normalize():f}".replace(".", ",") for size in sizes if size) + " mm"
