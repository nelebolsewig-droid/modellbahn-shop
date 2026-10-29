# Modellbahn-Shop

Webshop und Werkstatt-Backend von **adp-Modelle**: Fahrzeugmodelle in Handarbeit und
Kleinserie, für Schiene und Straße. Gebaut als **modularer
Monolith**: ein Repository, ein Backend in Python (FastAPI) mit zwei Prozessen (API und
Worker), ein Frontend in Next.js, PostgreSQL als Datenbank und Warteschlange, Caddy als
HTTPS-Eingang. Das vollständige Architekturkonzept steht in [docs/KONZEPT.md](docs/KONZEPT.md),
die tragenden Entscheidungen in [docs/adr/](docs/adr/).

**Stand: Schritt 5 – Lager und Barcodes.** Auf dem Fundament aus Schritt 2 (Plattform-Kern
mit Outbox, Unit of Work, IDs, Fehlerformat und Echtzeit; Modul *Identität* mit Kundenkonten
und Mitarbeiterzugang; Docker Compose, CI, Architekturregeln), den Modulen *Katalog* und
*Medien* aus Schritt 3 und *Verkauf* aus Schritt 4 steht jetzt das Modul *Lager*:
Lagerplätze, jedes Stück mit eigenem Etikett, ein Scanner fürs Handy, Kommissionieren live
und Lieferbarkeit im Shop (ADR 0011). Der Katalog ist nach **Maßstab** geordnet, darunter
nach Kategorie (ADR 0010). Dazu kam das Modul *Auftritt*: Messetermine mit Kalender und
Messe-Post, das Impressum aus der Konfiguration und der Versand in alle EU-Länder
(ADR 0012). Seit ADR 0013 gibt es jedes Modell als **Bausatz** oder **Fertigmodell** in
Farben, eine **Schnellerfassung** fürs Handy und einen Startbestand zum Einspielen. Die
Fertigung folgt mit Schritt 6.

Was sich vorführen lässt:

- **Konten.** Ein Besucher registriert sich, der Worker verschickt die Bestätigungs-E-Mail
  (sichtbar in Mailpit), der Link bestätigt das Konto und meldet an, der Kunde sieht „Mein
  Konto“. Ein Mitarbeiter sieht die Registrierung im Admin-Bereich „Stellwerk“ live
  erscheinen, ohne die Seite neu zu laden. Passwort zurücksetzen, Passwort ändern, Abmelden
  und Konto löschen funktionieren ebenfalls.
- **Katalog.** Im Stellwerk unter „Katalog“ legt ein Mitarbeiter Kategorien und ein Produkt
  an, ergänzt Maßstäbe (etwa H0, N oder 1:24) mit Maßen und Varianten mit Preis: den
  Bausatz und das Fertigmodell, dieses auch in mehreren Farben. Artikelnummer und interne
  EAN vergibt das System. Fotos gehen per Ziehen und Ablegen direkt
  in den Objektspeicher, der Worker rechnet alle Bildstufen, und das Vorschaubild erscheint
  nach wenigen Sekunden ohne Neuladen. Sind die Regeln erfüllt (Kategorie, aktive Variante,
  fertiges Hauptbild), wird das Produkt veröffentlicht.
  Die Maßstäbe selbst pflegt das Stellwerk unter „Maßstäbe“: von Z 1:220 bis G 1:22,5,
  dazu 1:24 und 1:25 für Straßenfahrzeuge ohne Gleis.
- **Schnellerfassung.** Unter „Erfassen“ steht man mit dem Handy an der Kiste: Foto, Modell
  suchen oder neu anlegen, Maßstab, Ausführung, Farbe und Preis antippen, Stücke mit
  Etiketten gleich dazu. Neues bleibt Entwurf; „Fertige veröffentlichen“ in der Produktliste
  bringt abends alle vollständigen Entwürfe in einem Schritt in den Shop.
  `make catalog-import` spielt den Startbestand ein: die bekannten Modelle mit Preisen und
  Entwürfe aus den Lagerfotos.
- **Shop.** Der Katalog beginnt mit der Frage „Welcher Maßstab?“: Kacheln mit der Zahl der
  Modelle und einem Maßband, das einen Meter Vorbild im jeweiligen Maßstab zeigt. Danach
  folgen unter `/katalog/{maßstab}/{kategorie}` nur die Kategorien und Unterkategorien, die
  es in diesem Maßstab gibt (etwa Straßenfahrzeuge → LKW → Feuerwehr), dazu Epoche,
  Sortierung und Suche. Die Produktseite zeigt Fotobühne, Wahl von Maßstab, Ausführung und
  Farbe (mit Farbtupfern; die Bühne springt auf Fotos der gewählten Farbe), Preis und Maße.
