# ADR 0023: DHL-Versandlabel aus dem Stellwerk

Status: angenommen · 09.11.2026

## Kontext

Bisher schrieb die Werkstatt jedes Paket im DHL-Geschäftskundenportal von Hand und tippte
die Sendungsnummer danach ins Stellwerk, damit sie in die Versandmail kommt. Die Adresse
stand also zweimal im Spiel, und ein Tippfehler in der Nummer erreichte den Kunden.

Die Werkstatt hat ein DHL-Geschäftskundenkonto mit Abrechnungsnummer und einen
Etikettendrucker für 100 × 150 mm. Verschickt wird DHL Paket in Deutschland und DHL Paket
International in die übrigen EU-Länder (ADR 0012).

DHL bietet dafür die „Parcel DE Shipping API“ (Version 2) an:
- Eine App im Entwicklerportal liefert den API-Schlüssel.
- Ein Systembenutzer des Geschäftskundenportals meldet sich mit Benutzer und Passwort an.
- Die Abrechnungsnummer hat 14 Ziffern: Kundennummer (EKP, 10 Ziffern), Verfahren (01 für
  DHL Paket, 53 für International) und Teilnahme (2 Ziffern).
- Eine Sandbox mit einem öffentlichen Testkunden erlaubt Versuche ohne echte Sendungen.

## Entscheidung

### Label buchen, drucken, stornieren

- **Ein Label je Bestellung:** Neue Tabelle `sales.shipping_labels` (Migration 0016).
  - Sie speichert Versanddienst, Produkt (`V01PAK` oder `V53WPAK`), DHLs Sendungsnummer,
    Gewicht, Druckformat, das PDF und den Zustand (`active`, `cancelled`).
  - Ein Teilindex lässt je Bestellung höchstens ein gültiges Label zu.
  - Stornierte Labels bleiben für die Nachvollziehbarkeit.
- **Wann:** Nur eine bezahlte Bestellung bekommt ein Label. Im Bestellpult erscheint es,
  sobald alles kommissioniert ist, oberhalb von „Als versendet melden“.
- **Buchen:** Der Packer wiegt das Paket und bucht (`bookShippingLabel`, auch für Packer).
  - Vorgeschlagen ist `MB_DHL_DEFAULT_WEIGHT_G` (1 kg).
  - Erlaubt sind 10 g bis 31,5 kg; das prüfen Domäne, API, Formular und Datenbank.
  - Das Produkt folgt aus dem Lieferland: DHL Paket in Deutschland, sonst International.
  - Der Absender ist der Anbieter aus dem Impressum (`MB_IMPRINT_*`). Ohne vollständiges
    Impressum bucht das Stellwerk keine echten Labels.
- **Drucken:** `GET /admin/orders/{id}/shipping-label.pdf` liefert das PDF, im Browser
  geöffnet und dort an den Etikettendrucker geschickt.
  - Druckformat ist `MB_DHL_PRINT_FORMAT`, vorgegeben `910-300-400`: DHLs Thermoetikett
    103 × 150 mm, das nächste zu den 100 × 150 mm der Rolle.
  - Die Sandbox-Prüfung misst die Seite des PDFs, das DHL schickt (siehe unten).
- **Versenden:** „Als versendet melden“ übernimmt Versanddienst und Sendungsnummer des
  gültigen Labels, wenn keine Nummer eingetippt ist.
  - Die Versandmail nennt die Nummer mit dem Verfolgungslink von DHL.
  - Eine eingetippte Nummer hat Vorrang (z. B. ein anderer Versanddienst).
- **Stornieren:** Ein falsches Label (Gewicht, Adresse) storniert der Packer bei DHL
  (`cancelShippingLabel`) und bucht ein neues.
  - Nach dem Versand nicht mehr: Das Paket ist mit diesem Label unterwegs.
  - Wird die Bestellung storniert, storniert der Worker ihr Label bei DHL
    (`sales.order.cancelled`). Ist DHL nicht erreichbar, versucht es die Outbox wieder;
    kennt DHL die Sendung nicht mehr, gilt das Label als storniert.

