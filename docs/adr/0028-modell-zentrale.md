# ADR 0028: Das Modell im Mittelpunkt

Status: angenommen · 15.11.2026 · ändert die Navigation aus ADR 0026

## Kontext

Seit ADR 0027 nennt ein Etikett das Modell, nicht das Stück. Das Stellwerk war aber noch
um einzelne Stücke gebaut:

- **Viele Stellen für eine Sache:** Katalog, Erfassen, Lager mit Bestandsliste und
  Platzbaum, Stücke-Liste, Unverbucht, Inventur. Wer wissen wollte, wie viele Kipper wo
  liegen, sprang zwischen drei Seiten.
- **Zwischenschritte:** Ein Modell anlegen hieß Schnellerfassung, dann Katalog für weitere
  Ausführungen, dann Lager für Stücke. Ein Regal anlegen hieß Lager, Regal, jedes Fach
  einzeln, jedes Etikett einzeln.
- **Zählen Stück für Stück:** Die Inventur hakte Stücke nach ihrem Code ab. Modell-Etiketten
  tragen keinen Code eines Stücks mehr.
- **Versand nur nach dem Scannen:** Ein Paket ging erst hinaus, wenn jedes Stück per Scan
  kommissioniert war, auch wenn der Packer es längst in der Hand hatte.

## Entscheidung

### Navigation

- **Jeden Tag:** Modelle, Bestellungen, Scannen, Lager; auf dem Handy die untere Leiste
  mit Scannen in der Mitte.
- **Danach:** Fertigung, Messen, eBay, Einstellungen; die Übersicht hinter „Mehr“ und hinter
  dem Namen des Stellwerks. Packer sehen Bestellungen, Scannen, Lager und unter „Mehr“
  Übersicht und Fertigung (der Katalog bleibt für Inhaber und Mitarbeiter).
- **Adressen:** `/admin/katalog` wird `/admin/modelle`, die Schnellerfassung wird
  `/admin/modelle/neu`, Kategorien und Maßstäbe liegen unter `/admin/einstellungen/…`. Die
  alten Adressen leiten dauerhaft weiter (`next.config.ts`).
- „Erfassen“, „Stücke“ und „Unverbucht“ stehen in keinem Menü mehr. Die Listen der Stücke
  bleiben erreichbar (Lager, Seite eines Stücks).

### Die Liste der Modelle

- Je Zeile: Foto, Name, Stand (Im Shop, Entwurf, Archiviert, dazu „eBay“ bei einem aktiven
  Angebot), freie und reservierte Stücke und die Plätze („7 · Regal 2, Boden 3“).
- Suche, Filter „Entwürfe“ und „Ohne Bestand“, oben groß „Neues Modell“.
- Der Bestand kommt aus `GET /stock/products`, eBay aus der ersten Seite der Angebote; ist
  eBay nicht verbunden, fehlt die Marke ohne Fehlermeldung.

### Die Seite eines Modells

1. **Kopf:** Foto, Name, Stand, Preis, „Im Shop ansehen“.
2. **Bestand:** je Ausführung die Plätze mit freien und reservierten Stücken. Einbuchen
   (Anzahl, Platz, „Etiketten drucken“), Ausbuchen (Anzahl, Grund, Platz), Umlagern (Anzahl,
   von, nach), Etiketten drucken, Zählen (je Zeile die gezählte Zahl; der Unterschied wird
   gebucht).
3. **Bearbeiten:** die bisherigen Abschnitte (Fotos, Maßstäbe und Ausführungen, Beschreibung,
   Shop, eBay, Stückliste), zugeklappt.
4. **Verlauf:** die Buchungen des Modells, je Buchung eine Zeile: wann, wer, ±Anzahl, Platz
   (`GET /stock/history`, Journalzeilen gleicher Zeit, Person, Art und Strecke zusammen).

### Neues Modell in vier Schritten

- Fürs Handy, ersetzt Erfassen und die Schnellerfassung:
  1. Name, Kategorie, Fotos;
  2. Maßstab, Ausführungen, Farben, Preis;
  3. Bestand: Anzahl und Platz je Ausführung (überspringbar);
  4. Etiketten (Anzahl vorbelegt) und „Gleich im Shop zeigen“ (vorgewählt mit Foto und Preis).
- Am Ende steht die Seite des Modells.
- **Keine neuen Endpunkte:** je Ausführung ein `createQuickEntry` (der erste legt das Modell
  an, mit dem ersten Foto), weitere Fotos mit `attachProductImage`, Stücke mit `POST /units`,
  dann `publishProduct`.

### Bestand nach Anzahl (Backend)

Neu im Lager-Modul, `StockService`:

| Methode | Pfad | Was |
| --- | --- | --- |
| GET | `/stock/products` | je Modell frei, reserviert, unverbucht, wartend, Plätze |
| GET | `/stock/places` | je Ausführung und Platz frei und reserviert; `product_id` oder `location_code` |
| GET | `/stock/history` | Verlauf eines Modells, gruppiert |
| POST | `/stock/moves` | `{variant_id, from_location, to_location, quantity}` |
| POST | `/stock/scraps` | `{variant_id, location_code?, quantity, reason, note}` |
| POST | `/stock/counts` | `{lines: [{variant_id, location_code, expected, counted}]}` |

