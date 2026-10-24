# ADR 0003: Sitzungscookies statt JWT, getrennt nach Shop und Admin

Status: angenommen · 22.10.2026

## Kontext

Einziger Client ist der Browser, Shop und API liegen hinter Caddy auf demselben Ursprung.
Abmelden, das Beenden aller anderen Sitzungen nach einer Passwortänderung und Kontosperren
müssen sofort wirken. Ein JWT gilt bis zu seinem Ablauf, lässt sich nur mit einer Sperrliste
widerrufen und landet, wenn JavaScript es lesen kann, bei jeder XSS-Lücke in fremden Händen.
Laut Konzept (§5.6) darf eine Kundensitzung nie den Admin-Bereich öffnen.

## Entscheidung

- Sitzungen sind zufällige, undurchsichtige Tokens (32 Byte). In `identity.sessions` steht nur
  ihr SHA-256-Hash, zusammen mit der Kontoart (`kind`).
- Zwei Cookies, beide `HttpOnly`, `Secure` und `Path=/`:
  `mb_session` für Kunden (`SameSite=Lax`, 30 Tage) und `mb_admin` für Mitarbeiter
  (`SameSite=Strict`, 12 Stunden).
- Eine Sitzung authentifiziert nur Endpunkte ihres Bereichs. Die Datenbank sichert ab, dass
  `kind` der Sitzung zur Kontoart passt (Fremdschlüssel auf `(id, kind)`).
- `Lax` beim Shop, damit ein Kunde, der über einen Link aus einer E-Mail oder von einer
  fremden Seite kommt, angemeldet bleibt. Der Admin-Bereich braucht das nicht und bekommt
  die strengere Einstellung.
- Passwortänderung beendet alle anderen Sitzungen, ein Passwort-Reset alle. `last_seen_at`
  wird höchstens alle fünf Minuten geschrieben.

## Folgen

- Abmelden und Widerruf wirken sofort: Die Zeile wird gelöscht.
- Ein Datenbankleck enthält keine verwendbaren Tokens, und Skripte im Browser lesen keines.
- Jede angemeldete Anfrage kostet einen Primärschlüssel-Zugriff auf die Datenbank.
- Cookies werden vom Browser automatisch mitgeschickt; deshalb braucht es CSRF-Schutz (ADR 0004).
- `Secure` setzt HTTPS voraus, darum läuft auch lokal Caddy. `MB_COOKIE_SECURE=false` ist nur
  für reines HTTP in der Entwicklung gedacht und wird in Produktion abgelehnt.
- Wer Mitarbeiter und Kunde zugleich ist, meldet sich in beiden Bereichen getrennt an.
