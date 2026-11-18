#!/usr/bin/env python3
"""Alte Shopify-Produktadressen den Produkten im neuen Shop zuordnen (ADR 0036).

Shopify nennt ein Produkt unter ``/products/<handle>``, der neue Shop unter
``/produkte/<slug>``. Heißt der Slug wie der Handle, leitet der Shop von selbst weiter.
Für alle anderen braucht er einen Eintrag in ``frontend/src/lib/site/shopify-produkte.json``
(Handle → Slug). Dieses Skript schreibt die Datei aus dem Produkt-Export von Shopify
(Shopify-Admin → Produkte → Exportieren → „Alle Produkte“, CSV für Excel oder einfach CSV).

Zugeordnet wird so, in dieser Reihenfolge:

1. **gleich:** Der Handle ist ein Slug im Shop. Kein Eintrag nötig.
2. **Name:** Der Shopify-Titel ergibt denselben Slug wie ein Produkt im Shop.
3. **ähnlich:** Handle oder Titel gleichen einem Slug zu mindestens ``--schwelle``
   (Standard 0,8). Diese Zeilen bitte prüfen; mit ``--nur-sicher`` bleiben sie weg.

Was übrig bleibt, landet auf der Katalogsuche mit den Wörtern des Handles (302, nicht
dauerhaft) und wird am Ende aufgelistet: Diese Einträge von Hand in die JSON-Datei
schreiben oder das Produkt im Stellwerk veröffentlichen und das Skript neu starten.

Der Shop wird über seine öffentliche Schnittstelle gefragt; es zählen nur Produkte, die
im Shop stehen. Vorhandene Einträge der JSON-Datei bleiben erhalten (von Hand ergänzte
auch), außer mit ``--neu``.

Aufruf im Repository (nur Python 3, keine weiteren Pakete)::

    python3 scripts/shopify_weiterleitungen.py products_export.csv
    python3 scripts/shopify_weiterleitungen.py products_export.csv --schreiben

Ohne ``--schreiben`` ist es ein Probelauf, der nur zeigt, was er eintragen würde.
"""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ZIEL = Path(__file__).resolve().parent.parent / "frontend/src/lib/site/shopify-produkte.json"
SLUG_MAX = 80
_UMLAUTE = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}
)


def slugify(text: str) -> str:
    """Wie der Shop (catalog/domain/text.py): „Kran EDK 6 (H0)“ → „kran-edk-6-h0“."""
    text = unicodedata.normalize("NFKD", text.translate(_UMLAUTE))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:SLUG_MAX].rstrip("-")


@dataclass(frozen=True)
class Altprodukt:
    handle: str
    titel: str


def lies_export(pfad: Path) -> list[Altprodukt]:
    """Je Handle eine Zeile; Shopify wiederholt den Handle für jede Variante und jedes Bild."""
    gesehen: dict[str, str] = {}
    with pfad.open(encoding="utf-8-sig", newline="") as datei:
        for zeile in csv.DictReader(datei):
            handle = (zeile.get("Handle") or "").strip().lower()
            titel = (zeile.get("Title") or zeile.get("Titel") or "").strip()
            if handle and (handle not in gesehen or not gesehen[handle]):
                gesehen[handle] = titel
    if not gesehen:
        sys.exit(f"{pfad}: keine Spalte „Handle“ gefunden. Ist das der Produkt-Export von Shopify?")
    return [Altprodukt(h, t) for h, t in sorted(gesehen.items())]


def shop_slugs(shop: str) -> set[str]:
    """Alle Slugs der Produkte im Shop, Seite für Seite."""
    slugs: set[str] = set()
    cursor: str | None = None
    for _ in range(200):
        query = {"limit": "48", "sort": "name"} | ({"cursor": cursor} if cursor else {})
        url = f"{shop.rstrip('/')}/api/v1/store/products?{urllib.parse.urlencode(query)}"
        anfrage = urllib.request.Request(url, headers={"Accept": "application/json"})  # noqa: S310
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:  # noqa: S310
            seite = json.load(antwort)
        slugs.update(item["slug"] for item in seite["items"])
        cursor = seite.get("next_cursor")
        if not cursor:
            break
    return slugs


