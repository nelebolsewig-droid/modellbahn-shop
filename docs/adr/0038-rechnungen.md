# ADR 0038: Rechnungen und Rechnungskorrekturen als PDF

Status: angenommen · 19.11.2026

## Kontext

Bisher bekam der Kunde eine Bestellbestätigung, aber keine Rechnung. Bei Shopify schrieb
die App die Rechnung; mit dem Umzug fällt sie weg. Ein Unternehmer muss bei einer
Lieferung an einen anderen Unternehmer eine Rechnung ausstellen und darf es bei
Privatkunden. Kunden erwarten sie, und Geschäftskunden (Vereine, Händler) brauchen sie
für den Vorsteuerabzug.

Eine ordentliche Rechnung nennt nach § 14 Abs. 4 UStG unter anderem:
- Name und Anschrift von Aussteller und Empfänger,
- Steuernummer oder USt-IdNr. des Ausstellers,
- Ausstellungsdatum und eine fortlaufende, einmalige Nummer,
- Menge und Art der Ware,
- den Zeitpunkt der Lieferung,
- Entgelt, Steuersatz und Steuerbetrag.

Der Lieferzeitpunkt steht erst mit dem Versand fest. Geld, das nach der Rechnung
zurückgeht (Rücksendung, Widerruf), braucht eine Rechnungskorrektur, die die Rechnung
nennt. Eine Rechnung wird nie geändert oder gelöscht (GoBD); das PDF muss zehn Jahre so
bleiben, wie der Kunde es bekam.

## Entscheidung

### Wann eine Rechnung entsteht

- **Rechnung beim Versand:** Der Worker hört auf `sales.order.shipped` und stellt die
  Rechnung aus. Die Versandmail trägt sie als PDF im Anhang und nennt die Nummer.
  - Das gilt auch für eBay-Bestellungen; deren Käufer bekommen vom Shop keine Mail, das
    Stellwerk zeigt die Rechnung aber zum Herunterladen.
- **Korrektur bei Erstattung:** `sales.order.refunded` nach der Rechnung erzeugt eine
  Rechnungskorrektur über den erstatteten Betrag.
  - Geht alles zurück, wiederholt sie alle Zeilen mit negativen Beträgen.
  - Geht ein Teil zurück, hat sie eine Zeile „Erstattung“ mit der darin enthaltenen
    Umsatzsteuer (19 %).
  - Die Erstattungsmail trägt die Korrektur als PDF.
  - Eine Stornierung vor dem Versand braucht keine Korrektur, weil es noch keine Rechnung
    gibt.
- **Idempotent:** Jede Rechnung hat eine Quelle, `order` für die Rechnung und die
  Ereignis-ID für eine Korrektur. Ein eindeutiger Index auf (Bestellung, Quelle) und die
  Sperre der Bestellung beim Ausstellen sorgen dafür, dass ein doppelt zugestelltes
  Ereignis oder Versandmail und Rechnungshandler zusammen nur ein Dokument erzeugen.

### Nummern

- Die Rechnung hat die Nummer `RE-2026-00001`, die Korrektur `RK-2026-00001`. Jede Art und
  jedes Jahr zählt für sich, das Jahr nach deutscher Zeit.
- `sales.invoice_counters` hält die letzte Nummer je Art und Jahr. Die nächste holt ein
  `INSERT … ON CONFLICT DO UPDATE … RETURNING`. Die Zeile bleibt bis zum Commit
  gesperrt, also entsteht keine Lücke: Scheitert das Ausstellen, rollt auch der Zähler
  zurück.

### Speicherung

- Neue Tabelle `sales.invoices` (Migration 0026) mit Nummer, Art, Summe, Steuer, Datum,
  dem Verweis der Korrektur auf ihre Rechnung und dem PDF als `bytea`.
- Prüfungen in der Datenbank:
  - Format der Nummer,
  - eine Korrektur nennt ihre Rechnung, eine Rechnung nicht,
  - die Rechnung ist positiv, die Korrektur negativ.
- Fremdschlüssel mit `RESTRICT`: Eine Bestellung mit Rechnung lässt sich nicht löschen.
- Das PDF wird einmal gezeichnet und gespeichert, nicht bei jedem Abruf neu. So bleibt es
  gleich, auch wenn sich später Impressum, Layout oder Produktname ändern.

### Das PDF

- reportlab, A4, Aufbau nach DIN 5008 Form B:
  - Fensterzeile und Anschrift,
  - Infoblock mit Nummer, Datum, Lieferdatum und Bestellung,
  - Tabelle,
  - Netto, Umsatzsteuer und Gesamt,
  - Fußzeile mit Anbieter, Kontakt und Steuernummer.
- Der Schriftzug ist Text, nicht Bild: „adp“ rot in Times Bold Italic, „-Modelle“ in
  Helvetica Bold (ADR 0030). Darunter läuft die Mandarin-Linie.
- Für Text und Zahlen gelten die Shopfarben und die Geist-Schriften.
  - Die Schriften liegen jetzt in `modellbahn.platform.fonts` und werden von Etiketten und
    Rechnungen gemeinsam genutzt.
- Lange Bestellungen laufen auf Folgeseiten weiter, mit Seitenzahl.

### Aussteller

- Der Aussteller ist das Impressum (`MB_IMPRINT_*`) mit `MB_IMPRINT_VAT_ID` oder, solange
  es keine USt-IdNr. gibt, `MB_IMPRINT_TAX_NUMBER`.
- Fehlt beides oder ist das Impressum unvollständig, stellt der Shop keine Rechnungen aus.
  Er ist dann trotzdem voll betriebsfähig.
  - `GET /admin/shipping/setup` meldet `issues_invoices: false`.
  - Das Bestellpult sagt bei versendeten Bestellungen, was fehlt.
  - Eine später eingetragene Steuernummer wirkt erst für Bestellungen, die danach
    versendet werden.

### Abrufen

- Die Bestellung (`OrderOut.invoices`) listet Rechnungen und Korrekturen.
- Das Stellwerk holt das PDF über `GET /admin/orders/{id}/invoices/{invoice_id}/document.pdf`,
  der Kunde über die Statusseite: `GET /store/orders/{token}/invoices/{invoice_id}/document.pdf`.

### Mails im Shop-Design

- Mit dem Anhang bekommen alle HTML-Mails das Erscheinungsbild des Shops:
  - Schriftzug als Text (Bilder blockieren viele Mailprogramme),
  - Mandarin-Linie und eine weiße Karte auf Sandgrund,
  - der Knopf in Mandarin.
- Die Textfassung bleibt unverändert.

## Folgen

- Die erste Rechnung entsteht erst nach dem Eintragen der Steuernummer. Johann trägt sie
  beim gesammelten Ausspielen in die `.env` ein, später die USt-IdNr.
- Die Datenbank wächst um etwa 30 KB je Rechnung. Bei hundert Bestellungen im Monat sind
  das weniger als 40 MB im Jahr. Die nächtliche Sicherung (ADR 0025) erfasst sie mit.
- Kleinunternehmer (§ 19 UStG) sind nicht vorgesehen: Die Rechnung weist immer 19 % aus,
  wie die Preise des Shops.
- Gutschriften für Wiederverkäufer oder Rechnungen ohne Versand (Messeverkauf) kommen
  später, falls sie gebraucht werden.