### Anbindung

- **Schnittstelle `Carrier`** in der Anwendungsschicht des Verkaufs, mit drei Adaptern:
  - `DhlCarrier`: Parcel DE Shipping API v2 mit `dhl-api-key` und Basic-Auth. Nur diese
    Datei kennt DHLs Datenmodell.
  - `TestCarrier`: zeichnet das Label selbst, mit Code 128 und „TESTLABEL“ durchgestrichen.
    Nichts verlässt den Rechner.
  - `NoCarrier`: kein Versanddienst; die Werkstatt tippt die Nummer wie bisher.
- **Modus `MB_DHL_MODE`:**
  - `test` für die Entwicklung.
  - `sandbox` mit DHLs Testkunden; braucht nur den API-Schlüssel.
  - `production` mit `MB_DHL_API_KEY`, `MB_DHL_USERNAME`, `MB_DHL_PASSWORD` und
    `MB_DHL_EKP`, dazu die Teilnahmen `MB_DHL_PARTICIPATION_NATIONAL` und
    `MB_DHL_PARTICIPATION_INTERNATIONAL` (je 2 Ziffern, meist `01`).
  - `off`: keine Labels.
  - Der echte Betrieb erlaubt nur `off` und `production`. Testlabels würden sonst auf
    echte Pakete geklebt, und DHL beförderte sie nicht.
- **Fehler:** DHLs Ablehnung (4xx) kommt als `carrier_rejected` (409) mit DHLs eigenen
  Worten im `detail`, z. B. die beanstandete Postleitzahl; das Stellwerk zeigt sie unter
  der deutschen Meldung. Ist DHL nicht erreichbar oder gestört (5xx), meldet die API
  `carrier_unavailable` (503); gebucht ist dann nichts.
- **Adresse:** DHL will Straße und Hausnummer getrennt und das Land als ISO-Alpha-3.
  `split_street` trennt die Hausnummer am Ende ab („Bahnhofstraße 12a“, „Am Hang 3-5“);
  ohne erkennbare Nummer bleibt alles in der Straße.
- **`GET /admin/shipping/setup`** sagt dem Stellwerk, ob es Labels bucht, mit welchem
  Versanddienst und welchem Vorschlagsgewicht.

### Prüfen, bevor es zählt

- **`make dhl-check`** (`cli dhl-check`) lässt DHL je eine Probesendung im Inland und nach
  Österreich prüfen (`validate=true`). Dabei entsteht kein Label. Der Befehl zeigt DHLs
  Antwort im Wortlaut, von der Kundennummer nur die letzten Ziffern.
  - Ohne Zusatz prüft er das Geschäftskundenkonto, auch solange `MB_DHL_MODE` noch `off`
    ist. So lässt sich der Zugang prüfen, bevor das Stellwerk damit bucht.
  - `make dhl-check SANDBOX=1` prüft in DHLs Sandbox als DHLs Testkunde, bucht dort ein
    Testlabel, misst seine Seite und storniert es wieder. Das geht auch auf dem
    Live-Server, ohne den Modus des Shops zu ändern.
- **Einrichtungsskript:** Stufe „DHL-Versandlabels“ fragt API-Schlüssel, Systembenutzer,
  Passwort, EKP und Teilnahmen ab. Eingeschaltet wird erst, wenn die Prüfung bestanden ist.

## Folgen

- Die Adresse kommt nur noch aus der Bestellung; die Sendungsnummer erreicht den Kunden
  ohne Abtippen und mit Verfolgungslink.
- Die Labels liegen als PDF in der Datenbank und kommen mit der nächtlichen Sicherung mit.
- Zugangsdaten stehen nur in `.env` auf dem Server: nie im Repository, in Mails oder im
  Laufzettel.
- eBay-Bestellungen bekommen ihr Label genauso; die Nummer geht wie bisher an eBay zurück
  (ADR 0014).
- Offen: Warenpost, Retourenlabels und Zollangaben für Länder außerhalb der EU.
