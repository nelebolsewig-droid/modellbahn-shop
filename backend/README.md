# Backend des Modellbahn-Shops

Modularer Monolith in Python 3.13: FastAPI für die API, ein Worker für die Outbox und die
Bild-Pipeline, PostgreSQL als Datenbank und Warteschlange, ein S3-Objektspeicher für Medien. Das Gesamtbild steht in
[`docs/KONZEPT.md`](../docs/KONZEPT.md); dieses Dokument beschreibt die Arbeit am Backend.

## Schnellstart

```bash
uv sync                                    # Abhängigkeiten inkl. Entwicklungswerkzeuge
make dev-db                                # im Projektwurzelverzeichnis: PostgreSQL + Mailpit
export MB_DATABASE_URL=postgresql+asyncpg://modellbahn:modellbahn@localhost:5432/modellbahn  # = Voreinstellung
export MB_COOKIE_SECURE=false              # nur für http://localhost ohne Caddy
uv run alembic upgrade head                # Schema anlegen
uv run uvicorn modellbahn.main:app --reload
uv run python -m modellbahn.worker         # zweites Terminal: Outbox-Worker (Mails, Live-Ereignisse)
```

Der Objektspeicher läuft nur im Compose-Stack. Ohne ihn funktionieren alle Routen außer dem
Hochladen und Verarbeiten von Fotos; die Tests des S3-Adapters starten Garage selbst.

Die API-Dokumentation liegt dann unter <http://localhost:8000/api/v1/docs> (nicht in Produktion).

## Befehle

| Zweck | Befehl |
| --- | --- |
| Tests mit Abdeckung | `uv run pytest` |
| Linter | `uv run ruff check` |
| Formatprüfung | `uv run ruff format --check` |
| Typprüfung (strict) | `uv run mypy` |
| Architekturregeln | `uv run lint-imports` |
| Mitarbeiterkonto anlegen | `uv run python -m modellbahn.cli create-staff --email … --name … --role owner` |
| Objektspeicher einrichten (Garage, idempotent) | `uv run python -m modellbahn.cli init-storage` mit `GARAGE_ADMIN_URL` und `GARAGE_ADMIN_TOKEN` |
| OpenAPI-Schema exportieren | `uv run python -m modellbahn.cli export-openapi` (schreibt `../frontend/openapi.json`) |

`create-staff` fragt das Passwort zweimal verdeckt ab; mit `--password-stdin` liest es
das Passwort von der Standardeingabe.

Die Tests laufen gegen ein echtes PostgreSQL. Ist `TEST_DATABASE_URL` gesetzt, wird dieser
Server benutzt (so in der CI), sonst startet Testcontainers einen Container mit dem Image aus
`TEST_POSTGRES_IMAGE` (Standard `postgres:17-alpine`). Jeder Testlauf legt eine eigene
Datenbank an und migriert sie einmal. Die Tests des S3-Adapters und von `init-storage`
starten einen Garage-Container; alle anderen nutzen einen Speicher im Arbeitsspeicher.

## Aufbau

```
src/modellbahn/
├── main.py         API-Anwendung (create_app), Kompositionswurzel
├── worker.py       Outbox-Worker und periodische Jobs bis SIGTERM
├── cli.py          create-staff, unlock-staff, init-storage, export-openapi
├── platform/       gemeinsamer Kern ohne Fachlogik: Konfiguration, IDs, Uhr, Datenbank,
│                   Ereignisse, Unit of Work, Outbox, Echtzeit (SSE), Fehler, Sicherheit,
│                   Mail, Logging, Health-Checks
└── modules/
    ├── identity/   Konten, Sitzungen, E-Mail-Bestätigung, Passwörter
    │   ├── domain/          reines Python: Modell, Ereignisse, Fehler
    │   ├── application/     Anwendungsfälle, Ports, Outbox-Handler, Mailtexte
    │   ├── infrastructure/  Tabellen, imperatives Mapping, Repositories
    │   ├── api/             Router, Schemas, Abhängigkeiten
    │   └── contracts/       das Einzige, was andere Module importieren dürfen
    ├── media/      Uploads, Bildverarbeitung (Pillow), S3-Adapter, Garage-Einrichtung
    ├── catalog/    Produkte, Spurweiten, Varianten, Kategorien, Galerie; Shop-Abfragen
    └── sales/      Warenkorb, Bestellungen, Zahlung (Port mit Mock-Adapter), Adressbuch,
                    Bestell-E-Mails
migrations/         Alembic, von Hand geschrieben (kein Autogenerate)
tests/              unit/, integration/, api/, architecture/
```

## Architekturregeln

`lint-imports` prüft sie bei jedem Lauf (Konfiguration in `pyproject.toml`), und
`tests/architecture/` stellt sicher, dass die Regeln auch für künftige Module greifen:

