"""Catalogue of the admin area: products, scales, variants, galleries, categories.

Every answer about a product carries the whole product and its version as ``ETag``.
Routes that overwrite what the client saw require ``If-Match``; the other commands
check it when it is sent.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel

from modellbahn.modules.catalog.api.deps import (
    CatalogEditor,
    CatalogServiceDep,
    IfMatch,
    ScaleServiceDep,
    expected_version,
    set_etag,
)
from modellbahn.modules.catalog.api.errors import (
    ACCESS,
    PRODUCT_NOT_FOUND,
    VERSION_REQUIRED,
    VERSIONED,
)
from modellbahn.modules.catalog.api.schemas import (
    AdminScaleOut,
    CategoryCreateIn,
    CategoryOut,
    CategoryPatchIn,
    DimensionsIn,
    GalleryAttachIn,
    GalleryIn,
    ProductCreateIn,
    ProductOut,
    ProductPageOut,
    ProductPatchIn,
    ProductScaleIn,
    ReferencesOut,
    ScaleCreateIn,
    ScalePatchIn,
    VariantCreateIn,
    VariantPatchIn,
    exact_decimal,
)
from modellbahn.modules.catalog.application.services import ProductDetails
from modellbahn.modules.catalog.domain.model import UNSET, ProductStatus
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/admin", tags=["admin-catalog"])

_SCALE_NOT_FOUND = {404: ["product_scale_not_found"]}
_VARIANT_NOT_FOUND = {404: ["variant_not_found"]}


def _product(details: ProductDetails, response: Response) -> ProductOut:
    set_etag(response, details.product.version)
    return ProductOut.from_details(details)


def _given(body: BaseModel, name: str, *, nullable: bool = False) -> Any:
    """The field's value if the client sent it, else ``UNSET`` (the change leaves it alone).

    Only ``nullable`` fields can be cleared with null; for the others null means "unchanged".
    """
    if name not in body.model_fields_set:
        return UNSET
    value = getattr(body, name)
    return UNSET if value is None and not nullable else value


# --- Reference data and categories ----------------------------------------------------


@router.get(
    "/catalog/references",
    operation_id="getCatalogReferences",
    summary="Scales, finishes and epochs",
    responses=problems(ACCESS, unsafe=False, validated=False),
)
async def get_references(_: CatalogEditor, service: CatalogServiceDep) -> ReferencesOut:
    return ReferencesOut.from_references(await service.references())


@router.get(
    "/categories",
    operation_id="listCategories",
    summary="All categories (flat, with parent)",
    responses=problems(ACCESS, unsafe=False, validated=False),
)
async def list_categories(_: CatalogEditor, service: CatalogServiceDep) -> list[CategoryOut]:
    return [CategoryOut.from_category(c) for c in await service.list_categories()]


@router.post(
    "/categories",
    status_code=status.HTTP_201_CREATED,
    operation_id="createCategory",
    summary="Create a category",
    responses=problems({**ACCESS, 409: ["slug_taken"]}),
)
async def create_category(
    body: CategoryCreateIn, _: CatalogEditor, service: CatalogServiceDep
) -> CategoryOut:
    category = await service.create_category(
        name=body.name, slug=body.slug, parent_id=body.parent_id, position=body.position
    )
    return CategoryOut.from_category(category)


@router.patch(
    "/categories/{category_id}",
    operation_id="updateCategory",
    summary="Rename, move or reorder a category",
    responses=problems({**ACCESS, 404: ["category_not_found"], 409: ["slug_taken"]}),
)
async def update_category(
    category_id: UUID, body: CategoryPatchIn, _: CatalogEditor, service: CatalogServiceDep
) -> CategoryOut:
    category = await service.change_category(
        category_id,
        name=_given(body, "name"),
        slug=_given(body, "slug"),
        parent_id=_given(body, "parent_id", nullable=True),
        position=_given(body, "position"),
    )
    return CategoryOut.from_category(category)


# --- Scales ---------------------------------------------------------------------------

_SCALE_MISSING = {404: ["scale_not_found"]}


@router.get(
    "/scales",
    operation_id="listScales",
    summary="Every scale, the smallest models first, with how many products use it",
    responses=problems(ACCESS, unsafe=False, validated=False),
)
async def list_scales(_: CatalogEditor, service: ScaleServiceDep) -> list[AdminScaleOut]:
    return [AdminScaleOut.from_usage(usage) for usage in await service.list_scales()]


@router.post(
    "/scales",
    status_code=status.HTTP_201_CREATED,
    operation_id="createScale",
    summary="Add a scale, e.g. 1:24 for road vehicles",
    responses=problems(ACCESS),
)
async def create_scale(
    body: ScaleCreateIn, _: CatalogEditor, service: ScaleServiceDep
) -> AdminScaleOut:
    usage = await service.create_scale(
        code=body.code,
        name=body.name,
        ratio_denominator=exact_decimal(body.ratio_denominator),
        track_gauge_mm=None if body.track_gauge_mm is None else exact_decimal(body.track_gauge_mm),
    )
    return AdminScaleOut.from_usage(usage)


@router.patch(
    "/scales/{code}",
    operation_id="updateScale",
    summary="Rename a scale or correct its ratio or track gauge (the code stays)",
    responses=problems({**ACCESS, **_SCALE_MISSING}),
)
async def update_scale(
    code: str, body: ScalePatchIn, _: CatalogEditor, service: ScaleServiceDep
) -> AdminScaleOut:
    ratio = _given(body, "ratio_denominator")
    gauge = _given(body, "track_gauge_mm", nullable=True)
    usage = await service.change_scale(
        code,
        name=_given(body, "name"),
        ratio_denominator=ratio if ratio is UNSET else exact_decimal(ratio),
        track_gauge_mm=gauge if gauge is UNSET or gauge is None else exact_decimal(gauge),
    )
    return AdminScaleOut.from_usage(usage)


@router.delete(
    "/scales/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteScale",
    summary="Remove a scale no product and no photo uses",
    responses=problems({**ACCESS, **_SCALE_MISSING, 409: ["scale_in_use"]}),
)
async def delete_scale(code: str, _: CatalogEditor, service: ScaleServiceDep) -> None:
    await service.delete_scale(code)


# --- Products -------------------------------------------------------------------------


@router.get(
    "/products",
    operation_id="listProducts",
    summary="Products, newest first",
    responses=problems(ACCESS, unsafe=False),
)
async def list_products(
    _: CatalogEditor,
    service: CatalogServiceDep,
    *,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    q: Annotated[str | None, Query(max_length=200, description="German full-text search.")] = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ProductPageOut:
    page = await service.list_products(status=status_filter, text=q, cursor=cursor, limit=limit)
    return ProductPageOut.from_page(page)


@router.post(
    "/products",
    status_code=status.HTTP_201_CREATED,
    operation_id="createProduct",
    summary="Create a draft product",
    responses=problems({**ACCESS, 409: ["slug_taken"]}),
)
async def create_product(
    body: ProductCreateIn, response: Response, _: CatalogEditor, service: CatalogServiceDep
) -> ProductOut:
    details = await service.create_product(name=body.name, slug=body.slug)
    response.headers["Location"] = f"/api/v1/admin/products/{details.product.id}"
    return _product(details, response)


@router.get(
    "/products/{product_id}",
    operation_id="getProduct",
    summary="A product with scales, variants and gallery",
    responses=problems({**ACCESS, **PRODUCT_NOT_FOUND}, unsafe=False),
)
async def get_product(
    product_id: UUID, response: Response, _: CatalogEditor, service: CatalogServiceDep
) -> ProductOut:
    return _product(await service.get_product(product_id), response)


@router.patch(
    "/products/{product_id}",
    operation_id="updateProduct",
    summary="Change texts, address, category or epochs",
    responses=problems(
        {**ACCESS, **PRODUCT_NOT_FOUND, **VERSION_REQUIRED, 409: ["slug_taken", "slug_locked"]}
    ),
)
async def update_product(
    product_id: UUID,
    body: ProductPatchIn,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    """Needs ``If-Match``. On a product in the shop, the shop's rules must still hold."""
    details = await service.change_product(
        product_id,
        expected_version=expected_version(if_match, required=True),
        name=_given(body, "name"),
        slug=_given(body, "slug"),
        summary=_given(body, "summary"),
        description=_given(body, "description"),
        prototype=_given(body, "prototype"),
        primary_category_id=_given(body, "primary_category_id", nullable=True),
        epoch_codes=_given(body, "epoch_codes"),
    )
    return _product(details, response)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    operation_id="deleteProduct",
    summary="Delete a draft that was never published",
    responses=problems(
        {
            **ACCESS,
            **PRODUCT_NOT_FOUND,
            **VERSIONED,
            409: ["product_not_deletable", "variant_has_units"],
        }
    ),
)
async def delete_product(
    product_id: UUID, _: CatalogEditor, service: CatalogServiceDep, if_match: IfMatch = None
) -> None:
    await service.delete_product(
        product_id, expected_version=expected_version(if_match, required=False)
    )


