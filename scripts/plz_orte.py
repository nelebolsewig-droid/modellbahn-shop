#!/usr/bin/env python3
"""Postleitzahl → Ort für die Kasse: frontend/public/plz/<zwei Ziffern>.json erzeugen.

Quelle sind die deutschen Postleitzahlen von GeoNames (CC BY 4.0, https://www.geonames.org),
etwa als CSV aus https://github.com/zauberware/postal-codes-json-xml-csv (data/DE.zip,
Spalten ``zipcode`` und ``place``). Ortsteile wie „Dresden Innere Altstadt“ fallen weg,
wenn der Ort selbst („Dresden“) unter derselben Postleitzahl steht: Auf das Paket gehört
der Ort. Je Datei die Postleitzahlen mit derselben ersten zwei Ziffern, damit die Kasse
nur ein paar Kilobyte lädt.

Aufruf::

    python3 scripts/plz_orte.py zipcodes.de.csv frontend/public/plz
"""

# ruff: noqa: T201

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


def towns(places: list[str]) -> list[str]:
    """The places of one postal code without the districts of a town that is also listed."""
    unique = list(dict.fromkeys(place.strip() for place in places if place.strip()))
    return [p for p in unique if not any(p != q and p.startswith(q + " ") for q in unique)]


def main(source: Path, target: Path) -> None:
    places: dict[str, list[str]] = defaultdict(list)
    with source.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            places[row["zipcode"].strip()].append(row["place"])
    chunks: dict[str, dict[str, list[str]]] = defaultdict(dict)
    for code in sorted(places):
        if len(code) == 5 and code.isdigit():
            chunks[code[:2]][code] = towns(places[code])
    target.mkdir(parents=True, exist_ok=True)
    for prefix, chunk in chunks.items():
        (target / f"{prefix}.json").write_text(
            json.dumps(chunk, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    print(f"{sum(len(c) for c in chunks.values())} Postleitzahlen in {len(chunks)} Dateien")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