1. In jedem Modul gilt `api → application → domain`; `infrastructure` darf `application` und
   `domain` nutzen. `api` und `infrastructure` kennen einander nicht, die Domäne kennt keine
   der anderen Schichten.
2. Ein Modul nutzt ein anderes nur über dessen `contracts`.
3. `modellbahn.platform` importiert keine Module.
4. Eine Domäne importiert weder FastAPI noch SQLAlchemy, Pydantic oder Starlette, auch nicht
   auf Umwegen.

Jedes Modul ist ein echtes Paket mit `__init__.py`; ohne diese Datei sähe import-linter
das Modul nicht, und die Regeln wären stillschweigend wirkungslos.

## Wichtige Abläufe

- **Outbox:** Ein Anwendungsfall schreibt Zustand und Ereignisse in *einer* Transaktion
  (`platform.uow`). Der Worker holt Ereignisse mit `FOR UPDATE SKIP LOCKED`, wird per
  `NOTIFY mb_outbox` geweckt, wiederholt Fehlschläge mit wachsendem Abstand (30 s bis 1 h)
  und markiert ein Ereignis nach `MB_OUTBOX_MAX_ATTEMPTS` Versuchen als `dead`. Handler
  werden mindestens einmal ausgeführt und müssen daher idempotent sein.
- **Echtzeit:** Ereignisse mit Publikum (z. B. `staff`) schickt der Worker per
  `NOTIFY mb_events` an alle API-Prozesse; diese reichen sie als Server-Sent Events unter
  `GET /api/v1/admin/events` weiter. Mit `Last-Event-ID` werden verpasste Ereignisse aus
  der Outbox nachgeliefert.
- **Medien:** Der Browser holt sich ein Upload-Ticket (`POST /admin/media/uploads`), lädt
  die Datei per signierter URL direkt in den privaten Bucket und schließt ab. Das Ereignis
  `media.asset.uploaded` startet im Worker die Verarbeitung: EXIF-Drehung, Metadaten weg,
  sRGB, sechs Größen in WebP und AVIF, Platzhalter, Dominanzfarbe, Hash. Die Stufen liegen
  unter inhaltsadressierten Namen im öffentlichen Bucket; `media.asset.ready` erreicht das
  Stellwerk per SSE. Einzelheiten: ADR 0008.
- **Katalog:** Das Produkt ist das Aggregat; Spurweiten, Varianten, Epochen und Galerie
  ändern sich nur über seine Methoden. Jede Änderung erhöht `version`; `GET` liefert sie als
  `ETag`, `PATCH` und `PUT …/media` verlangen sie als `If-Match` (fehlt: 428, veraltet: 412).
  Veröffentlichen prüft die Regeln (Kategorie, aktive Variante, fertiges Hauptbild); dieselben
  Regeln gelten weiter, solange das Produkt im Shop steht.
- **Verkauf:** Der Warenkorb liegt auf dem Server, das HttpOnly-Cookie `mb_cart` benennt
  ihn. Preise und Kaufbarkeit holt der Verkauf über den Katalog-Vertrag
  `load_sale_variants`; der Browser schickt nur die angezeigte Summe mit (anders: 409
  `price_changed`). Checkout und Zahlung verlangen `Idempotency-Key`; dieselbe Anfrage noch
  einmal liefert das erste Ergebnis (`Idempotent-Replayed: true`), eine andere mit demselben
  Schlüssel 409. Die Zahlung läuft über den Port `PaymentGateway`, heute
  `MockPaymentGateway` mit wählbarem Ausgang. Die Ereignisse `sales.order.*` lösen im Worker
  die E-Mails aus und erreichen das Stellwerk per SSE; `identity.account.email_verified`
  übernimmt Gastbestellungen ins Konto. Periodische Jobs stornieren unbezahlte Bestellungen
  nach 24 Stunden (alle 15 Minuten) und löschen abgelaufene Warenkörbe (alle 6 Stunden).
  Einzelheiten: ADR 0009.
- **Fehler:** Jede Fehlerantwort ist `application/problem+json` (RFC 9457) mit einem
  stabilen `code`, den das Frontend übersetzt.
- **CSRF:** Zustandsändernde Anfragen unter `/api/` brauchen den Header
  `X-Modellbahn-Client: web` und, mit Rumpf, `Content-Type: application/json`.

## Konfiguration

Alle Einstellungen kommen aus Umgebungsvariablen mit dem Präfix `MB_`
(`platform/config.py`, dokumentiert in `../.env.example`). In Produktion
(`MB_ENVIRONMENT=production`) verweigert der Start `MB_COOKIE_SECURE=false` und den
S3-Entwicklungsschlüssel aus `.env.example`.
