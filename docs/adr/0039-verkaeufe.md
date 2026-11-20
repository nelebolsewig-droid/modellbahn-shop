# ADR 0039: Verkäufe – alle Verkäufe mit Umsatz, auch von der Messe

Status: angenommen · 20.11.2026

## Kontext

Auf Messen verkauft adp-Modelle direkt vom Stand. Die verkauften Stücke werden im
Stellwerk ausgebucht (Scanner, Modus „Ausbuchen“, Grund „Verkauft“). Dabei hielt das
System nur fest, *dass* ein Stück verkauft wurde, nicht *wo* und *für wie viel*. Eine
Übersicht, was an einem Messetag (oder in einem Monat) über alle Wege eingenommen wurde,
gab es nicht: Onlinebestellungen standen nur in der Bestellliste, Messeverkäufe nirgends.

## Entscheidung

### Was beim Ausbuchen als verkauft festgehalten wird

- Ein Stück mit Grund „Verkauft“ bekommt einen **Verkaufskanal** (Messe, Laden, Privat,
  Sonstiges) und einen **Verkaufspreis** (brutto, je Stück). Beides ist freiwillig.
  - Andere Gründe (beschädigt, fehlt, Versehen) tragen keinen Verkauf; die Datenbank
    erzwingt das (`ck_units_sale_when_sold`).
  - Wieder einbuchen oder ein zurückgenommener Scan löschen den Verkauf mit dem Grund.
- Die Dialoge (Stück, mehrere Stücke, Bestand eines Modells) fragen „Wo verkauft?“ mit
  vier großen Feldern und den Preis, **vorbelegt mit dem Shoppreis**.
- Der Scanner fragt nur den Kanal (gemerkt auf dem Gerät, am Anfang „Messe“), keinen
  Preis: Am Stand zählt jede Sekunde. Der Preis wird danach in „Verkäufe“ eingetragen.
- Ohne eingetragenen Preis zählt der **heutige Shoppreis**, sichtbar markiert
  („Shoppreis“). So stimmt die Summe ungefähr sofort und genau, sobald jemand nachträgt.
- Nachtragen: `PUT /admin/inventory/units/{code}/sale`, nur für Stücke mit Grund
  „Verkauft“. Das ist keine Lagerbewegung; das Journal bleibt, wie es ist.

### Die Übersicht „Verkäufe“ (`/admin/verkaeufe`)

- `GET /admin/sales/report?start&end` liefert alle Verkäufe zwischen zwei Shop-Tagen
  (Europe/Berlin, höchstens 366 Tage), neueste zuerst:
  - **Onlinebestellungen** (Shop und eBay) mit ihren Zeilen am Tag der Zahlung; storniert
    zählt nicht. Teilerstattungen werden (noch) nicht abgezogen.
  - **Stücke außer Haus** am Tag des letzten Ausbuchens; der Verkaufsbereich liest sie
    über den Vertrag `inventory.contracts.sales`, die Namen über den Katalog.
- Die Seite zählt im Browser zusammen: Umsatz, Stück, Verkäufe, Ø je Stück, Anteile je
  Kanal als ein Balken, Verlauf je Tag (bis 31 Tage, sonst je Monat), darunter jeder
  Verkauf mit „Preis eintragen“. Filter je Kanal, Zeiträume als Knöpfe (Heute, Gestern,
  7/30 Tage, Monat, Jahr, eigener) und **laufende oder kürzliche Messen** aus der
  Messeliste als eigener Knopf mit ihrem Zeitraum.
- Sie lädt jede Minute neu: Wer im Büro schaut, sieht die Messe mitlaufen.
- Nur Inhaber und Mitarbeiter (wie Stornieren und Erstatten); Packer sehen keinen Umsatz.

## Folgen

- Migration 0027: `inventory.units.sale_channel`, `inventory.units.sale_price_cents`.
- Stücke, die vor dieser Änderung als verkauft ausgebucht wurden, erscheinen mit „Ohne
  Angabe“ und Shoppreis; Kanal und Preis lassen sich nachtragen.
- Messeverkäufe sind keine Bestellungen: keine Rechnung, keine Mail, keine Kundendaten.
  Eine Barkasse oder Kassenbuchführung ersetzt die Übersicht nicht.
