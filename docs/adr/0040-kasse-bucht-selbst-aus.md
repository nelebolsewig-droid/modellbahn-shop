# ADR 0040: Kasse – SumUp-Verkäufe buchen sich selbst aus

Status: angenommen · 20.11.2026

## Kontext

Auf Messen kassiert adp-Modelle mit der SumUp-App (Kartenleser Solo, auch bar). Verkaufte
Stücke mussten danach zusätzlich im Stellwerk ausgebucht werden (Scanner, „Verkauft“).
Gewünscht: Was an der Kasse verkauft wird, ist im Lager automatisch eins weniger.

Was SumUp kann (geprüft am 20.11.2026 im Konto des Shops):

- Für Verkäufe der App gibt es **keinen Webhook**; Webhooks gibt es nur für
  Online-Checkouts (ADR 0019). Der Shop muss nachfragen.
- Die Transactions API (`/v2.1/merchants/{code}/transactions/history`) listet die
  Zahlungen. Verkäufe der App haben den Zahlungstyp `POS` (Karte) oder `CASH`; die
  Onlinezahlungen des Shops sind `ECOM` bzw. `APM` und bleiben außen vor.
- Die Einzelabfrage (`…/transactions?transaction_code=…`) nennt die verkauften Artikel:
  **nur Name, Menge und Preis**, keine Artikelnummer und keinen Barcode.
- Der Artikelkatalog in SumUp („Sammlung“, rund 350 Artikel) ist von Hand gepflegt, mit
  eigenen Namen. Auf der Messe im Oktober wurde meist nur ein Betrag eingetippt
  („Individueller Betrag“).

## Entscheidung

### Abholen

- Der Worker fragt **jede Minute** die erfolgreichen `POS`- und `CASH`-Zahlungen der
  letzten drei Tage ab (ein Kartenleser ohne Netz meldet spät). Jede Zahlung wird nur
  einmal geholt und ihre Zeilen gespeichert (`inventory.till_lines`, eindeutig je Beleg
  und Position); doppelte Abfragen schaden nicht. Eine Zeilensperre auf
  `inventory.till_state` verhindert, dass zwei Worker denselben Verkauf buchen.
- **Start ist der erste Lauf.** Ältere Verkäufe wurden von Hand ausgebucht und bleiben,
  wie sie sind.
- Ist SumUp nicht erreichbar oder lehnt der Schlüssel ab, steht der Grund im Stellwerk;
  der nächste Lauf versucht es wieder.
- An, sobald `MB_SUMUP_API_KEY` und `MB_SUMUP_MERCHANT_CODE` gesetzt sind; aus mit
  `MB_SUMUP_TILL=false`. Der Schlüssel braucht Lesezugriff auf Umsätze
  (`transactions.history`).

### Zuordnen: Kassenartikel → Ausführung

- Weil SumUp nur den Namen kennt, wird jeder **Name einmal** einer Ausführung zugeordnet
  (`inventory.till_items`; Groß-/Kleinschreibung und Leerzeichen zählen nicht).
  Alternativ „Kein Modell“ (Porto, Beschriftung): Solche Zeilen buchen nichts.
- Eine Zeile mit zugeordnetem Namen bucht die **ältesten freien Stücke** der Ausführung
  aus, Grund „Verkauft“, Notiz „SumUp-Kasse, Beleg …“, Preis je Stück aus der Kasse
  (brutto), Kanal **Messe** an einem Tag, an dem laut Messeliste eine Messe läuft,
  sonst **Laden**. So erscheint der Verkauf auf der Seite „Verkäufe“ (ADR 0039).
- Reservierte Stücke (für Onlinebestellungen) werden nicht genommen.

### Was liegen bleibt

Auf der Seite „Verkäufe“ zeigt das Feld **Kasse**, was niemand automatisch buchen kann:

- **Noch keinem Modell zugeordnet:** „Modell zuordnen“ bucht diese und alle wartenden
  Zeilen des Namens sofort aus.
- **Preis ohne Artikel** („Individueller Betrag“): von Hand ausbuchen, dann „Erledigt“.
- **Zu wenig im Lager:** gebucht wird, was frei ist; der Rest, sobald Stücke
  eingebucht werden (jeder Lauf versucht es wieder), oder von Hand und „Erledigt“.

Darüber steht, ob die Kasse verbunden ist, wann zuletzt abgeholt wurde und wie viele
Stücke sie heute selbst ausgebucht hat. Nur Inhaber und Mitarbeiter sehen das Feld.

## Folgen

- Migration 0028: `inventory.till_state`, `inventory.till_items`, `inventory.till_lines`.
- An der Kasse muss der Artikel angetippt oder gescannt werden; ein eingetippter Betrag
  bucht nichts aus. Wer an der Kasse verkauft, scannt das Stück **nicht zusätzlich** im
  Stellwerk aus.
- Eine Erstattung an der Kasse bucht nichts wieder ein (das Stück kommt nicht
  zwangsläufig zurück); das geschieht von Hand.
- Ersetzt man den SumUp-Katalog durch die Artikelliste des Shops
  (`/admin/catalog/articles.csv`), heißen die Kassenartikel wie im Shop, und mit den
  Barcodes auf den Etiketten wird an der Kasse gescannt statt gesucht.