- **Kaufen.** Der Warenkorb zeigt Preise vom Server und den Versand: 5,90 € nach
  Deutschland, 16,90 € in die übrigen EU-Länder. An der Kasse bestellt man als
  Gast oder mit Konto (dann mit Auswahl aus dem Adressbuch). Die Zahlung ist bis zur
  Anbindung eines Anbieters eine sichtbare **Testzahlung**: Man wählt, ob sie gelingt,
  abgelehnt wird oder der Dienst gestört ist. Eingangsbestätigung, Zahlungseingang, Versand
  und Storno kommen als E-Mail (in Mailpit). Wer als Gast bestellt und später ein Konto mit
  derselben Adresse bestätigt, findet die Bestellung unter „Mein Konto → Bestellungen“.
- **Bestellungen im Stellwerk.** Unter „Bestellungen“ erscheinen neue Bestellungen live mit
  blinkendem Signal. Das Bestellpult zeigt Verlauf, Zahlungen, Artikel, die Pickliste und
  einen Paketaufkleber; Packer melden den Versand mit Sendungsnummer, sobald alles
  kommissioniert ist. Inhaber und Mitarbeiter können stornieren, eine Zahlung wird dabei
  erstattet.
- **Lager.** Unter „Lager“ legt ein Mitarbeiter Lager, Regale, Fächer und Boxen an und druckt
  ihre Etiketten. „Einheiten erfassen“ gibt jedem neuen Stück einen eigenen Code und druckt
  Etiketten mit der EAN für die Kasse und dem Code 128 des Stücks, als PDF für A4-Bögen
  (70 × 37 mm, ab einem freien Feld) oder den Brother QL (62 mm). Der Bestand zeigt je
  Artikel, was frei, reserviert, kommissioniert, noch einzulagern oder in Fertigung ist,
  live. Die Artikelliste für die Kasse (SumUp) gibt es als CSV.
- **Scanner.** Unter „Scanner“ arbeitet das Handy mit der Kamera, ein Handscanner per
  Tastatureingabe oder die Eingabe von Hand: Platz scannen, dann die Ware, und sie ist
  eingelagert. Beim Kommissionieren wählt man die Bestellung und scannt die Pickliste ab; das
  Bestellpult am Rechner zieht mit. Jeder Scan gibt Ton, Vibration und eine große Antwort,
  lässt sich zehn Sekunden lang zurücknehmen und wartet ohne Netz auf dem Gerät.
- **Lieferbarkeit.** Jede Ausführung ist vorrätig oder wird auf Bestellung gefertigt. Die
  Produktseite sagt „Sofort lieferbar“, „Wird für dich gefertigt · Lieferzeit 1–2 Wochen“
  oder „Derzeit nicht lieferbar“; Warenkorb und Kasse nehmen nicht mehr an, als lieferbar
  ist, und nennen die Lieferzeit vor dem Kauf.
- **Messen.** Im Stellwerk unter „Messen“ trägt ein Mitarbeiter Messen mit Tagen, Ort, Stand
  und Öffnungszeiten ein. Der Shop zeigt sie unter `/termine` als Halte auf einem
  Streckenband, die nächste auch auf der Startseite, jede als Kalenderdatei, alle als
  Kalender-Abo. Besucher bestellen die **Messe-Post** und bestätigen sie per Link aus der
  E-Mail (Double-Opt-in). „Ankündigen“ schickt eine Messe einmal an alle Bestätigten, jede
  Mail mit Abmeldelink. Bestell- und Versandmails nennen die nächste Messe.
- **eBay.** Unter „eBay“ verbindet der Inhaber das eBay-Konto des Shops und wählt Versand,
  Zahlung und Rücknahme; eine „Fahrstraße“ aus fünf Signalen zeigt, wann Angebote online
  gehen dürfen. Jede Shop-Kategorie bekommt die Nummer einer eBay-Kategorie, der Aufschlag
  für eBays Gebühren ist einstellbar. Im Produkt-Editor schaltet „Auf eBay anbieten“ je
  Maßstab; Texte, Fotos, Preise und Stückzahlen folgen dem Shop von selbst, jede Minute.
  Bestellungen von eBay kommen bezahlt herein, laufen durch Lager und Versand wie
  Shop-Bestellungen und melden die Sendungsnummer an eBay zurück. `MB_EBAY_MODE=test` (in
  `.env.example`) schaltet den eingebauten **Testmarktplatz** ein: verbinden, anbieten und
  als Käufer kaufen, ganz ohne eBay-Schlüssel (ADR 0014).
