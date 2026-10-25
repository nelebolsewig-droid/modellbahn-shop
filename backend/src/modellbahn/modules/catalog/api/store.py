"""Catalogue of the shop, public: ``/api/v1/store`` (navigation, product list, product page)."""

from typing import Annotated, Final, Literal

from fastapi import APIRouter, Query, Response

from modellbahn.modules.catalog.api.deps import STORE_CACHE_CONTROL, CatalogServiceDep
from modellbahn.modules.catalog.api.schemas import (
    NavigationOut,
    StoreProductOut,
    StoreProductPageOut,
)
from modellbahn.modules.catalog.application.ports import ProductOrder
from modellbahn.platform.errors import problems

router = APIRouter(prefix="/store", tags=["store-catalog"])

StoreSort = Literal["newest", "price_asc", "price_desc", "name"]
_STORE_ORDERS: Final[dict[str, ProductOrder]] = {
    "newest": ProductOrder.PUBLISHED,
    "price_asc": ProductOrder.PRICE_ASC,
    "price_desc": ProductOrder.PRICE_DESC,
    "name": ProductOrder.NAME,
}


@router.get(
    "/navigation",
    operation_id="getStoreNavigation",
    summary="Categories, scales, finishes and epochs for menus and filters, with counts",
    responses=problems(unsafe=False, validated=False),
)
async def get_navigation(response: Response, service: CatalogServiceDep) -> NavigationOut:
    navigation = await service.navigation()
    response.headers["Cache-Control"] = STORE_CACHE_CONTROL
    return NavigationOut.from_navigation(navigation)


@router.get(
    "/products",
    operation_id="listStoreProducts",
    summary="Products in the shop, newest first",
    responses=problems({404: ["category_not_found"]}, unsafe=False),
)
async def list_products(
    response: Response,
    service: CatalogServiceDep,
    *,
    category: Annotated[
        str | None,
        Query(max_length=80, description="Category slug; includes its subcategories."),
    ] = None,
    scale: Annotated[
        str | None, Query(max_length=10, description="Scale code, e.g. H0 or 124 (1:24).")
    ] = None,
    epoch: Annotated[str | None, Query(max_length=10, description="Epoch code, e.g. III.")] = None,
    q: Annotated[str | None, Query(max_length=200, description="German full-text search.")] = None,
    sort: Annotated[
        StoreSort, Query(description="Newest first (default), by price or by name.")
    ] = "newest",
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=48)] = 24,
) -> StoreProductPageOut:
    page = await service.store_products(
        category_slug=category,
        scale_code=scale,
        epoch_code=epoch,
        text=q,
        order=_STORE_ORDERS[sort],
        cursor=cursor,
        limit=limit,
    )
    references = await service.references()
    response.headers["Cache-Control"] = STORE_CACHE_CONTROL
    return StoreProductPageOut.from_page(page, scale_order=[s.code for s in references.scales])


@router.get(
    "/products/{slug}",
    operation_id="getStoreProduct",
    summary="A product page: scales, finishes, prices, gallery",
    responses=problems({404: ["product_not_found"]}, unsafe=False),
)
async def get_product(slug: str, response: Response, service: CatalogServiceDep) -> StoreProductOut:
    found = await service.store_product(slug)
    response.headers["Cache-Control"] = STORE_CACHE_CONTROL
    return StoreProductOut.from_store_product(found)
