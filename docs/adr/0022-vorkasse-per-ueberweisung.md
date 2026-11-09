# ADR 0022: Vorkasse per Überweisung

Status: angenommen · 09.11.2026

## Kontext

Bisher nahm der Shop Zahlungen nur über SumUp an (ADR 0019): Karte, Apple Pay, Google Pay
und, je nach SumUp-Konto, PayPal. Viele Modellbahner zahlen lieber per Überweisung, und
eine Überweisung kostet den Shop keine Gebühr. Einen Zahlungsdienstleister braucht sie
nicht: Das Geld kommt direkt auf das Konto der Werkstatt.

Dafür muss der Shop selbst leisten, was SumUp sonst tut:
- dem Kunden sagen, wohin er was überweist;
- die Zahlung der richtigen Bestellung zuordnen;
- Geld zurückgeben, wenn eine Bestellung storniert oder widerrufen wird.

Ohne Zugriff auf das Bankkonto bucht der Shop den Eingang nicht selbst, sondern die
Werkstatt nach einem Blick in den Kontoauszug.

## Entscheidung

### Angebot und Konfiguration

- **Bankverbindung nur in der Konfiguration:** `MB_BANK_ACCOUNT_HOLDER`, `MB_BANK_IBAN`,
  optional `MB_BANK_BIC` und `MB_BANK_NAME`.
  - Vorkasse ist angeboten, sobald Kontoinhaber und IBAN gesetzt sind; beide gehören
    zusammen.
  - Die IBAN wird beim Start geprüft (Format und Prüfziffer, ISO 13616), ebenso die BIC.
  - Das Beispielkonto aus `.env.example` verweigert der echte Betrieb.
  - Das Einrichtungsskript fragt die Verbindung in einer eigenen, optionalen Stufe ab und
    prüft die IBAN, bevor es sie speichert.
- **Zahlungsarten:** `GET /store/payment-provider` meldet zusätzlich `bank_transfer`.
  Shop, Warenkorb und AGB nennen Vorkasse dann als zweite Zahlungsart.

### Ablauf

- **Wahl auf der Bezahlseite:** Der Kunde wählt dort zwischen SumUp und „Vorkasse per
  Überweisung“ (`payOrder` mit `method: bank_transfer`).
  - Es entsteht eine offene Zahlung des Anbieters `bank_transfer`, ohne Bezahlseite; ihre
    Referenz ist die Bestellnummer.
  - Wer von einer offenen SumUp-Seite zur Überweisung wechselt, dem schließt der Shop die
    SumUp-Seite vorher. Hat der Kunde dort doch bezahlt, gilt das.
  - Eine Bestellung, die auf eine Überweisung wartet, bleibt dabei; sie wechselt nicht
    zurück zu SumUp.
- **Frist zehn Tage statt 24 Stunden:** Eine Überweisung dauert ein bis zwei Werktage und
  wird nicht sofort ausgeführt.
  - `payment_due_at` liegt bei Vorkasse zehn Tage nach der Bestellung.
  - Danach storniert der Worker die Bestellung wie jede überfällige, mit eigenem Text in
    der Stornomail.
  - Die Suche nach überfälligen Bestellungen lässt Vorkasse-Bestellungen bis dahin aus, damit
    sie die Charge der 24-Stunden-Bestellungen nicht füllen.
  - An sein Angebot ist der Kunde bei Vorkasse zehn Tage gebunden (AGB § 4 Abs. 5).
- **Was zu überweisen ist:** Die Bestellung trägt `bank_transfer` mit Empfänger, IBAN (in
  Vierergruppen), BIC, Bank, Betrag, Verwendungszweck und Frist.
  - Bezahlseite und Bestellübersicht zeigen das mit Kopierknöpfen.
  - Der Kunde bekommt dieselben Angaben per E-Mail (`sales.order.bank_transfer_chosen`).
  - Verwendungszweck ist nur die Bestellnummer, damit die Zuordnung im Kontoauszug
    eindeutig ist.
- **GiroCode:** `GET /store/orders/{token}/girocode.svg` liefert den EPC-QR-Code (EPC069-12,
  Version 002, UTF-8, Fehlerkorrektur M). Banking-Apps füllen damit die Überweisung aus.
  - Erzeugt wird er im Backend mit `segno`.
  - Es gibt ihn nur, solange die Bestellung auf die Überweisung wartet; sonst 404.
- **Zahlungseingang buchen:** Im Stellwerk zeigt das Bestellpult bei einer wartenden
  Überweisung Verwendungszweck, Betrag und Frist und den Knopf „Überweisung eingegangen“
  (`confirmBankTransfer`, für Inhaber und Mitarbeiter).
  - Danach ist die Bestellung bezahlt wie nach SumUp: Bestätigungsmail, Zuteilung,
    Kommissionieren.

### Geld zurück

- **Rücküberweisung von Hand:** Storno, Teilerstattung und Widerruf fragen bei einer
  Überweisung keinen Zahlungsdienst. Der Shop vermerkt die Erstattung (wie „von Hand
  erstattet“ bei SumUp, ADR 0019).
  - Der Kunde erfährt per E-Mail, dass das Geld auf das Konto zurückkommt, von dem es
    kam.
  - Die Werkstatt bekommt an `MB_IMPRINT_EMAIL` eine Aufgabe: Betrag, Bestellung, Name
    und der Hinweis, die IBAN aus dem Kontoauszug zu nehmen.
  - Die Events `sales.order.cancelled` und `sales.order.refunded` tragen dafür
    `refund_by_transfer` bzw. `by_transfer`, das Storno-Event auch den Betrag.
- **Geld nach dem Storno:** Kommt eine Überweisung erst nach der Frist, sieht die Werkstatt
  sie im Kontoauszug zu einer stornierten Bestellung und überweist sie zurück. Der Shop
  kennt diesen Eingang nicht.

### Datenbank

- **Migration 0015:** Die Regel „offene Zahlung hat eine Bezahlseite“
  (`ck_payments_checkout_url`) gilt nicht für `bank_transfer`.
  - Beim Zurückrollen gelten noch wartende Überweisungen als gescheitert.

## Folgen

- Zwei Zahlungsarten nebeneinander, ohne einen zweiten Zahlungsdienst und ohne Gebühren für
  Überweisungen.
- Der Zahlungseingang hängt an einem Menschen: Ohne Blick ins Konto bleibt eine bezahlte
  Bestellung bis zur Buchung offen. Wird nichts gebucht, storniert der Worker sie nach zehn
  Tagen.
  - Später kann ein Kontoabruf (FinTS oder die API der Bank) das Buchen übernehmen.
- Rückzahlungen sind Handarbeit; die Aufgabe per E-Mail sorgt dafür, dass keine vergessen
  wird.
- Die Datenschutzerklärung nennt die Daten, die mit einer Überweisung kommen: Name, IBAN,
  Betrag, Verwendungszweck (Art. 6 Abs. 1 lit. b und c DSGVO).