@router.post(
    "/products/{product_id}/publish",
    operation_id="publishProduct",
    summary="Put the product into the shop",
    responses=problems(
        {
            **ACCESS,
            **PRODUCT_NOT_FOUND,
            **VERSIONED,
            409: ["invalid_product_state"],
            422: ["not_publishable"],
        }
    ),
)
async def publish_product(
    product_id: UUID,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    """Needs a category, an active variant and a ready main image (422 lists what is missing)."""
    details = await service.publish(
        product_id, expected_version=expected_version(if_match, required=False)
    )
    return _product(details, response)


@router.post(
    "/products/{product_id}/archive",
    operation_id="archiveProduct",
    summary="Take the product out of the shop",
    responses=problems(
        {**ACCESS, **PRODUCT_NOT_FOUND, **VERSIONED, 409: ["invalid_product_state"]}
    ),
)
async def archive_product(
    product_id: UUID,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    details = await service.archive(
        product_id, expected_version=expected_version(if_match, required=False)
    )
    return _product(details, response)


# --- Scales and variants --------------------------------------------------------------


@router.post(
    "/products/{product_id}/scales",
    status_code=status.HTTP_201_CREATED,
    operation_id="addProductScale",
    summary="Offer the product in another scale",
    responses=problems({**ACCESS, **PRODUCT_NOT_FOUND, **VERSIONED, 409: ["scale_exists"]}),
)
async def add_product_scale(
    product_id: UUID,
    body: ProductScaleIn,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    details = await service.add_scale(
        product_id,
        expected_version=expected_version(if_match, required=False),
        scale_code=body.scale_code,
        dimensions=body.to_dimensions(),
    )
    return _product(details, response)


@router.patch(
    "/product-scales/{product_scale_id}",
    operation_id="updateProductScale",
    summary="Set the size and weight in this scale",
    responses=problems({**ACCESS, **_SCALE_NOT_FOUND, **VERSIONED}),
)
async def update_product_scale(
    product_scale_id: UUID,
    body: DimensionsIn,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    """Replaces all four values; null means unknown."""
    details = await service.change_scale(
        product_scale_id,
        expected_version=expected_version(if_match, required=False),
        dimensions=body.to_dimensions(),
    )
    return _product(details, response)


@router.delete(
    "/product-scales/{product_scale_id}",
    operation_id="deleteProductScale",
    summary="Stop offering the product in this scale",
    responses=problems(
        {
            **ACCESS,
            **_SCALE_NOT_FOUND,
            **VERSIONED,
            409: ["variant_has_units"],
            422: ["not_publishable"],
        }
    ),
)
async def delete_product_scale(
    product_scale_id: UUID,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    """Removes its variants too; answers with the changed product."""
    details = await service.remove_scale(
        product_scale_id, expected_version=expected_version(if_match, required=False)
    )
    return _product(details, response)


@router.post(
    "/product-scales/{product_scale_id}/variants",
    status_code=status.HTTP_201_CREATED,
    operation_id="addVariant",
    summary="Sell the scale in another finish",
    responses=problems({**ACCESS, **_SCALE_NOT_FOUND, **VERSIONED, 409: ["variant_exists"]}),
)
async def add_variant(
    product_scale_id: UUID,
    body: VariantCreateIn,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    """SKU and internal EAN-13 are assigned automatically."""
    details = await service.add_variant(
        product_scale_id,
        expected_version=expected_version(if_match, required=False),
        finish_code=body.finish_code,
        price_cents=body.price_cents,
        compare_at_price_cents=body.compare_at_price_cents,
        allow_backorder=body.allow_backorder,
        active=body.active,
    )
    return _product(details, response)


@router.patch(
    "/variants/{variant_id}",
    operation_id="updateVariant",
    summary="Change price, former price, backorders or availability",
    responses=problems({**ACCESS, **_VARIANT_NOT_FOUND, **VERSIONED, 422: ["not_publishable"]}),
)
async def update_variant(
    variant_id: UUID,
    body: VariantPatchIn,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    """Only the fields sent change; ``compare_at_price_cents: null`` removes the former price."""
    details = await service.change_variant(
        variant_id,
        expected_version=expected_version(if_match, required=False),
        price_cents=_given(body, "price_cents"),
        compare_at_price_cents=_given(body, "compare_at_price_cents", nullable=True),
        allow_backorder=_given(body, "allow_backorder"),
        active=_given(body, "active"),
    )
    return _product(details, response)


@router.delete(
    "/variants/{variant_id}",
    operation_id="deleteVariant",
    summary="Remove a variant (one with units in the workshop can only be deactivated)",
    responses=problems(
        {
            **ACCESS,
            **_VARIANT_NOT_FOUND,
            **VERSIONED,
            409: ["variant_has_units"],
            422: ["not_publishable"],
        }
    ),
)
async def delete_variant(
    variant_id: UUID,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    details = await service.remove_variant(
        variant_id, expected_version=expected_version(if_match, required=False)
    )
    return _product(details, response)


# --- Gallery --------------------------------------------------------------------------


@router.post(
    "/products/{product_id}/media",
    operation_id="attachProductImage",
    summary="Append an uploaded image to the gallery",
    responses=problems({**ACCESS, **PRODUCT_NOT_FOUND}),
)
async def attach_image(
    product_id: UUID,
    body: GalleryAttachIn,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
) -> ProductOut:
    """Takes images whose upload is complete, even while they are still processed.

    Needs no ``If-Match``: several uploads may append to the same gallery at once.
    """
    details = await service.attach_image(product_id, asset_id=body.asset_id, alt_text=body.alt_text)
    return _product(details, response)


@router.put(
    "/products/{product_id}/media",
    operation_id="arrangeProductGallery",
    summary="Order, roles, alt texts and tags of the gallery in one step",
    responses=problems(
        {**ACCESS, **PRODUCT_NOT_FOUND, **VERSION_REQUIRED, 422: ["not_publishable"]}
    ),
)
async def arrange_gallery(
    product_id: UUID,
    body: GalleryIn,
    response: Response,
    _: CatalogEditor,
    service: CatalogServiceDep,
    if_match: IfMatch = None,
) -> ProductOut:
    """Needs ``If-Match``. Images left out are removed from the gallery (not deleted)."""
    details = await service.arrange_gallery(
        product_id,
        expected_version=expected_version(if_match, required=True),
        entries=[entry.to_entry() for entry in body.entries],
    )
    return _product(details, response)
