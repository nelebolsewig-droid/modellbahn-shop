# ADR 0004: CSRF-Schutz über eigenen Header

Status: angenommen · 22.10.2026

## Kontext

Die Anmeldung läuft über Cookies (ADR 0003), die der Browser auch bei Anfragen mitschickt,
die eine fremde Seite auslöst. Gängige Abwehr sind Synchronizer-Tokens (serverseitig
gespeichert oder als Double-Submit-Cookie), die Prüfung von `Origin`/`Referer` oder ein
eigener Anfrage-Header. Tokens müssen in jedes Formular und jeden Client gebracht werden und
vertragen sich schlecht mit Server-Rendering und einem generierten API-Client.

## Entscheidung

- Jede unsichere Methode (POST, PUT, PATCH, DELETE) unter `/api/` verlangt den Header
  `X-Modellbahn-Client: web`. Fehlt er, antwortet die API mit 403 und dem Problem-Code
  `csrf_header_missing`. Anfragen mit Body müssen `application/json` sein.
- Die API sendet keine CORS-Header.
- Begründung: Ohne Preflight darf eine fremde Seite nur „einfache“ Anfragen schicken, also
  keine mit eigenen Headern und keine mit `application/json`. Alles andere löst einen
  CORS-Preflight aus, und den lehnt der Browser ab, weil die API ihn nicht erlaubt. HTML-Formulare
  können keine Header setzen.
- `SameSite=Lax` bzw. `Strict` an den Cookies (ADR 0003) bleibt als zweite Schicht bestehen.
- Der gemeinsame Fetcher des Frontends setzt den Header bei jeder unsicheren Anfrage.

## Folgen

- Kein Zustand auf dem Server, keine Tokens in Formularen; funktioniert mit
  Server-Rendering und dem generierten Client und ist leicht zu testen.
- Der Schutz hängt daran, dass die API nie CORS mit Credentials für fremde Ursprünge erlaubt.
  Wer CORS einführen will, muss diese Entscheidung neu treffen.
- `GET` muss frei von Seiteneffekten bleiben; es ist nicht geschützt.
- Andere Clients (Skripte, später Scanner) setzen den Header ebenfalls. Er ist kein
  Geheimnis, sondern ein Nachweis, dass die Anfrage nicht als einfache Anfrage kam.
- Gegen XSS auf dem eigenen Ursprung hilft keine CSRF-Abwehr; dafür braucht es sauberes
  Escaping und später eine Content-Security-Policy.
