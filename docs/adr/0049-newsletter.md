# ADR 0049: Newsletter für Kundenkonten

Status: angenommen · 24.11.2026 · ergänzt ADR 0030 (Mail-Layout)

## Kontext
Statt Werbung in Versandmail, Lieferschein und Rechnung soll es einen Newsletter geben:
einmal im Monat die neuen Modelle und Empfehlungen passend zu den bisherigen
Käufen, nur für Kund:innen mit Konto, automatisch versendet. Werbemails brauchen eine
nachweisbare Einwilligung (Art. 6 Abs. 1 lit. a DSGVO, § 7 Abs. 2 UWG).

## Entscheidung
- **Eigenes Modul `newsletter`** (Schema `newsletter`, Migration 0035). Es liest Kataloge,
  Käufe, Konten und Fotos nur über die Verträge der anderen Module
  (`catalog.contracts.showcase`, `sales.contracts.purchases`, `identity.contracts.accounts`).
- **Double-Opt-in je Kundenkonto:** Häkchen bei der Registrierung (`newsletter` im
  Ereignis `CustomerRegistered`) oder Schalter unter „Mein Konto“. Die Bestätigungsmail
  geht erst an eine bestätigte Adresse (sonst nach `EmailVerified`), Link 7 Tage gültig,
  Unbestätigtes nach 14 Tagen gelöscht. Gespeichert werden Zeitpunkt und Textversion
  (`newsletter-2026-11`), keine Adresse: Jede Ausgabe geht an die aktuelle Kontoadresse.
- **Abmelden** mit einem Klick: Link in jeder Ausgabe, `List-Unsubscribe` +
  `List-Unsubscribe-Post` (RFC 8058, `/api/v1/webhooks/newsletter/unsubscribe`), Schalter
  im Konto. Kontolöschung beendet den Newsletter.
- **Automatischer Versand:** Der Worker prüft stündlich; an den Tagen aus
  `MB_NEWSLETTER_DAYS` (Standard `1`, also monatlich am 1.; `1,15` für zweimal) zwischen 9 und 20 Uhr gibt er eine Ausgabe frei,
  wenn seit der letzten neue Modelle veröffentlicht wurden (erste Ausgabe: 30 Tage
  zurück). Höchstens eine Ausgabe je Tag; jede Zustellung wird vermerkt (kein Doppelversand).
- **Inhalt:** bis 6 neue Modelle, danach bis 3 Empfehlungen „Passt zu deiner Sammlung“:
  gleiche Spur wie ein Kauf, Punkte für gleiche (Ober-)Kategorie, nie schon Gekauftes
  oder oben Gezeigtes. Ohne Käufe keine Empfehlungen. Kein Öffnungs- oder Klick-Tracking.
- **Stellwerk → Newsletter:** Zahl der Leser:innen, nächster Termin, wartende neue Modelle,
  bisherige Ausgaben und eine Vorschau mit Beispiel-Leser:in.

## Folgen
- Fotos in der Mail kommen als WebP (256 px); Outlook für Windows zeigt sie nicht, der
  Text steht trotzdem.
- Datenschutzerklärung Abschnitt 8 „Newsletter“.
