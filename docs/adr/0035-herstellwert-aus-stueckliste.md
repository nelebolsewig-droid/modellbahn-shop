# ADR 0035: Herstellwert aus Stückliste und Materialpreis

Status: angenommen · 18.11.2026 · ergänzt ADR 0017 (Fertigung) und den Lagerwert (#46)

## Kontext

Das Lager zeigt seit #46 den Warenwert zum heutigen Shoppreis. Gewünscht ist daneben der
Herstellwert: was die Modelle auf den Regalen gekostet haben. Die Herstellkosten stehen
heute in der Druckdatei des Slicers; sie bei jedem Modell von Hand einzutragen ist
umständlich und veraltet, sobald sich ein Teil oder der Harzpreis ändert.

Das System weiß schon fast alles dafür: Jedes Teil trägt seine Materialmenge (ml Resin
oder g Filament, Stützen eingeschlossen, ADR 0017), jedes Produkt in einem Maßstab hat
eine Stückliste. Es fehlt nur, was das Material kostet.

## Entscheidung

- **Ein Material hat einen Preis**: brutto in Cent je Liter Resin oder je Kilogramm
  Filament (`manufacturing.materials.price_cents`, leer = unbekannt). Er wird einmal
  je Material gepflegt („Teile & Material“, Knopf „Preis“).
  - `PUT /materials/{id}` ohne `price_cents` lässt den Preis stehen (der Knopf
    „Archivieren“ schickt ihn nicht mit); `null` löscht ihn.
- **Ein Bausatz kostet** die Summe über seine Stückliste: Menge × Material je Teil ×
  Preis ÷ 1000 (`kit_material_cost`, rein im Fachmodell). Bausatz und Fertigmodell teilen
  die Stückliste (ADR 0017) und kosten daher gleich viel Material.
- **Nichts Halbes:** Fehlt einem Teil die Menge oder seinem Material der Preis, oder hat das
  Produkt keine Stückliste, ist der Bausatz *unbekannt*. Der Lagerwert zählt solche Stücke
  gesondert und nennt sie, statt mit einer zu kleinen Summe zu täuschen.
- **Im Lager** (`GET /inventory/stock/value`): `cost_cents` (Herstellwert der Stücke mit
  bekannten Kosten), `cost_pieces`, `cost_value_cents` (deren Verkaufswert, damit der
  Anteil „x % vom Verkaufswert“ Gleiches mit Gleichem vergleicht), dazu je Ausführung,
  Maßstab und Modell.
- **Der Wert ist nur Material**, wie die Kostenangabe des Slicers. Lack, Arbeitszeit,
  Strom und Fehldrucke stecken nicht darin.

## Folgen

- Ein neuer Harzpreis wirkt sofort auf alle Modelle; nichts wird gespeichert, was sich
  ableiten lässt.
- Nächster Schritt: Die Druckdatei am Teil hochladen und Materialmenge und Druckzeit
  daraus lesen, damit auch die Menge je Teil nicht mehr getippt werden muss. Das Format
  hängt vom Slicer der Werkstatt ab und folgt in einem eigenen ADR.
