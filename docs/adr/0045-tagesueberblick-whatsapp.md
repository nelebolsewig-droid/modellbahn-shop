# ADR 0045: Tagesüberblick per WhatsApp

Status: angenommen · 22.11.2026 · ergänzt ADR 0034 (Morgenmail „Heute dran“)

## Kontext
Die Morgenmail wird im Postfach leicht übersehen. Das Team will den Überblick aufs Handy,
am liebsten per WhatsApp.

## Entscheidung
- Der Worker schickt nach den Mails denselben Überblick als kurze WhatsApp-Nachricht
  (Betreff fett, die Zeilen der Tabelle, Link ins Stellwerk).
- Versand über **CallMeBot** (kostenlos): Jede Person schickt einmal
  „I allow callmebot to send me messages“ an die Nummer, die auf https://www.callmebot.com/blog/free-api-whatsapp-messages/ steht (sie wechselt gelegentlich), und bekommt einen Schlüssel.
- `MB_DIGEST_WHATSAPP=+491701234567:SCHLÜSSEL,+49…:SCHLÜSSEL` in der `.env`; leer = aus.
- Eine fehlgeschlagene Nachricht wird nur geloggt: Die Mail ist dann schon raus und darf
  nicht doppelt kommen.

## Abgewogen
- WhatsApp Cloud API (Meta): offiziell, aber Business-Konto, eigene Nummer, freigegebene
  Vorlage, ca. 4 ct je Nachricht. Lohnt erst, wenn Kunden Nachrichten bekommen sollen.
- SMS (z. B. seven.io): zuverlässig, ca. 8 ct je SMS, Konto mit Guthaben.

## Folgen
CallMeBot ist inoffiziell und ohne Zusage. Die Nachricht enthält nur Zahlen und eine
Bestellnummer, keine Kundendaten. Fällt der Dienst weg, lässt sich `Messenger` gegen
einen anderen Anbieter tauschen, ohne die Morgenmail anzufassen.

## Nachtrag 23.11.2026: Telegram
CallMeBot nahm keine neuen Nutzer mehr an („bot is currently full“). Deshalb zusätzlich
ein eigener Telegram-Bot (offizielle Bot-API, kostenlos): `MB_TELEGRAM_BOT_TOKEN` von
@BotFather, `MB_DIGEST_TELEGRAM` mit den Chat-IDs (z. B. eine Gruppe fürs Team).
Telegram bekommt reinen Text. Beide Wege können parallel laufen (`Broadcast`).