@dataclass(frozen=True)
class Zuordnung:
    handle: str
    slug: str | None
    art: str  # gleich, Name, ähnlich, offen
    guete: float = 1.0


def ordne_zu(alt: Altprodukt, slugs: set[str], schwelle: float) -> Zuordnung:
    if alt.handle in slugs:
        return Zuordnung(alt.handle, alt.handle, "gleich")
    aus_titel = slugify(alt.titel) if alt.titel else ""
    if aus_titel in slugs:
        return Zuordnung(alt.handle, aus_titel, "Name")
    best: tuple[float, str] | None = None
    for kandidat in slugs:
        guete = max(
            difflib.SequenceMatcher(None, alt.handle, kandidat).ratio(),
            difflib.SequenceMatcher(None, aus_titel, kandidat).ratio() if aus_titel else 0.0,
        )
        if best is None or guete > best[0]:
            best = (guete, kandidat)
    if best is not None and best[0] >= schwelle:
        return Zuordnung(alt.handle, best[1], "ähnlich", best[0])
    return Zuordnung(alt.handle, None, "offen")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("export", type=Path, help="Produkt-Export von Shopify (CSV)")
    parser.add_argument(
        "--shop", default="https://neu.adp-modelle.de", help="Adresse des neuen Shops"
    )
    parser.add_argument(
        "--schwelle", type=float, default=0.8, help="Mindestgüte für „ähnlich“ (0 bis 1)"
    )
    parser.add_argument(
        "--nur-sicher", action="store_true", help="ähnliche Treffer nicht eintragen"
    )
    parser.add_argument("--neu", action="store_true", help="vorhandene Einträge verwerfen")
    parser.add_argument("--schreiben", action="store_true", help="Datei wirklich schreiben")
    parser.add_argument("--ziel", type=Path, default=ZIEL, help=argparse.SUPPRESS)
    args = parser.parse_args()

    alte = lies_export(args.export)
    slugs = shop_slugs(args.shop)
    print(f"{len(alte)} Shopify-Produkte, {len(slugs)} Produkte im Shop ({args.shop}).\n")

    eintraege: dict[str, str] = (
        {} if args.neu or not args.ziel.exists() else json.loads(args.ziel.read_text())
    )
    offen: list[Altprodukt] = []
    for alt in alte:
        z = ordne_zu(alt, slugs, args.schwelle)
        if z.art == "offen":
            if alt.handle not in eintraege:
                offen.append(alt)
            continue
        if z.art == "gleich":
            eintraege.pop(alt.handle, None)
            continue
        if z.art == "ähnlich" and args.nur_sicher:
            offen.append(alt)
            continue
        hinweis = f"  (ähnlich {z.guete:.0%}, bitte prüfen)" if z.art == "ähnlich" else ""
        print(f"  /products/{alt.handle}  →  /produkte/{z.slug}{hinweis}")
        eintraege[alt.handle] = z.slug  # type: ignore[assignment]

    if offen:
        print(f"\nOhne Ziel ({len(offen)}), landen auf der Katalogsuche:")
        for alt in offen:
            print(f"  /products/{alt.handle}  „{alt.titel}“")

    inhalt = json.dumps(dict(sorted(eintraege.items())), ensure_ascii=False, indent=2) + "\n"
    if args.schreiben:
        args.ziel.write_text(inhalt, encoding="utf-8")
        print(f"\n{len(eintraege)} Einträge in {args.ziel} geschrieben. Committen, ausrollen.")
    else:
        print(f"\nProbelauf: {len(eintraege)} Einträge, mit --schreiben in {args.ziel.name}.")


if __name__ == "__main__":
    main()
