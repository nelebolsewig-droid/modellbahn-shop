"""The article list as CSV, for Johann's till (SumUp) and for spreadsheets.

German conventions, so that Excel opens it with a double click: semicolons between
the fields, a comma in prices, UTF-8 with a byte order mark. One line per variant.
"""

import csv
import io
from collections.abc import Sequence
from typing import Final

from modellbahn.modules.catalog.application.ports import Article

VAT_PERCENT: Final = 19
COLUMNS: Final = (
    "Name",
    "Variante",
    "Artikelnummer",
    "EAN",
    "Preis",
    "MwSt",
    "Kategorie",
    "Verfügbarkeit",
    "Aktiv",
)


def _euros(cents: int) -> str:
    return f"{cents // 100},{cents % 100:02d}"


def _availability(article: Article) -> str:
    if not article.allow_backorder:
        return "vorrätig"
    if article.lead_time_weeks is None:  # pragma: no cover - the database requires one
        return "auf Bestellung"
    shortest, longest = article.lead_time_weeks
    weeks = f"{shortest}" if shortest == longest else f"{shortest}-{longest}"
    return f"auf Bestellung ({weeks} Wochen)"


def articles_csv(articles: Sequence[Article]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUMNS)
    for article in articles:
        writer.writerow(
            (
                article.product_name,
                f"{article.scale_name} · {article.finish_name}",
                article.sku,
                article.gtin,
                _euros(article.price_cents),
                VAT_PERCENT,
                article.category_name or "",
                _availability(article),
                "ja" if article.active else "nein",
            )
        )
    return buffer.getvalue().encode("utf-8-sig")
