#!/usr/bin/env python3
"""Fotos aus einem Ordner automatisch ins Stellwerk laden, nach einer Übersichtsliste.

Die Liste ist eine CSV mit Semikolon, wie sie Claude beim Durchsehen der Fotos schreibt
(``modelle-uebersicht.csv``), mit den Spalten::

    Datei; Modell; Entwurf im Startbestand; Maßstab; Farbe; Ausführung; Zustand; Eignung;
    Hauptbild (ja/nein); Bemerkung

Je Modell kommen das Hauptbild und die übrigen Fotos mit Eignung „gut“ oder „brauchbar“
in die Galerie des gleichnamigen Produkts, höchstens ``--max-fotos`` Stück. Fotos mit
„nein“ bleiben draußen. Das Produkt muss im Stellwerk schon stehen (Startbestand oder
Schnellerfassung); das Skript legt keine Produkte an und veröffentlicht nichts.

Ohne ``--hochladen`` ist es ein Probelauf: Es meldet sich an, ordnet zu und zeigt, was
es tun würde. Mehrfach starten ist unschädlich: Dasselbe Foto erkennt der Server an
seiner Prüfsumme, und ein Bild, das schon in der Galerie ist, kommt nicht doppelt hinein.

Aufruf im Ordner mit der CSV (nur Python 3, keine weiteren Pakete)::

    python3 fotos_hochladen.py modelle-uebersicht.csv --email du@example.de
    python3 fotos_hochladen.py modelle-uebersicht.csv --email du@example.de --hochladen

Das Passwort fragt das Skript verdeckt ab (oder liest ``MB_STELLWERK_PASSWORT``).
"""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import http.cookiejar
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

DEFAULT_SERVER: Final = "https://neu.adp-modelle.de"
API: Final = "/api/v1/admin"
CLIENT_HEADER: Final = "X-Modellbahn-Client"
HTTP_TIMEOUT: Final = 120
HTTP_ERROR: Final = 400
HTTP_REDIRECT: Final = 300
# Limits of the server (media and catalog modules).
IMAGE_MAX_BYTES: Final = 50 * 1024 * 1024
GALLERY_MAX_SIZE: Final = 40
ALT_TEXT_MAX_LENGTH: Final = 250
MIME_TYPES: Final = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".heic": "image/heic",
    ".heif": "image/heif",
}
NEW_MARKERS: Final = {"", "neu", "-", "\u2013"}
SUITABILITY_RANK: Final = {"gut": 0, "brauchbar": 1}


def photos_text(count: int) -> str:
    return f"{count} Foto" if count == 1 else f"{count} Fotos"


class ListError(ValueError):
    """The overview cannot be read as it is; nothing was uploaded."""


@dataclass(frozen=True, slots=True)
class Photo:
    path: Path
    model: str
    target: str
    color: str
    suitability: str
    main: bool

    @property
    def alt_text(self) -> str:
        text = f"{self.model}, {self.color}" if self.color else self.model
        return text[:ALT_TEXT_MAX_LENGTH]


@dataclass(slots=True)
class Plan:
    """What goes where; built from the overview alone, before any request."""

    galleries: dict[str, list[Photo]] = field(default_factory=dict)
    unsuitable: list[Photo] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    over_limit: dict[str, int] = field(default_factory=dict)