- **Impressum und Werkstatt.** `/impressum` kommt aus `MB_IMPRINT_*`, dieselben Angaben
  schließen jede E-Mail. Dazu die Seiten „Über uns“ und „Sonderanfertigung“ (3D-Druck und
  Lasercutting).
- **So entsteht ein Modell.** `/so-entsteht-ein-modell` zerlegt ein Fahrzeug als
  Explosionszeichnung in 3D: Beim Scrollen fährt es auseinander und wieder zusammen, mit
  Positionsnummern, Stückliste und Druckzeiten. three.js lädt erst auf dieser Seite. Bis die
  Werkstatt ein eigenes Modell liefert, steht ein gekennzeichneter Platzhalter da (ADR 0016).

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

`make up` legt beim ersten Aufruf `.env` aus `.env.example` an, baut die Images, richtet den
Objektspeicher ein (Buckets und Zugangsschlüssel, idempotent), wendet die Migrationen an und
wartet, bis alle Dienste gesund sind. `make staff` fragt das Passwort
verdeckt zweimal ab; mit `ROLE=staff` oder `ROLE=packer` entsteht ein Konto mit anderer Rolle.

`make smoke` prüft den laufenden Stack von außen, über Caddy und Mailpit, so wie ein Browser:
Startseite, Registrierung, Bestätigungs-E-Mail, Bestätigung mit Anmeldung, Abmelden, erneutes
Anmelden, Passwort zurücksetzen, Anmeldung im Stellwerk, Ereignisstrom (Nachlieferung per
`Last-Event-ID` und live), dann den Katalog: Produktentwurf mit `If-Match`, Maßstab mit zwei
Varianten, ein Foto über die signierte Upload-URL, die Bildstufen live und öffentlich unter
`/medien`, Veröffentlichen, die Shop-Ansicht nach Maßstab mit Umleitung alter Adressen und die
Pflege der Maßstäbe. Danach der Verkauf: Warenkorb mit Cookie,
abgelehnte veraltete Summe, Gastbestellung mit `Idempotency-Key` (auch wiederholt),
Eingangsbestätigung, Statusseite, Testzahlung (abgelehnt, gestört, bezahlt), Übernahme ins
Konto nach der Registrierung, Versand mit Sendungsnummer, eine Kundenbestellung mit
Adressbuch und ihr Storno mit Erstattung. Zum Schluss Archivieren, die Grenzen zwischen
Shop- und Admin-Sitzung und den CSRF-Header. Jeder Schritt erscheint mit ✓ oder ✗; beim ersten Fehler endet der Lauf mit
Exit-Code 1. Für jeden Lauf legt das Ziel ein Wegwerf-Mitarbeiterkonto (Rolle `staff`) mit
Zufallspasswort an und prüft HTTPS gegen Caddys interne Zertifizierungsstelle. Das Skript
[`scripts/smoke_e2e.py`](scripts/smoke_e2e.py) braucht nur Python 3.13 ohne Zusatzpakete.

| Adresse | Was |
| --- | --- |
| <https://localhost> | Shop |
| <https://localhost/katalog> | Shop-Katalog nach Maßstab, etwa `/katalog/h0/lkw`; Produktseiten unter `/produkte/{adresse}` |
| <https://localhost/warenkorb> | Warenkorb; weiter zur Kasse unter `/kasse` |
| <https://localhost/konto/registrieren> | Kundenkonto anlegen; Bestellungen und Adressbuch unter `/konto/bestellungen` und `/konto/adressen` |
| <https://localhost/admin> | Admin-Bereich „Stellwerk“ (Anmeldung mit dem Konto aus `make staff`) |
| <https://localhost/admin/bestellungen> | Bestellungen: Liste live, Bestellpult mit Versand und Storno |
| <https://localhost/admin/katalog> | Produkte anlegen und pflegen; Kategorien und Maßstäbe unter `/admin/katalog/kategorien` und `/admin/katalog/massstaebe` |
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

Stoppen mit `make down`; die Daten bleiben erhalten. Alles inklusive Datenbank, Fotos und
Zertifikaten löschen: `docker compose down --volumes`.

**Bestehende `.env` aus Schritt 2:** Der Objektspeicher braucht neue Werte. Den Block
„Object storage“ aus [`.env.example`](.env.example) in die eigene `.env` übernehmen; fehlt er,
bricht `make up` mit einem Hinweis auf die fehlende Variable ab.

## Make-Ziele

`make` ohne Ziel zeigt diese Übersicht.

