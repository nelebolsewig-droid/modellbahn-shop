# Modellbahn-Shop

Webshop und Werkstatt-Backend für 3D-gedruckte Modellbahn-Artikel. Gebaut als **modularer
Monolith**: ein Repository, ein Backend in Python (FastAPI) mit zwei Prozessen (API und
Worker), ein Frontend in Next.js, PostgreSQL als Datenbank und Warteschlange, Caddy als
HTTPS-Eingang. Das vollständige Architekturkonzept steht in [docs/KONZEPT.md](docs/KONZEPT.md),
die tragenden Entscheidungen in [docs/adr/](docs/adr/).

**Stand: Schritt 2 – Fundament.** Enthalten sind Plattform-Kern (Outbox, Unit of Work, IDs,
Fehlerformat, Echtzeit), das Modul *Identität* mit Kundenkonten und Mitarbeiterzugang sowie
Docker Compose, CI und Architekturregeln. Katalog, Medien und Bestellungen folgen ab Schritt 3.

Was sich vorführen lässt: Ein Besucher registriert sich, der Worker verschickt die
Bestätigungs-E-Mail (sichtbar in Mailpit), der Link bestätigt das Konto und meldet an, der
Kunde sieht „Mein Konto“. Ein Mitarbeiter sieht die Registrierung im Admin-Bereich
„Stellwerk“ live erscheinen, ohne die Seite neu zu laden. Passwort zurücksetzen, Passwort
ändern, Abmelden und Konto löschen funktionieren ebenfalls.

## Voraussetzungen

