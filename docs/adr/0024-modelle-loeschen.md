# ADR 0024: Modelle endgültig löschen

Status: angenommen · 11.11.2026

## Kontext

Bisher ließ sich nur ein Entwurf löschen, der nie im Shop war (`product_not_deletable`).
Zum Ausprobieren angelegte Testmodelle wurden aber veröffentlicht, mit Etiketten erfasst
oder testweise bestellt. Archivieren nahm sie aus dem Shop, im Stellwerk blieben sie
für immer.

Die Leitlinie „Geschäftsvorfälle sind unveränderlich“ (KONZEPT, Abschnitt 1) sagt:
Bestellungen, Zahlungen und Lagerbuchungen werden nie gelöscht. Ein Testmodell mit
erfassten Stücken hat aber Lagerbuchungen.

## Entscheidung

### Wann ein Modell gelöscht werden kann

- **Nur außerhalb des Shops:** Ein Entwurf oder ein archiviertes Modell lässt sich löschen.
  Ein Modell im Shop wird zuerst archiviert (`product_not_deletable`). Das nimmt es auch
  von eBay: Der Abgleich beendet seine Angebote.
- **Was das Modell festhält (409):**
  - `product_in_open_orders`: Eine Bestellung, die auf Zahlung oder Versand wartet,
    enthält das Modell. Das `detail` nennt die Bestellnummern. Nach Storno oder Versand
    hält sie es nicht mehr fest.
  - `product_has_history`: Ein Stück wurde reserviert, kommissioniert, versendet oder
    montiert. Seine Buchungen belegen einen Verkauf oder eine Montage und bleiben. Das
    Modell bleibt deshalb archiviert.
  - `product_on_marketplace`: Ein eBay-Angebot läuft noch oder wird gerade beendet.
  - `product_scale_has_bom` wie bisher: Eine Stückliste der Fertigung hängt an einem
    Maßstab.

### Was mitgelöscht wird

Das alles geschieht in einer Transaktion, unter Sperre der Produktzeile:

- Maßstäbe, Varianten, Epochen und die Zuordnung der Galerie. Die Fotos selbst bleiben in
  der Medienbibliothek.
- **Stücke, die die Werkstatt nie verlassen haben** (etikettiert, im Lager, verschrottet)
  samt ihren Lagerbuchungen. Ihre Etiketten gelten danach nicht mehr.
- Beendete eBay-Angebote.

Bestellungen tragen ihre eigene Kopie von Name, Preis und Bild. Abgeschlossene
Bestellungen halten das Modell deshalb nicht fest und bleiben nach dem Löschen unverändert.

### Ausnahme von der Leitlinie

Die Lagerbuchungen nie verkaufter Stücke gehen mit dem Modell. Sie beschreiben Bestand,
aus dem nie ein Geschäft wurde. Was ein Geschäft belegt, bleibt: Bestellungen, Zahlungen
und die Buchungen jedes reservierten, versendeten oder montierten Stücks. Gibt es so eine
Buchung, lässt sich das Modell nicht löschen.

### Stellwerk

- Im Produkteditor bietet „Modell löschen …“ einen Dialog an. Er nennt, was mitgeht, und
  löscht erst nach „Endgültig löschen“.
- Bei einem Modell im Shop steht statt des Knopfs „Zum Löschen erst archivieren.“
- Hält etwas das Modell fest, sagt der Dialog was, bei offenen Bestellungen mit Nummern.
- Das Log vermerkt jedes Löschen (`catalog.product.deleted` mit Name, Nummer und Zahl der
  Stücke).

## Folgen

- Testmodelle verschwinden ganz aus Katalog, Lager und eBay-Übersicht.
- Ein Modell mit Verkaufs- oder Montagegeschichte bleibt archiviert, unsichtbar im Shop.
- Rückgängig machen lässt sich ein Löschen nur über die nächtliche Sicherung (BETRIEB,
  „Wiederherstellen“).