def normalized(name: str) -> str:
    """Names compared the way people mean them: case, quotes and spaces aside."""
    text = re.sub(r"[\u201e\u201c\u201d\u201f\"'\u00ab\u00bb\u201a\u2018\u2019]", '"', name)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _column(row: Mapping[str, str | None], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None:
            return value.strip()
    return ""


def _suitability(value: str) -> str:
    """The first word of the rating: „gut“, „brauchbar“ or „nein“ (with or without reason)."""
    word = re.split(r"[\s,;:(/\u2013-]+", value.strip().casefold(), maxsplit=1)[0]
    return word if word in {"gut", "brauchbar", "nein"} else ""


def _resolve(base: Path, name: str) -> Path | None:
    for candidate in (base / name, base / "Modelle" / name):
        if candidate.is_file():
            return candidate
    return None


def read_overview(csv_path: Path) -> tuple[list[Photo], list[str]]:
    """The photos of the overview, and the file names it lists that do not exist."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if reader.fieldnames is None:
            raise ListError(f"{csv_path.name} ist leer")
        reader.fieldnames = [name.strip() for name in reader.fieldnames]
        for required in ("Datei", "Modell", "Eignung"):
            if required not in reader.fieldnames:
                raise ListError(f"{csv_path.name}: Spalte „{required}“ fehlt")
        photos, missing = [], []
        for row in reader:
            name = _column(row, "Datei")
            if not name:
                continue
            path = _resolve(csv_path.parent, name)
            if path is None:
                missing.append(name)
                continue
            model = _column(row, "Modell")
            draft = _column(row, "Entwurf im Startbestand")
            target = model if draft.casefold() in NEW_MARKERS else draft
            if not target:
                continue
            photos.append(
                Photo(
                    path=path,
                    model=model or target,
                    target=target,
                    color=_column(row, "Farbe"),
                    suitability=_suitability(_column(row, "Eignung")),
                    main=_column(row, "Hauptbild (ja/nein)", "Hauptbild")
                    .casefold()
                    .startswith("j"),
                )
            )
    return photos, missing


def make_plan(photos: Iterable[Photo], missing: list[str], *, max_photos: int) -> Plan:
    """Per product: the main photo first, then the good ones, then the usable ones."""
    plan = Plan(missing_files=list(missing))
    seen: set[Path] = set()
    grouped: dict[str, list[Photo]] = {}
    for photo in photos:
        if photo.path in seen:
            continue
        seen.add(photo.path)
        if photo.suitability not in SUITABILITY_RANK and not photo.main:
            plan.unsuitable.append(photo)
            continue
        grouped.setdefault(photo.target, []).append(photo)
    limit = min(max_photos, GALLERY_MAX_SIZE)
    for target, group in grouped.items():
        ordered = sorted(
            group, key=lambda p: (not p.main, SUITABILITY_RANK.get(p.suitability, 2), p.path.name)
        )
        plan.galleries[target] = ordered[:limit]
        if len(ordered) > limit:
            plan.over_limit[target] = len(ordered) - limit
    return plan


class StellwerkError(RuntimeError):
    """The server refused a request; the message says which and why."""


class Stellwerk:
    """The admin API as the Stellwerk in the browser uses it: session cookie, CSRF header."""

    def __init__(self, base_url: str, *, ca_file: str | None = None) -> None:
        if not base_url.startswith("https://"):
            raise StellwerkError(f"{base_url}: nur https-Adressen")
        self.base_url = base_url.rstrip("/")
        context = ssl.create_default_context(cafile=ca_file)
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=context),
        )

    def _send(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, bytes]:
        # https only: the base URL is checked in __init__, upload URLs must start with it.
        request = urllib.request.Request(  # noqa: S310
            url, data=data, method=method, headers=dict(headers or {})
        )
        try:
            with self._opener.open(request, timeout=HTTP_TIMEOUT) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, error.read()
        except urllib.error.URLError as error:
            raise StellwerkError(f"Keine Verbindung zu {url}: {error.reason}") from None

    def call(self, method: str, path: str, body: Mapping[str, object] | None = None) -> Any:
        headers = {"Accept": "application/json"}
        if method != "GET":
            headers[CLIENT_HEADER] = "web"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        status, raw = self._send(method, self.base_url + path, data=data, headers=headers)
        if status >= HTTP_ERROR:
            try:
                problem = json.loads(raw)
                detail = problem.get("detail") or problem.get("title") or ""
                code = problem.get("code", "")
            except ValueError:
                detail, code = raw[:200].decode(errors="replace"), ""
            raise StellwerkError(f"{method} {path}: HTTP {status} {code} {detail}".strip())
        return json.loads(raw) if raw else None

    def login(self, email: str, password: str) -> None:
        self.call("POST", f"{API}/auth/session", {"email": email, "password": password})

    def products(self) -> dict[str, dict[str, Any]]:
        """Every product of the catalogue by normalized name."""
        found: dict[str, dict[str, Any]] = {}
        cursor: str | None = None
        while True:
            query = {"limit": "100"} | ({"cursor": cursor} if cursor else {})
            page = self.call("GET", f"{API}/products?{urllib.parse.urlencode(query)}")
            for item in page["items"]:
                found.setdefault(normalized(item["name"]), item)
            cursor = page.get("next_cursor")
            if not cursor:
                return found

    def gallery_size(self, product_id: str) -> int:
        return len(self.call("GET", f"{API}/products/{product_id}")["media"])

    def upload(self, photo: Photo) -> str:
        """The photo as a stored asset; a file the server already has is not sent again."""
        data = photo.path.read_bytes()
        ticket = self.call(
            "POST",
            f"{API}/media/uploads",
            {
                "filename": photo.path.name,
                "mime_type": MIME_TYPES[photo.path.suffix.lower()],
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
        asset_id: str = ticket["asset"]["id"]
        upload = ticket.get("upload")
        if upload is None:
            return asset_id
        if not upload["url"].startswith(self.base_url + "/"):
            raise StellwerkError(f"Upload-Adresse zeigt nicht auf {self.base_url}")
        status, raw = self._send("PUT", upload["url"], data=data, headers=upload["headers"])
        if status >= HTTP_REDIRECT:
            raise StellwerkError(f"Hochladen von {photo.path.name}: HTTP {status} {raw[:200]!r}")
        self.call("POST", f"{API}/media/{asset_id}/complete")
        return asset_id

    def attach(self, product_id: str, asset_id: str, alt_text: str) -> None:
        self.call(
            "POST",
            f"{API}/products/{product_id}/media",
            {"asset_id": asset_id, "alt_text": alt_text},
        )


def _check_files(plan: Plan) -> list[str]:
    problems = []
    for photos in plan.galleries.values():
        for photo in photos:
            if photo.path.suffix.lower() not in MIME_TYPES:
                problems.append(f"{photo.path.name}: Dateityp {photo.path.suffix} geht nicht")
            elif photo.path.stat().st_size > IMAGE_MAX_BYTES:
                problems.append(f"{photo.path.name}: größer als 50 MB")
    return problems


def _report(
    plan: Plan, absent: list[str], args: argparse.Namespace, *, uploaded: int, failed: int
) -> None:
    if absent:
        print(f"\nNicht im Stellwerk, erst anlegen oder Startbestand einspielen ({len(absent)}):")
        for target in absent:
            print(f"  - {target} ({photos_text(len(plan.galleries[target]))})")
    if plan.over_limit:
        print(f"\nMehr als {args.max_fotos} geeignete Fotos, der Rest bleibt draußen:")
        for target, extra in sorted(plan.over_limit.items()):
            print(f"  - {target}: {extra} weitere")
    if plan.unsuitable:
        print(f"\nAls ungeeignet bewertet, nicht hochgeladen: {photos_text(len(plan.unsuitable))}")
    if plan.missing_files:
        print(f"\nIn der Liste, aber nicht im Ordner ({len(plan.missing_files)}):")
        for name in plan.missing_files[:20]:
            print(f"  - {name}")
    if args.hochladen:
        print(f"\nNeu in den Galerien: {photos_text(uploaded)}. Fehlgeschlagen: {failed} Modelle.")
    else:
        print("\nNichts hochgeladen. Mit --hochladen geht es los.")


def run(args: argparse.Namespace) -> int:
    csv_path = Path(args.liste).expanduser()
    photos, missing = read_overview(csv_path)
    plan = make_plan(photos, missing, max_photos=args.max_fotos)
    problems = _check_files(plan)
    if problems:
        print("Diese Fotos lassen sich nicht hochladen:", *problems, sep="\n  ")
        return 1

    password = os.environ.get("MB_STELLWERK_PASSWORT") or getpass.getpass(
        "Passwort fürs Stellwerk: "
    )
    stellwerk = Stellwerk(args.server, ca_file=args.ca_datei)
    stellwerk.login(args.email, password)
    catalogue = stellwerk.products()

    found = {t: catalogue[normalized(t)] for t in plan.galleries if normalized(t) in catalogue}
    absent = sorted(t for t in plan.galleries if t not in found)
    count = sum(len(plan.galleries[t]) for t in found)
    print(f"{'Hochladen' if args.hochladen else 'Probelauf'}: {args.server}")
    print(f"{len(found)} Modelle im Stellwerk gefunden, {photos_text(count)} dafür.\n")

    uploaded = failed = 0
    for target in sorted(found):
        product = found[target]
        gallery = plan.galleries[target]
        line = (
            f"MB-{product['number']:06d} {product['name']}: "
            f"{photos_text(len(gallery))}, Hauptbild {gallery[0].path.name}"
        )
        if not args.hochladen:
            print(f"  {line}")
            continue
        try:
            before = stellwerk.gallery_size(product["id"])
            for photo in gallery:
                stellwerk.attach(product["id"], stellwerk.upload(photo), photo.alt_text)
            added = stellwerk.gallery_size(product["id"]) - before
        except (StellwerkError, OSError) as error:
            failed += 1
            print(f"  ✗ {line}\n    {error}")
            continue
        uploaded += added
        if added == 0:
            print(f"  = {line}: schon alle in der Galerie")
        elif before:
            print(f"  ✓ {line}: {added} neu, Reihenfolge der Galerie im Stellwerk prüfen")
        else:
            print(f"  ✓ {line}")

    _report(plan, absent, args, uploaded=uploaded, failed=failed)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("liste", help="die Übersicht, z. B. modelle-uebersicht.csv")
    parser.add_argument("--email", required=True, help="Anmeldung fürs Stellwerk")
    parser.add_argument("--server", default=DEFAULT_SERVER, help=f"Standard: {DEFAULT_SERVER}")
    parser.add_argument(
        "--hochladen", action="store_true", help="wirklich hochladen (sonst Probelauf)"
    )
    parser.add_argument(
        "--max-fotos", type=int, default=8, help="höchstens so viele Fotos je Modell"
    )
    parser.add_argument("--ca-datei", default=None, help=argparse.SUPPRESS)  # local test stack only
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (ListError, StellwerkError) as error:
        print(f"Abgebrochen: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