| Wofür | Was |
| --- | --- |
| Stack starten | Docker Engine mit Compose v2 (`docker compose`), GNU Make |
| Freie Ports | 80 und 443 (Caddy); nur auf 127.0.0.1: 5432 (PostgreSQL), 8025 und 1025 (Mailpit) |
| Entwicklung ohne Container, `make test`, `make check` | Python 3.13 und [uv](https://docs.astral.sh/uv/) 0.11, Node.js 22 mit npm 10 |
| `make smoke` | Python 3.13 (`python3`, nur Standardbibliothek) |

Die Backend-Tests starten PostgreSQL selbst per Testcontainers und brauchen dafür Docker.

## Schnellstart

```bash
make up                                                   # baut und startet alles
make staff EMAIL=chef@example.de NAME="Vorname Nachname"  # Mitarbeiterkonto, Rolle owner
make smoke                                                # spielt die Vorführung automatisch durch
```

`make up` legt beim ersten Aufruf `.env` aus `.env.example` an, baut die Images, wendet die
Migrationen an und wartet, bis alle Dienste gesund sind. `make staff` fragt das Passwort
verdeckt zweimal ab; mit `ROLE=staff` oder `ROLE=packer` entsteht ein Konto mit anderer Rolle.

`make smoke` prüft den laufenden Stack von außen, über Caddy und Mailpit, so wie ein Browser:
Startseite, Registrierung, Bestätigungs-E-Mail, Bestätigung mit Anmeldung, Abmelden, erneutes
Anmelden, Passwort zurücksetzen, Anmeldung im Stellwerk, Ereignisstrom (Nachlieferung per
`Last-Event-ID` und live) sowie die Grenzen zwischen Shop- und Admin-Sitzung und den
CSRF-Header. Jeder Schritt erscheint mit ✓ oder ✗; beim ersten Fehler endet der Lauf mit
Exit-Code 1. Für jeden Lauf legt das Ziel ein Wegwerf-Mitarbeiterkonto (Rolle `staff`) mit
Zufallspasswort an und prüft HTTPS gegen Caddys interne Zertifizierungsstelle. Das Skript
[`scripts/smoke_e2e.py`](scripts/smoke_e2e.py) braucht nur Python 3.13 ohne Zusatzpakete.

| Adresse | Was |
| --- | --- |
| <https://localhost> | Shop |
| <https://localhost/konto/registrieren> | Kundenkonto anlegen |
| <https://localhost/admin> | Admin-Bereich „Stellwerk“ (Anmeldung mit dem Konto aus `make staff`) |
| <http://localhost:8025> | Mailpit: hier landet jede E-Mail des Stacks |
| <https://localhost/healthz>, <https://localhost/readyz> | Lebenszeichen der API, Bereitschaft inkl. Datenbank |

**Zertifikatswarnung:** Für `localhost` stellt Caddy das Zertifikat aus seiner eigenen,
internen Zertifizierungsstelle aus. Der Browser kennt sie nicht und warnt beim ersten Aufruf;
für die lokale Entwicklung kann die Warnung bestätigt werden. Wer sie dauerhaft loswerden
will, exportiert das Wurzelzertifikat und importiert es im Browser oder Betriebssystem als
vertrauenswürdige Zertifizierungsstelle:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ~/modellbahn-caddy-root.crt
```

Die Zertifizierungsstelle liegt im Volume `caddy-data` und bleibt über Neustarts erhalten.

Stoppen mit `make down`; die Daten bleiben erhalten. Alles inklusive Datenbank und
Zertifikaten löschen: `docker compose down --volumes`.

## Make-Ziele

`make` ohne Ziel zeigt diese Übersicht.

| Ziel | Wirkung |
| --- | --- |
| `make up` | Stack bauen und starten: db, mailpit, migrate, api, worker, web, caddy |
| `make down` | Stack stoppen, Daten bleiben erhalten |
| `make logs` | Logs aller Dienste verfolgen; ein Dienst: `make logs SERVICE=worker` |
| `make dev-db` | Nur PostgreSQL und Mailpit starten, für die Entwicklung ohne Container |
| `make migrate` | Migrationen mit dem Backend-Image auf die Datenbank des Stacks anwenden |
| `make staff EMAIL=… NAME="…" [ROLE=owner\|staff\|packer]` | Mitarbeiterkonto anlegen |
| `make smoke` | End-to-End-Test gegen den laufenden Stack (siehe Schnellstart) |
| `make test` | Tests von Backend (pytest) und Frontend (Vitest) |
| `make lint` | Ruff, Formatprüfung, Architekturregeln (import-linter), ESLint |
| `make fmt` | Formatieren und automatisch behebbare Lint-Fehler beheben |
| `make typecheck` | `mypy --strict` und `tsc --noEmit` |
| `make openapi` | OpenAPI-Schema des Backends nach `frontend/openapi.json` exportieren |
| `make client` | Schema exportieren und den API-Client des Frontends neu erzeugen |
| `make check` | Alles, was die CI prüft, einschließlich Frontend-Build und Image-Build |

Die Qualitätsziele installieren die Frontend-Abhängigkeiten selbst (`npm ci`), sobald sich
`frontend/package-lock.json` geändert hat. uv synchronisiert das Backend bei jedem `uv run`.

## Entwicklung ohne Container

Für schnelles Arbeiten laufen Backend und Frontend direkt auf dem Rechner, nur Datenbank und
Mailpit im Container. Die Voreinstellungen des Backends passen dazu (Datenbank auf
`localhost:5432`, SMTP auf `localhost:1025`, Links auf `http://localhost:3000`).

```bash
make dev-db                                          # PostgreSQL und Mailpit
cd backend
uv run alembic upgrade head
uv run uvicorn modellbahn.main:app --reload          # API auf :8000
```

In zwei weiteren Terminals, jeweils vom Wurzelverzeichnis aus:

```bash
cd backend && uv run python -m modellbahn.worker     # Worker: verschickt die E-Mails
cd frontend && npm ci && npm run dev                 # Frontend auf http://localhost:3000
```

Im Entwicklungsmodus leitet Next.js `/api/*` an die API weiter, sodass Cookies auf demselben
Ursprung bleiben. Das Backend liest seine Einstellungen nur aus `MB_*`-Umgebungsvariablen,
nicht aus `.env`. Sitzungscookies sind standardmäßig `Secure`; Chrome und Firefox nehmen sie
auf `http://localhost` trotzdem an, Safari nicht. Dort hilft `MB_COOKIE_SECURE=false` (in
Produktion verweigert das Backend diese Einstellung).

Die Backend-Tests verwenden `TEST_DATABASE_URL`, wenn gesetzt, und starten sonst einen
PostgreSQL-Container (`TEST_POSTGRES_IMAGE`, Standard `postgres:17-alpine`).

## Repository

```text
modellbahn-shop/
├── Makefile                    Einstiegspunkte, siehe oben
├── docker-compose.yml          db, mailpit, migrate, api, worker, web, caddy
├── Caddyfile                   HTTPS; /api/* an die API, alles andere an Next.js
├── .env.example                jede Variable des Stacks mit Entwicklungswert
├── .github/workflows/ci.yml
├── scripts/smoke_e2e.py        End-to-End-Test des laufenden Stacks (make smoke)
├── docs/
│   ├── KONZEPT.md              Architekturkonzept
│   └── adr/                    Architekturentscheidungen
├── backend/                    Python 3.13, uv, FastAPI, SQLAlchemy, Alembic
│   ├── Dockerfile              ein Image für api, worker und migrate
│   ├── migrations/             Alembic, handgeschrieben
│   ├── src/modellbahn/
│   │   ├── main.py             FastAPI-Anwendung
│   │   ├── worker.py           Outbox-Dispatcher (python -m modellbahn.worker)
│   │   ├── cli.py              create-staff, export-openapi
│   │   ├── platform/           gemeinsamer Kern ohne Fachlogik
│   │   └── modules/identity/   domain, application, infrastructure, api, contracts
│   └── tests/
└── frontend/                   Next.js 16, React 19, TypeScript, Tailwind CSS
    ├── Dockerfile
    ├── openapi.json            aus dem Backend exportiert, committet
    └── src/
        ├── app/                Seiten: Startseite, /konto/…, /admin/…
        ├── components/ui/
        └── lib/api/generated/  von Orval erzeugter API-Client, committet
```

## Architekturregeln

Die Regeln stammen aus [Konzept §3](docs/KONZEPT.md#3--systemarchitektur). Was sich
automatisch prüfen lässt, prüft die CI; ein Verstoß bricht den Build.

**Module.** Jedes fachliche Modul liegt unter `backend/src/modellbahn/modules/<name>/` und
besitzt ein eigenes PostgreSQL-Schema (heute nur `identity`; dazu `platform` für die Outbox).
Fremdschlüssel über Modulgrenzen zeigen nur auf Aggregatwurzeln und löschen nie kaskadierend.

**Schichten im Modul.** `api` und `infrastructure` → `application` → `domain`. Die Domäne
ist reines Python: keine Importe aus FastAPI, Starlette, SQLAlchemy oder Pydantic. SQLAlchemy
bildet die Domänen-Dataclasses imperativ auf Tabellen ab, ohne ORM-Basisklasse.

**Verträge.** Ein Modul importiert aus einem anderen ausschließlich dessen `contracts`-Paket:
öffentliche Ereignisklassen, DTOs und Abfragefunktionen. `modellbahn.platform` importiert
nie aus `modellbahn.modules`. Die Regeln stehen als import-linter-Verträge mit Platzhaltern in
`backend/pyproject.toml`; ein Test schlägt fehl, wenn ein neues Modul nicht abgedeckt ist.

**Ereignisse und Outbox.** Zustandsänderungen erzeugen Domänenereignisse
(`identity.customer.registered` usw.). Die Unit of Work schreibt sie beim Commit in derselben
Transaktion wie die Fachdaten in `platform.outbox` und weckt den Worker per `NOTIFY`. Der
Worker verteilt sie mit `FOR UPDATE SKIP LOCKED` an die registrierten Handler, wiederholt
Fehlschläge mit wachsendem Abstand und markiert ein Ereignis nach der Höchstzahl an Versuchen
als `dead`. Die Zustellung ist *mindestens einmal*: **Jeder Handler muss idempotent sein.**
Kein Repository committet selbst.

**Echtzeit.** Ereignisse mit Zielgruppe (z. B. `staff`) meldet der Worker nach erfolgreicher
Verarbeitung über `NOTIFY mb_events`. Jede API-Instanz reicht sie per Server-Sent Events an
`GET /api/v1/admin/events` weiter; mit `Last-Event-ID` holt ein Client Verpasstes nach.
Übertragen wird nur der öffentliche Teil eines Ereignisses, nie Geheimnisse oder
E-Mail-Adressen von Kunden.

**API.** Alles unter `/api/v1`, JSON in snake_case, jede Route mit `operation_id` und
Antwortmodell, damit der erzeugte Client sauber bleibt. Fehler sind RFC 9457
`application/problem+json` mit stabilem `code`, den das Frontend ins Deutsche übersetzt.
Unsichere Methoden verlangen den Header `X-Modellbahn-Client: web` (CSRF-Schutz). Kunden und
Mitarbeiter haben getrennte Sitzungscookies (`mb_session`, `mb_admin`); keines öffnet den
Bereich des anderen.

**Sprache.** Bezeichner, API und Code-Kommentare auf Englisch, Oberfläche und Dokumentation
auf Deutsch.

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) läuft für jeden Pull Request, jeden
Push auf `main` und auf Knopfdruck. Ein neuer Push bricht den laufenden Lauf desselben Zweigs
ab (außer auf `main`). Der Workflow darf das Repository nur lesen.

| Job | Prüft |
| --- | --- |
| `backend` | `uv.lock` passt zu `pyproject.toml`; `uv sync --frozen`; Ruff (Lint und Format), `mypy --strict`, import-linter, pytest gegen einen PostgreSQL-17-Dienst |
| `frontend` | `npm ci`, ESLint, `tsc --noEmit`, Vitest, `next build` |
| `contract` | exportiert das OpenAPI-Schema und erzeugt den Client neu; beides muss dem committeten Stand entsprechen |
| `compose` | `docker compose config`, `caddy validate`, Build beider Images |

Lokal prüft `make check` dasselbe. Schlägt `contract` fehl: `make client` ausführen und das
Ergebnis committen.

## Konfiguration

Alle Einstellungen des Stacks kommen aus `.env`; [`.env.example`](.env.example) beschreibt
jede Variable und taugt unverändert für die lokale Entwicklung. `.env` ist von Git
ausgeschlossen. Für eine öffentliche Domain mindestens `SITE_ADDRESS`, `CADDY_TLS` (eine
E-Mail-Adresse schaltet auf Let's Encrypt), `MB_PUBLIC_BASE_URL`, `MB_ENVIRONMENT=production`,
`POSTGRES_PASSWORD` und die `MB_SMTP_*`-Werte eines echten Mailservers setzen. Der
Produktionsbetrieb (Sicherungen, HSTS, ohne Mailpit) ist noch nicht Teil von Schritt 2.

### Hinter einem TLS-Proxy

Prüft ein Firmen-Proxy TLS mit einer eigenen Zertifizierungsstelle, scheitern `pip`, `uv` und
`npm` beim Image-Build. Beide Dockerfiles nehmen dafür ein optionales Build-Secret `build_ca`
an, das nur in den Build-Stufen gilt und nie ins fertige Image gelangt. Eine lokale
`docker-compose.override.yml` (von Git ausgeschlossen, Compose liest sie automatisch) reicht
es durch:

```yaml
x-build-ca: &build-ca
  build:
    secrets:
      - build_ca

services:
  migrate: *build-ca
  api: *build-ca
  worker: *build-ca
  web: *build-ca

secrets:
  build_ca:
    file: ./build-ca.pem   # CA-Kette des Proxys im PEM-Format, ebenfalls ignoriert
```

## Weiterlesen

- [Architekturkonzept](docs/KONZEPT.md): Domäne, Datenmodell, API, Fahrplan
- Architekturentscheidungen:
  - [0001 Modularer Monolith mit Schema je Modul](docs/adr/0001-modularer-monolith-mit-schema-je-modul.md)
  - [0002 Outbox in PostgreSQL statt Broker](docs/adr/0002-outbox-in-postgresql-statt-broker.md)
  - [0003 Sitzungscookies statt JWT, getrennt nach Shop und Admin](docs/adr/0003-sitzungscookies-statt-jwt-getrennt-nach-shop-und-admin.md)
  - [0004 CSRF-Schutz über eigenen Header](docs/adr/0004-csrf-schutz-ueber-eigenen-header.md)
  - [0005 Kundenkonten ab Start, Gastbestellung mit späterer Übernahme](docs/adr/0005-kundenkonten-ab-start-gastbestellung-mit-spaeterer-uebernahme.md)
  - [0006 UUIDv7 als Kennungen](docs/adr/0006-uuidv7-als-kennungen.md)