| Ziel | Wirkung |
| --- | --- |
| `make up` | Stack bauen und starten: db, mailpit, storage, storage-init, migrate, api, worker, web, caddy |
| `make down` | Stack stoppen, Daten bleiben erhalten |
| `make logs` | Logs aller Dienste verfolgen; ein Dienst: `make logs SERVICE=worker` |
| `make dev-db` | Nur PostgreSQL und Mailpit starten, für die Entwicklung ohne Container |
| `make migrate` | Migrationen mit dem Backend-Image auf die Datenbank des Stacks anwenden |
| `make staff EMAIL=… NAME="…" [ROLE=owner\|staff\|packer]` | Mitarbeiterkonto anlegen |
| `make catalog-import` | Startbestand des Katalogs einspielen (`backend/seed/startbestand.json`); wiederholbar, legt nur Entwürfe an |
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
Ursprung bleiben. Der Objektspeicher läuft nur im Compose-Stack: Ohne Container
funktionieren Katalog und Shop, Fotos lassen sich aber nicht hochladen; dafür `make up`
verwenden. Das Backend liest seine Einstellungen nur aus `MB_*`-Umgebungsvariablen,
nicht aus `.env`. Sitzungscookies sind standardmäßig `Secure`; Chrome und Firefox nehmen sie
auf `http://localhost` trotzdem an, Safari nicht. Dort hilft `MB_COOKIE_SECURE=false` (in
Produktion verweigert das Backend diese Einstellung).

Die Backend-Tests verwenden `TEST_DATABASE_URL`, wenn gesetzt, und starten sonst einen
PostgreSQL-Container (`TEST_POSTGRES_IMAGE`, Standard `postgres:17-alpine`).

## Repository

```text
modellbahn-shop/
├── Makefile                    Einstiegspunkte, siehe oben
├── docker-compose.yml          db, mailpit, storage, storage-init, migrate, api, worker, web, caddy
├── Caddyfile                   HTTPS; /api/* an die API, Uploads und /medien an den Speicher,
│                               alles andere an Next.js
├── infra/garage/garage.toml    Objektspeicher (Garage, ein Knoten)
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
│   │   ├── worker.py           Outbox-Dispatcher und Bild-Pipeline (python -m modellbahn.worker)
│   │   ├── cli.py              create-staff, unlock-staff, init-storage, export-openapi
│   │   ├── platform/           gemeinsamer Kern ohne Fachlogik
│   │   └── modules/            je Modul domain, application, infrastructure, api, contracts
│   │       ├── identity/       Kundenkonten, Mitarbeiter, Sitzungen
│   │       ├── media/          Uploads, Bildstufen, Objektspeicher
│   │       ├── catalog/        Produkte, Maßstäbe, Varianten, Kategorien, Galerie,
│   │       │                   Artikelliste für die Kasse
│   │       ├── sales/          Warenkorb, Bestellungen, Zahlung, Adressbuch, Versandzonen
│   │       ├── inventory/      Lagerplätze, Einheiten, Journal, Scans, Zuteilung,
│   │       │                   Etiketten (PDF mit EAN-13 und Code 128), Lieferbarkeit
│   │       ├── site/           Messen, Kalender (iCalendar), Messe-Post mit Double-Opt-in
│   │       └── marketplace/    eBay: Verbindung (OAuth), Angebote im Gleichschritt mit
│   │                           Katalog und Lager, Bestellungen, Testmarktplatz
│   └── tests/
└── frontend/                   Next.js 16, React 19, TypeScript, Tailwind CSS
    ├── Dockerfile
    ├── openapi.json            aus dem Backend exportiert, committet
    └── src/
        ├── app/                Seiten: Startseite, /katalog, /produkte/…, /warenkorb, /kasse,
        │                       /bestellung/…, /konto/…, /termine, /ueber-uns,
        │                       /sonderanfertigung, /impressum, /admin/…
        ├── components/ui/      Bausteine des Designsystems (Konzept §11.3)
        ├── lib/inventory/      Scanner ohne Browser testbar: Codes, Handscanner, Scan-Sitzung,
        │                       Offline-Warteschlange
        └── lib/api/generated/  von Orval erzeugter API-Client, committet
```

## Architekturregeln

