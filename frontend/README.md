# Frontend des Modellbahn-Shops

Next.js 16 (App Router) mit React 19, TypeScript (strict) und Tailwind CSS 4: der Shop für
Kundinnen und Kunden und der Admin-Bereich „Stellwerk“ in einem Projekt. Das Gesamtbild steht
in [`docs/KONZEPT.md`](../docs/KONZEPT.md), Start und Stack in der [README](../README.md) im
Wurzelverzeichnis.

## Schnellstart

```bash
npm ci
npm run dev        # http://localhost:3000; API, Worker und Datenbank wie in der README
```

`next dev` leitet `/api/*`, `/healthz` und `/readyz` an `API_INTERNAL_URL` weiter (Standard
`http://localhost:8000`). Der Browser spricht so nur mit einem Ursprung, die Sitzungscookies
bleiben First-Party – wie hinter Caddy, wo diese Pfade Next.js gar nicht erreichen.

## Befehle

| Zweck | Befehl |
| --- | --- |
| Entwicklungsserver | `npm run dev` |
| Linter (ESLint, inkl. jsx-a11y und TanStack Query) | `npm run lint` |
| Typprüfung (erzeugt vorher die Routentypen) | `npm run typecheck` |
| Tests (Vitest, Testing Library) | `npm test` |
| Produktions-Build (`output: "standalone"`) | `npm run build` |
| API-Client aus `openapi.json` neu erzeugen | `npm run client` |

`NEXT_PUBLIC_SHOP_NAME` setzt den Namen des Shops; er wird beim Build eingebaut.

## Aufbau

```text
src/
├── app/
│   ├── (shop)/            Startseite, /konto/…, Impressum, Datenschutz – mit Kopf- und Fußzeile
│   ├── admin/             /admin/anmelden und das Stellwerk, immer im dunklen Thema
│   ├── globals.css        Design-Tokens (@theme) und Grundstile
│   └── layout.tsx         <html lang="de">, Schriften, QueryClientProvider
├── components/
│   ├── ui/                eigene Bausteine im shadcn-Stil (Button, Dialog, FormField, …)
│   ├── forms/             Formulare, die Shop und Admin teilen
│   ├── account/           Kundenkonto
│   ├── admin/             Stellwerk: Ereignis-Feed, Signallampe, Systemstatus
│   └── site/              Kopf, Fuß, Seitenrahmen, Gleisplan
├── lib/
│   ├── api/               fetcher.ts (Mutator), problem.ts (ApiProblem), generated/ (Orval)
│   ├── i18n/problems.ts   deutsche Texte für jeden Fehlercode der API
│   ├── session/           Anmeldestatus aus /me, Weiterleitungen geschützter Seiten
│   ├── realtime/          EventSource-Hook und Auswertung der SSE-Nachrichten
│   └── validation/        zod-Schemas, Spiegel der Backend-Regeln
└── proxy.ts               leitet ohne Sitzungscookie auf die Anmeldung um
```

## Regeln im Code

- **API nur über den erzeugten Client.** `npm run client` erzeugt Hooks und Typen aus
  `openapi.json` nach `src/lib/api/generated/`; der Ordner ist committet und wird nie von Hand
  geändert. Die CI prüft, dass er zum Schema passt.
- **Der Fetcher** (`src/lib/api/fetcher.ts`) bleibt bei relativen URLs, schickt immer die
  Cookies mit, setzt bei POST/PUT/PATCH/DELETE den Header `X-Modellbahn-Client: web` und wirft
  bei jedem Fehler ein `ApiProblem` mit dem `code` der Antwort.
- **Fehlertexte kommen aus dem `code`,** nie aus `detail` oder `title` (die sind englisch).
  Jeder Code, den `openapi.json` nennt, braucht einen Eintrag in `src/lib/i18n/problems.ts`;
  ein Test prüft das.
- **Angemeldet ist, wen `/me` bestätigt.** Der Proxy prüft nur, ob ein Cookie da ist, und
  spart damit einen Umweg. Seiten werten die Antwort von `/me` aus: 401 heißt abgemeldet.
- **Formulare** nutzen `useApiForm` (react-hook-form + zod): Prüfung beim Verlassen eines
  Feldes, Feldfehler der API am Feld, alles andere über dem Formular. Feldnamen sind die der
  API (`display_name`, `new_password`), damit 422-Antworten direkt passen.
- **Farben nur über Tokens** (`bg-surface`, `text-ink`, `border-line-strong`, …) aus
  `globals.css`. Der Shop folgt dem Farbschema des Systems; das Stellwerk ist immer dunkel.
  Text erreicht mindestens 4,5:1 Kontrast, Rahmen von Eingabefeldern 3:1.
- **Barrierefreiheit:** jedes Feld hat ein Label, Fehler sind Live-Regionen, der Fokus ist
  sichtbar, Dialoge kommen von Radix (Fokusfalle, Escape). Farbe trägt nie allein eine
  Information – die Signallampen stehen immer neben Text.
- Zeiten erscheinen in deutscher Zeit (Europe/Berlin), unabhängig vom Gerät.
