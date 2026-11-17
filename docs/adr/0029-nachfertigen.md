# ADR 0029: Nachfertigen für alle Modelle

Status: angenommen · 15.11.2026 · ändert die Entscheidungen 9 und 15 (ADR 0011, ADR 0013)

## Kontext

Bisher war eine Ausführung entweder *vorrätig* (ausverkauft, wenn das Regal leer ist) oder
*auf Bestellung* (`allow_backorder` mit einer Lieferzeit je Ausführung). Der Inhaber will,
dass jedes Modell über den Bestand hinaus bestellbar ist: Was fehlt, fertigt die Werkstatt.

- Dafür hätte man bei jeder Ausführung den Haken setzen und eine Lieferzeit eintragen
  müssen (Katalog → Modell → Maßstäbe).
- Der Shop schrieb dann „Wird für dich gefertigt“, auch wenn drei Stücke im Regal lagen.
  Das klang, als käme die ganze Menge aus der Fertigung.
- Eingangs- und Zahlungsmail sagten nicht, wann das Paket geht.
- Was die Werkstatt für bezahlte Bestellungen fertigen muss, stand nirgends beisammen.

## Entscheidung

### Nachfertigen ist die Regel

- **Eine Lieferzeit für den Shop:** `catalog.production_settings`, eine Zeile, zu Beginn
  2–4 Wochen. Lesen Inhaber und Mitarbeiter (`GET /admin/catalog/production`), ändern nur
  der Inhaber (`PUT`, Einstellungen → Lieferzeit).
- **Jede Ausführung wird nachgefertigt** (`allow_backorder`, jetzt Vorgabe), in der
  Lieferzeit des Shops. Ausnahmen je Ausführung:
  - **eigene Lieferzeit** (`lead_time_min/max_weeks` gesetzt);
  - **nicht nachfertigen** (`allow_backorder` aus: Einzelstück, ausgelaufenes Modell); eine
    eigene Lieferzeit gibt es dann nicht (Datenbankregel `lead_time_only_made_again`).
- **Beim Lesen bestimmt, nicht kopiert:** Die Lieferzeit einer Ausführung ohne eigene kommt
  in derselben Abfrage aus `production_settings` (`made_within()` im Katalogvertrag). Ändert
  der Inhaber sie, gilt das sofort für jede solche Ausführung, ohne Datenmigration, ohne
  Ereignis. Kopiert hätte jede Änderung alle Ausführungen umschreiben müssen und eigene
  Lieferzeiten nicht mehr von übernommenen unterschieden.
- `SaleVariant.lead_time_weeks` ist die wirksame Lieferzeit; `own_lead_time` sagt, ob sie
  der Ausführung gehört.
- **Migration 0020:** Jede Ausführung wird nachgefertigt. Wer auf Bestellung war, behält
  seine Lieferzeit als eigene. Lieferzeiten von Ausführungen, die nicht auf Bestellung waren,
  waren nie sichtbar oder wirksam; sie fallen weg, diese folgen der des Shops.
- **Im Stellwerk** wählt man je Ausführung „Standard-Lieferzeit (2–4 Wochen)“, „eigene
  Lieferzeit“ (beginnt bei der des Shops) oder „nicht nachfertigen“. „Neues Modell“ fragt
  nichts zusätzlich.

### Klare Worte im Shop

- **Artikel**, wenn das Regal knapp ist (bis 3 Stück) oder mehr gewünscht als da: „Nur noch
  3 Stück sofort lieferbar – weitere fertigen wir für dich (Lieferzeit 2–4 Wochen)“. Liegt
  nichts im Regal: „Wird für dich gefertigt · Lieferzeit 2–4 Wochen“.
- **Warenkorb:** „3 sofort lieferbar, 2 werden für dich gefertigt · Lieferzeit 2–4 Wochen“.
  Der Hinweis, dass alles zusammen in einem Paket geht, bleibt.
