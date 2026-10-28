"""The starting catalogue from a file: categories, and products as drafts to complete.

A seed lists categories (with children) and products with their scales and variants;
a product without variants is a draft that still needs a price, say. Importing goes
through the catalogue service, product by product, and can run again after the file
grew: a category with the same name under the same parent and a product with the
same address (slug) are left alone.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Final

from modellbahn.modules.catalog.application.services import CatalogService
from modellbahn.modules.catalog.domain.model import Category, Dimensions
from modellbahn.modules.catalog.domain.text import slugify

PATH_SEPARATOR: Final = " / "


@dataclass(frozen=True, slots=True)
class VariantSeed:
    finish_code: str
    price_cents: int
    color: str = ""


@dataclass(frozen=True, slots=True)
class ScaleSeed:
    scale_code: str
    variants: Sequence[VariantSeed] = ()


@dataclass(frozen=True, slots=True)
class ProductSeed:
    name: str
    category: str
    """The category's path from the top, e.g. ``Lkw / Kipper``."""
    summary: str = ""
    description: str = ""
    prototype: str = ""
    scales: Sequence[ScaleSeed] = ()
    note: str = ""
    """For the person importing, never stored: "laut Shopify 2 Stück", "Preis fehlt"."""


@dataclass(frozen=True, slots=True)
class CategorySeed:
    name: str
    children: Sequence["CategorySeed"] = ()


@dataclass(frozen=True, slots=True)
class CatalogSeed:
    categories: Sequence[CategorySeed]
    products: Sequence[ProductSeed]


@dataclass(slots=True)
class ImportReport:
    categories: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[tuple[str, str]] = field(default_factory=list)


class SeedError(ValueError):
    """The seed names a category or scale that does not exist; nothing was written."""


async def import_catalog(service: CatalogService, seed: CatalogSeed) -> ImportReport:
    """Create what the seed lists and the catalogue lacks; report what was done."""
    await _check(service, seed)
    report = ImportReport()
    paths = await _categories(service, seed.categories, report)
    for product in seed.products:
        category = paths[product.category]
        if await service.find_product(slugify(product.name)) is not None:
            report.skipped.append(product.name)
            continue
        details = await service.create_product(name=product.name)
        product_id = details.product.id
        await service.change_product(
            product_id,
            expected_version=None,
            summary=product.summary,
            description=product.description,
            prototype=product.prototype,
            primary_category_id=category.id,
        )
        for scale in product.scales:
            details = await service.add_scale(
                product_id,
                expected_version=None,
                scale_code=scale.scale_code,
                dimensions=Dimensions(),
            )
            product_scale = next(
                s for s in details.product.scales if s.scale_code == scale.scale_code
            )
            for variant in scale.variants:
                await service.add_variant(
                    product_scale.id,
                    expected_version=None,
                    finish_code=variant.finish_code,
                    color=variant.color,
                    price_cents=variant.price_cents,
                )
        report.products.append(product.name)
        if product.note:
            report.notes.append((product.name, product.note))
    return report


async def _check(service: CatalogService, seed: CatalogSeed) -> None:
    """Every category path and scale code the products name, before anything is written."""
    paths = set(_paths(seed.categories, ""))
    scales = {s.code for s in (await service.references()).scales}
    problems = [
        f"{product.name}: unknown category {product.category!r}"
        for product in seed.products
        if product.category not in paths
    ] + [
        f"{product.name}: unknown scale {scale.scale_code!r}"
        for product in seed.products
        for scale in product.scales
        if scale.scale_code not in scales
    ]
    if problems:
        raise SeedError("; ".join(problems))


def _paths(nodes: Sequence[CategorySeed], prefix: str) -> Iterator[str]:
    for node in nodes:
        path = f"{prefix}{node.name}"
        yield path
        yield from _paths(node.children, f"{path}{PATH_SEPARATOR}")


async def _categories(
    service: CatalogService, seeds: Sequence[CategorySeed], report: ImportReport
) -> dict[str, Category]:
    """Every category of the seed by its path, created where the catalogue lacks it."""
    existing = await service.list_categories()
    paths: dict[str, Category] = {}

    async def walk(nodes: Sequence[CategorySeed], parent: Category | None, prefix: str) -> None:
        for position, node in enumerate(nodes):
            path = f"{prefix}{node.name}"
            found = next(
                (
                    c
                    for c in existing
                    if c.parent_id == (parent.id if parent else None)
                    and c.name.casefold() == node.name.casefold()
                ),
                None,
            )
            if found is None:
                found = await service.create_category(
                    name=node.name,
                    parent_id=parent.id if parent else None,
                    position=position,
                )
                existing.append(found)
                report.categories.append(path)
            paths[path] = found
            await walk(node.children, found, f"{path}{PATH_SEPARATOR}")

    await walk(seeds, None, "")
    return paths
