"""The format of a catalogue seed file, such as ``backend/seed/startbestand.json``.

Strict: an unknown key or a finish that is no longer offered stops the import before
anything is written, with the place of the mistake in the message.
"""

from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from modellbahn.modules.catalog.application.importing import (
    CatalogSeed,
    CategorySeed,
    ProductSeed,
    ScaleSeed,
    VariantSeed,
)
from modellbahn.modules.catalog.domain.model import COLOR_MAX_LENGTH, PRICE_MAX_CENTS


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VariantEntry(_Strict):
    finish: Literal["unpainted", "painted"]
    color: str = Field(default="", max_length=COLOR_MAX_LENGTH)
    price_cents: int = Field(ge=0, le=PRICE_MAX_CENTS)


class ScaleEntry(_Strict):
    code: str
    variants: list[VariantEntry] = []


class ProductEntry(_Strict):
    name: str = Field(min_length=1)
    category: str = Field(description="Path from the top: 'Lkw / Kipper'.")
    summary: str = ""
    description: str = ""
    prototype: str = ""
    scales: list[ScaleEntry] = []
    note: str = ""


class CategoryEntry(_Strict):
    name: str = Field(min_length=1)
    children: list["CategoryEntry"] = []

    def to_seed(self) -> CategorySeed:
        return CategorySeed(name=self.name, children=[c.to_seed() for c in self.children])


class SeedFile(_Strict):
    about: str = ""
    categories: list[CategoryEntry]
    products: list[ProductEntry]

    @classmethod
    def read(cls, path: Path) -> Self:
        return cls.model_validate_json(path.read_bytes())

    def to_seed(self) -> CatalogSeed:
        return CatalogSeed(
            categories=[c.to_seed() for c in self.categories],
            products=[
                ProductSeed(
                    name=p.name,
                    category=p.category,
                    summary=p.summary,
                    description=p.description,
                    prototype=p.prototype,
                    scales=[
                        ScaleSeed(
                            scale_code=s.code,
                            variants=[
                                VariantSeed(
                                    finish_code=v.finish, price_cents=v.price_cents, color=v.color
                                )
                                for v in s.variants
                            ],
                        )
                        for s in p.scales
                    ],
                    note=p.note,
                )
                for p in self.products
            ],
        )