- **Kasse:** je Zeile, was gefertigt wird; ist alles vorrätig: „in der Regel 1–3 Werktage,
  nachdem deine Zahlung eingegangen ist“.
- **Mails:** Die Bestellung merkt sich die Lieferzeit der Kasse (`sales.orders.lead_time_*`,
  Migration 0021: die längste der gefertigten Zeilen). Eingangs- und Zahlungsmail sagen
  „in der Regel 1–3 Werktage …“ oder „Nicht alles ist vorrätig: Was fehlt, fertigen wir für
  dich. Wir schicken alles zusammen in einem Paket, voraussichtlich in 2–4 Wochen.“
- **Widerruf und AGB bleiben:** Nachgefertigte Modelle sind Serienmodelle, keine
  Anfertigung nach Kundenwunsch; das Widerrufsrecht gilt (§ 312g Abs. 2 Nr. 1 BGB greift
  nicht). AGB § 6 nennt die Lieferzeit am Artikel schon.

### Zu fertigen

- `GET /admin/inventory/stock/to-make` (Inhaber, Mitarbeiter): je Ausführung mit
  wartenden Stücken bezahlter Bestellungen Modell, Ausführung, Anzahl, Bestellungen mit
  Nummer und Datum, die älteste zuerst, dazu die Summe.
- Im Stellwerk unter Bestellungen neben „Zu versenden“: „Zu fertigen (3)“. Die Zahl steht
  auch im Menü neben „Bestellungen“. Packer sehen beides nicht.
- Eingebucht wird wie immer auf der Seite des Modells. Ein neues Stück bedient die älteste
  wartende Bestellung (ADR 0011); die Zeile schrumpft und verschwindet. Die Liste folgt den
  Ereignissen (Zahlung, Bestand) live, die Zahl im Menü jede Minute.

### eBay

- eBay bleibt beim Bestand: Die Lieferzeit des Shops erreicht eBay nicht.
- Über den Bestand hinaus (mit der eingestellten Stückzahl) bietet eBay nur Ausführungen
  mit **eigener** Lieferzeit an. Das sind genau die, die vor dieser Entscheidung auf
  Bestellung waren; für eBay ändert sich also nichts.

## Folgen

- Jedes Modell ist bestellbar, ohne dass jemand bei jeder Ausführung etwas einstellt.
- Eine Lieferzeit gilt für viele Ausführungen. Wer für eine eigene setzt, nimmt sie aus der
  Regel heraus und bietet sie damit auch auf eBay ohne Bestand an. Das sagt die
  eBay-Einrichtung.
- Lieferzeiten, die vorher auf Bestellung gesetzt waren (oft die damalige Vorgabe 1–2 Wochen),
  bleiben eigene. Sollen sie der des Shops folgen: beim Modell „Standard-Lieferzeit“ wählen.
- Bestand wird erst bei der Zahlung zugeteilt. Wird das Regal zwischen Kasse und Zahlung
  leer (gleichzeitig gekauft, oder Vorkasse mit bis zu zehn Tagen), sagten Eingangs- und
  Zahlungsmail „1–3 Werktage“. Deshalb: Meldet das Lager ein Stück als zu fertigen
  (`inventory.allocation.backordered`) und hat die Bestellung keine Lieferzeit, übernimmt sie
  die längste der wartenden Ausführungen (für „nicht nachfertigen“ die des Shops) und meldet
  `sales.order.delayed`. Der Kunde bekommt genau einmal „Kurze Info zu deiner Bestellung …“:
  was gefertigt wird und wann das Paket voraussichtlich geht. Hatte die Kasse schon eine
  Lieferzeit genannt, kommt keine Mail. Ist bis zum Versand der Mail alles gefertigt oder
  die Bestellung storniert, entfällt sie.
- Die Artikelliste für die Kasse (CSV) schreibt „vorrätig, sonst 2-4 Wochen“ oder
  „nur vorrätig“.