- **Wer:** Lesen alle Mitarbeiter (die Lagerseite ist für Packer da), Buchen Inhaber und
  Mitarbeiter.
- **Wie:** Alles oder nichts, eine Transaktion. Die Stücke werden auf einmal nach Kennung
  gesperrt. Journal und `inventory.stock.changed` je Stück, wie beim Scannen.
- **Umlagern** nimmt die ältesten Stücke am Platz, reservierte behalten ihre Bestellung;
  liegen weniger dort, 409 `not_enough_pieces`.
- **Ausbuchen** nur freie Stücke; zu wenige: 409 `not_enough_free`.
- **Zählen:**
  - Fehlende Stücke gehen mit Grund `missing` hinaus, nur freie. Bräuchte es reservierte,
    bucht die Zählung nichts (409 `count_takes_reserved`, `detail` nennt die Zeilen).
  - Zusätzliche Stücke werden neu im Platz eingebucht und bedienen zuerst wartende
    Bestellungen.
  - Stimmt `expected` nicht mehr (inzwischen gebucht), 409 `stocktake_outdated`.
- Die Inventur Stück für Stück (`POST /locations/{code}/stocktakes`) und ihre Oberfläche
  entfallen.

### Lager: Regale und Böden

- Die Lagerseite zeigt Regale, darin die Böden, auf jedem die Modelle mit Anzahl, verlinkt
  zum Modell. Plätze außerhalb von Regalen (Packtisch) stehen unter „Weitere Plätze“.
- **Neues Regal** in einem Schritt (`POST /locations/shelves`, Name und 0 bis 20 Böden):
  - legt das Lager selbst an, falls es keins gibt (`LAGER`, unsichtbar);
  - Regal `R01`, `R02` …, ohne Namen „Regal N“; Böden `R01-B01` … mit den Namen
    „Boden 1“ … „Boden N“;
  - danach alle Etiketten auf einmal. Ein Boden-Etikett nennt sein Regal
    („Regal 1 · Boden 3“).
- **Ein Regal ohne Böden** nimmt selbst Ware auf. Der Baum sagt es (`holds_goods`), ebenso
  jede Prüfung beim Buchen. Einen Boden unter ein Regal mit Ware zu hängen, lehnt der
  Server ab (`location_not_empty`).
- Jeder Platz hat einen Namen für Menschen (`place`: „Regal 2, Boden 3“), in Baum,
  Bestand, Verlauf und Pickliste.
- Bestehende Lager, Fächer, Boxen und Ablagen funktionieren weiter. Lager oder Box einzeln
  anzulegen, bietet das Stellwerk nicht mehr an.
- **Zählen je Platz:** die Modelle dort mit der erwarteten Zahl, die gezählte eintragen,
  buchen über `/stock/counts`.
- **Alter Bestand:** Solange unverbuchte Stücke aus dem alten Ablauf existieren, steht ein
  Hinweis mit „Alle als Versehen ausbuchen“.

### Versand ohne Scannen

- `OrderService.ship` verlangt nicht mehr jedes Stück kommissioniert. Eine bezahlte
  Bestellung geht hinaus, sobald jedes Stück einen Platz hat; das Lager kommissioniert die
  reservierten beim Versand selbst und bucht sie aus.
- Wartet ein Stück noch auf die Fertigung, lehnt der Server ab: 409 `order_pieces_missing`,
  `detail` nennt die Modelle (ersetzt `order_not_picked`).
- **„Versandlabel drucken“** (`POST /orders/{id}/shipping-label` mit `ship: true`) bucht das
  DHL-Label und versendet die Bestellung in einer Transaktion; die Versandmail trägt die
  Sendungsnummer. Fehlt ein Stück, wird DHL gar nicht erst gefragt; lehnt DHL ab, geht
  nichts hinaus.
- Scannen beim Kommissionieren bleibt möglich, ist aber freiwillig. Die Packansicht nennt je
  Stück den Platz („Regal 2, Boden 3“).

## Folgen

- Ein Modell ist eine Seite: was es ist, wie viele wo liegen, was damit geschah. Die
  meisten Buchungen sind zwei Taps.
- Packer sehen keine Modelle-Seite, weil der Katalog Inhabern und Mitarbeitern gehört; sie
  finden die Modelle über das Lager und die Bestellungen.
- **Bewusst offen:**
  - Zwischen der Prüfung beim Versand und der Buchung im Lager (der Worker hört
    `sales.order.shipped`) kann ein reserviertes Stück ausgebucht werden. Dann ist das Paket
    versendet, das Lager vermerkt das fehlende Stück im Log
    (`inventory.ship.piece_without_unit`); eine Zählung stellt es richtig.
  - Die eBay-Marke in der Liste kennt nur die ersten 100 Angebote.
- Smoke-Test: Er prüft kein „Versand vor dem Kommissionieren“ mehr; das Kommissionieren
  per Scan bleibt darin.
