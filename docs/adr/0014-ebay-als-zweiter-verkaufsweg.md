# ADR 0014: eBay als zweiter Verkaufsweg

Status: angenommen · 29.10.2026

## Kontext

adp-Modelle hat neben dem Shop bisher über Kleinanzeigen verkauft. Der Auftraggeber
möchte stattdessen **eBay** anbinden, und zwar so, dass der Shop die Angebote dort führt:
gleiche Texte, Fotos und Preise, ein gemeinsamer Bestand und die Bestellungen im selben
Lager- und Versandablauf.

Am 28.10.2026 entschieden:

- **Aufschlag** auf die Shop-Preise für eBays Gebühren: einstellbar, zum Start 0 %.
- **EAN:** „Nicht zutreffend“. Die EAN des Shops sind interne Nummern mit Präfix 2 für
  Scanner und Kasse (Entscheidung 2), keine GS1-Nummern, die eBay annimmt.
- **Modelle auf Bestellung** gehen auch auf eBay. Mit der Lieferzeit von 1 bis 2 Wochen
  (Entscheidung 15) passt das zu eBays Bearbeitungszeit von höchstens 10 Werktagen.

Am 29.10.2026 kam dazu: Auf dem eBay-Konto des Inhabers liegen schon **Angebote mit Fotos**
seiner Modelle. Sie sollen **übernommen** werden: Fotos, Titel und Preise kommen als Entwürfe in
den Katalog, und sobald das Angebot des Shops online geht, **endet das alte** (keine
Doppelangebote). Diese Bestandsübernahme folgt als eigener Schritt; dieses ADR legt die
Anbindung fest, auf der sie aufbaut.

## Entscheidung

### Ein eigenes Modul `marketplace`

eBay ist ein eigener Bounded Context mit eigenem Schema `marketplace` (Migration 0008).
Er spricht mit den anderen Modulen nur über deren Verträge:

- **Katalog:** `catalog.contracts.listings` liefert ein Produkt in einem Maßstab mit
  Texten, Maßen, Epochen, Fotos und Varianten.
- **Lager:** freie Stücke je Variante (`load_free_units`).
- **Medien:** die Bildgrößen; eBay bekommt die größte WebP-Größe als absolute Adresse.
- **Verkauf:** die Adressregel des Shops (`address_problem`) und der Versand einer
  Bestellung (`load_shipment`).

Hinter einer Anti-Corruption-Schicht (KONZEPT §2.6) steht der Port `EbayGateway`. Er
spricht eBays REST-APIs (OAuth, Identity, Account, Inventory, Fulfillment) und gibt nur
eigene, einfache Typen zurück. Was eBay Inventory Item, Item Group, Offer und Fulfillment
nennt, bleibt in `infrastructure/ebay.py`.

### Das Konto

- **Verbinden über eBays Zustimmungsseite (OAuth Authorization Code).** Der Shop
  schickt den Inhaber mit einem zufälligen `state` zu eBay. Gespeichert wird nur dessen
  SHA-256, 15 Minuten gültig und einmal verwendbar.
- **Rücksprung ohne Stellwerk-Cookie.** Das Stellwerk-Cookie ist `SameSite=Strict` und
  kommt beim Rücksprung von eBay nicht mit. Der Callback ist deshalb durch den `state`
  geschützt, nicht durch die Sitzung. Er antwortet mit einer kleinen Zwischenseite, die
  per Meta-Refresh ins Stellwerk weiterleitet; diese Navigation startet auf der eigenen
  Seite und trägt das Cookie wieder. Caddy schwärzt `code` und `state` in seinen Logs.
- **Tokens verschlüsselt (Fernet, `MB_EBAY_TOKEN_KEY`).** Das Zugriffstoken gilt zwei
  Stunden und wird fünf Minuten vor Ablauf mit dem Refresh-Token erneuert. Das
  Refresh-Token gilt rund 18 Monate. Lehnt eBay es ab, steht das Konto auf „abgelaufen“
  und der Inhaber verbindet neu.