Die Regeln stammen aus [Konzept §3](docs/KONZEPT.md#3--systemarchitektur). Was sich
automatisch prüfen lässt, prüft die CI; ein Verstoß bricht den Build.

**Module.** Jedes fachliche Modul liegt unter `backend/src/modellbahn/modules/<name>/` und
besitzt ein eigenes PostgreSQL-Schema (heute `identity`, `media`, `catalog` und `sales`; dazu
`platform` für die Outbox).
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
`POSTGRES_PASSWORD`, die `MB_SMTP_*`-Werte eines echten Mailservers, die Anbieterangaben
`MB_IMPRINT_*` (ohne sie startet das Backend in Produktion nicht) und eigene Werte für
`GARAGE_RPC_SECRET`, `GARAGE_ADMIN_TOKEN`, `MB_S3_ACCESS_KEY_ID` und `MB_S3_SECRET_ACCESS_KEY`
setzen (`.env.example` zeigt, wie man sie erzeugt; in Produktion verweigert das Backend den
Entwicklungsschlüssel). Echte Anbieterangaben gehören nur in `.env`; `.env.example` hat
Platzhalter. Der Shopname kommt aus dem Absender `MB_SMTP_FROM` (E-Mails) und
`NEXT_PUBLIC_SHOP_NAME` (Oberfläche). Der Produktionsbetrieb (Sicherungen von Datenbank und
Objektspeicher, HSTS, ohne Mailpit) und ein echter Zahlungsanbieter fehlen noch.

Für den echten eBay-Verkauf braucht es ein Entwicklerkonto auf developer.ebay.com: die
Schlüssel der Anwendung (`MB_EBAY_CLIENT_ID`, `MB_EBAY_CLIENT_SECRET`) und einen RuName
(`MB_EBAY_RU_NAME`), dessen „Auth accepted URL“ auf
`https://<domain>/api/v1/admin/marketplace/ebay/callback` zeigt. Dazu `MB_EBAY_MODE=sandbox`
zum Ausprobieren oder `production` und einen eigenen `MB_EBAY_TOKEN_KEY`. In Produktion
verweigert das Backend den Testmarktplatz und die Sandbox.

eBay gibt die Produktions-Schlüssel erst frei, wenn der Shop **Löschmeldungen** empfängt
(ADR 0015). Dafür ein eigenes `MB_EBAY_VERIFICATION_TOKEN` setzen (32 bis 80 Zeichen, etwa
`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`). Im Entwicklerkonto unter
„Alerts & Notifications“ dann dasselbe Token und die Adresse eintragen, die das Stellwerk
unter „eBay“ anzeigt: `https://<domain>/api/v1/webhooks/ebay/account-deletion`. Das geht
schon mit `MB_EBAY_MODE=off`, also bevor die Produktions-Schlüssel gelten.

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
  storage-init: *build-ca
  api: *build-ca
  worker: *build-ca
  web: *build-ca

secrets:
  build_ca:
    file: ./build-ca.pem   # CA-Kette des Proxys im PEM-Format, ebenfalls ignoriert
```

## Weiterlesen

- [Architekturkonzept](docs/KONZEPT.md): Domäne, Datenmodell, API, Gestaltung, Fahrplan
- Architekturentscheidungen:
  - [0001 Modularer Monolith mit Schema je Modul](docs/adr/0001-modularer-monolith-mit-schema-je-modul.md)
  - [0002 Outbox in PostgreSQL statt Broker](docs/adr/0002-outbox-in-postgresql-statt-broker.md)
  - [0003 Sitzungscookies statt JWT, getrennt nach Shop und Admin](docs/adr/0003-sitzungscookies-statt-jwt-getrennt-nach-shop-und-admin.md)
  - [0004 CSRF-Schutz über eigenen Header](docs/adr/0004-csrf-schutz-ueber-eigenen-header.md)
  - [0005 Kundenkonten ab Start, Gastbestellung mit späterer Übernahme](docs/adr/0005-kundenkonten-ab-start-gastbestellung-mit-spaeterer-uebernahme.md)
  - [0006 UUIDv7 als Kennungen](docs/adr/0006-uuidv7-als-kennungen.md)
  - [0007 Helles Präzisionsdesign](docs/adr/0007-helles-praezisionsdesign.md)
  - [0008 Objektspeicher und Medien-Pipeline](docs/adr/0008-objektspeicher-und-medien-pipeline.md)
  - [0009 Warenkorb, Checkout und Mock-Zahlung](docs/adr/0009-warenkorb-checkout-und-mock-zahlung.md)
  - [0010 Katalog nach Maßstab statt nach Spurweite](docs/adr/0010-katalog-nach-massstab.md)
  - [0011 Lager, Barcodes und Lieferbarkeit](docs/adr/0011-lager-barcodes-und-lieferbarkeit.md)
  - [0012 Messen, Messe-Post und Impressum](docs/adr/0012-messen-messe-post-und-impressum.md)
  - [0013 Bausatz und Fertigmodell, Farben, Schnellerfassung und Startbestand](docs/adr/0013-bausatz-fertigmodell-farben-schnellerfassung.md)