- **Bereit sind Angebote erst, wenn die „Fahrstraße“ frei ist:** verbunden, je eine
  Grundsatz-Option für Versand, Zahlung und Rücknahme gewählt (eBays Business Policies)
  und der Versandort angelegt (`werkstatt`, aus der Impressumsadresse).
  - Gibt es von einer Art genau eine Option, wählt der Shop sie selbst.
  - Ein anderes eBay-Konto vergisst die Grundsätze und den Versandort des alten.

### Angebote

- **Ein Angebot je Produkt und Maßstab.** Bausatz und Fertigmodell in jeder Farbe sind
  seine Auswahlmöglichkeiten.
  - Eine Variante wird ein einfaches Angebot, mehrere eine Item Group, die sich in
    „Ausführung“ und, wo es Farben gibt, „Farbe“ unterscheidet. Der Bausatz heißt dort
    „Unlackiert“.
  - Schlüssel ist `MB-{Nummer}-{Maßstab}`, die SKUs sind die Artikelnummern.
  - Wechselt ein Angebot zwischen einer und mehreren Varianten, endet das alte und ein
    neues beginnt; eBay kann die Form nicht ändern.
- **Der Shop ist führend.** Auf eBay wird nichts von Hand bearbeitet. Jede Änderung macht
  die betroffenen Angebote fällig (`needs_sync`):
  - am Produkt (`ProductUpdated`, `…Published`, `…Archived`);
  - am Bestand (`StockChanged`);
  - an den Einstellungen und Kategorien.

  Der Worker gleicht jede Minute bis zu 25 fällige Angebote ab und schreibt sie als
  Ganzes neu. Eine Welle von Änderungen kostet so einen Abgleich. Im Stellwerk geht
  „Jetzt abgleichen“ sofort.
- **Was eBay erfährt:**
  - Titel aus Name, Maßstab, Ausführungen und Marke, höchstens 80 Zeichen; was nicht
    passt, entfällt von hinten.
  - Beschreibung als schlichtes HTML ohne Skripte, mit Ausführungen, Lieferzeit und
    Daten.
  - Merkmale: Marke, Maßstab (1:87), Spurweite (H0), Epoche, Vorbild.
  - Die Fotos des Maßstabs, das passende Foto jeder Variante zuerst.
  - Preis: Shop-Preis plus Aufschlag, kaufmännisch auf den Cent gerundet.
- **Stückzahl.**
  - Vorrätige Varianten: die freien Stücke im Lager.
  - Varianten auf Bestellung: mindestens die eingestellte Stückzahl (Vorgabe 3,
    höchstens 20), damit eBay sie auch ohne Bestand verkauft. Jeder Verkauf wird
    gefertigt.
- **Was nicht online gehen kann, kommt herunter, mit Grund.** Kein Foto, keine
  eBay-Kategorie, nicht im Shop oder keine Variante im Shop: Das Angebot endet und zeigt
  den Grund (Status „Wartet“). Ausverkauft und nichts auf Bestellung: Es pausiert und
  kommt mit neuem Bestand von selbst wieder.
- **eBay-Kategorien je Shop-Kategorie.** Der Inhaber trägt die Nummer einer
  eBay-Kategorie ein. Unterkategorien ohne eigene Nummer nehmen die ihrer
  Oberkategorie. Ein Katalog der eBay-Kategorien mit Suche ist nicht nötig.
- **Lehnt eBay ab, bleibt die alte Version online.** Status „Von eBay abgelehnt“ mit
  eBays Meldung.
- **Ist eBay nicht erreichbar** (Netz, 429, 5xx), bleibt das Angebot fällig. Der nächste
  Lauf versucht es wieder.

### Bestellungen

- **Abholen alle zwei Minuten.** Der Worker fragt eBay nach Bestellungen, die sich seit
  dem letzten Mal geändert haben. Er schaut zehn Minuten zurück, weil eBays
  Änderungszeiten nachlaufen können.
  - Eine neue **bezahlte** Bestellung wird als `MarketplaceOrder` gespeichert, wie eBay sie
    meldet.
  - Unbekannte Artikel oder eine Adresse, die der Shop nicht beliefert, ergeben „Nicht
    übernommen“ mit Grund.
- **Der Verkauf macht daraus eine bezahlte Shop-Bestellung** (`Order.import_paid`,
  Kanal `ebay`, Zahlungsanbieter `ebay`):
  - mit eBays Preisen und Versandkosten;
  - mit einer eigenen Bestellnummer `MB-…`;
  - die eBay-Bestellnummer steht in `external_ref` und ist je Kanal eindeutig.

  `OrderPlaced` und `OrderPaid` laufen wie bei jeder Bestellung: Das Lager teilt zu, die
  Werkstatt kommissioniert und versendet.
- **Keine Shop-Mails.** Der Käufer hört von eBay. Eine eBay-Bestellung wandert auch nie
  in ein Kundenkonto des Shops.
- **Versand geht zurück an eBay.** `OrderShipped` meldet Versanddienst (als eBay-Code,
  etwa `DEUTSCHE_POST`) und Sendungsnummer je Position. Scheitert die Meldung, steht der
  Grund an der Bestellung und „Versand erneut melden“ wiederholt sie.
- **Storniert wird auf eBay.** Der Shop kann eine eBay-Bestellung nicht selbst
  stornieren (`marketplace_order`, 409), denn das Geld liegt bei eBay. Meldet eBay die
  Stornierung, storniert der Shop mit Grund `by_marketplace`, ohne eigene Erstattung, und
  das Lager gibt die Stücke frei. War die Ware schon unterwegs, bleibt die Bestellung
  versendet; eBays Rückgabe übernimmt.

### Betriebsarten

`MB_EBAY_MODE` steuert die Betriebsart:

- **`off`**: Vorgabe; das Stellwerk zeigt nur einen Hinweis.
- **`test`**: der **eingebaute Testmarktplatz**, wie die Testzahlung (ADR 0009).
  - Verbinden springt direkt zum Callback.
  - Angebote „gehen online“ mit erfundenen Nummern.
  - Im Stellwerk kauft man als Käufer und storniert als Käufer; die Verkäufe liegen in
    `marketplace.test_sales`.
  - Die ganze Kette läuft ohne eBay-Schlüssel, im Smoke-Test und in der CI.
- **`sandbox`** und **`production`**: eBays APIs mit den Schlüsseln des Entwicklerkontos
  (`MB_EBAY_CLIENT_ID`, `MB_EBAY_CLIENT_SECRET`, `MB_EBAY_RU_NAME`).

Für Produktion gilt:

- Sie lässt nur `off` und `production` zu, damit Testverkäufe nie zwischen echten
  Bestellungen und in der Kommissionierung landen.
- Sie verlangt einen eigenen `MB_EBAY_TOKEN_KEY`.

## Folgen

- **Ein Bestand für zwei Verkaufswege.** Verkauft der Shop das letzte Stück, sinkt die
  Stückzahl auf eBay mit dem nächsten Abgleich, spätestens nach einer Minute. In dieser
  Minute kann eBay das Stück noch einmal verkaufen.
  - Bei Modellen auf Bestellung ist das kein Problem, es wird gefertigt.
  - Bei vorrätigen kann die zweite Bestellung zur Fertigung werden; das Lager führt sie
    als Rückstand.
- **Rechte:**
  - Der Inhaber verbindet und stellt ein.
  - Mitarbeiter bieten Produkte an und holen Bestellungen.
  - Packer sehen eBay nicht.
- **Noch in der Sandbox zu prüfen:**
  - ob eBay die WebP-Größen als Fotos annimmt (sonst bekommt das Medienmodul eine
    JPEG-Größe für eBay);
  - welche Fehlercodes `withdraw` für schon beendete Angebote liefert;
  - ob das Konto für Business Policies freigeschaltet ist.
- **Löschmeldungen:** eBay gibt die Produktions-Schlüssel nur frei, wenn der Shop eBays
  Meldungen über geschlossene Konten empfängt und die Käuferdaten löscht (ADR 0015).
- **Bestandsübernahme als nächster Schritt:**
  - Die laufenden Angebote des Inhabers lesen (Trading API `GetMyeBaySelling` und `GetItem`).
  - Daraus Katalog-Entwürfe mit Fotos machen.
  - Das alte Angebot beenden, sobald das neue online ist.
