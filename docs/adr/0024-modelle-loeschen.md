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
    - Dazu zählt eine bezahlte eBay-Bestellung, die der Shop noch nicht als eigene
      Bestellung übernommen hat (`eBay 12-34567-89012`). Ohne den Artikel würde der
      Verkauf sie beim Übernehmen verwerfen.
  - `product_has_history`: Ein Stück ist gerade einer Bestellung zugeteilt oder
    kommissioniert, oder es wurde versendet oder montiert. Die Buchungen versendeter und
    montierter Stücke belegen einen Verkauf oder eine Montage und bleiben; das Modell
    bleibt dann archiviert.
  - `product_on_marketplace`: eBay zeigt noch ein Angebot des Modells. Nach dem
    Archivieren nimmt der Abgleich es herunter.
  - `product_scale_has_bom` wie bisher: Eine Stückliste der Fertigung hängt an einem
    Maßstab.

### Was mitgelöscht wird

Das alles geschieht in einer Transaktion. Die Produktzeile und die Stücke sind dabei
gesperrt, so dass kein Scan und keine Zuteilung dazwischenkommt:

- Maßstäbe, Varianten, Epochen und die Zuordnung der Galerie. Die Fotos selbst bleiben in
  der Medienbibliothek.
- **Stücke, die die Werkstatt nie verlassen haben** (etikettiert, im Lager, verschrottet)
  samt ihren Lagerbuchungen, rückgängig gemachte Scans eingeschlossen. Ihre Etiketten
  gelten danach nicht mehr.
  - Dazu gehört ein Stück, dessen Reservierung mit einer stornierten Bestellung endete:
    Es wurde nie verkauft. Seine Buchungen zur Reservierung gehen mit, die stornierte
    Bestellung selbst bleibt.
- Die eBay-Angebote, die eBay nicht mehr zeigt: beendete und vom Shop zurückgehaltene.

Bestellungen tragen ihre eigene Kopie von Name und Preis. Abgeschlossene Bestellungen
halten das Modell deshalb nicht fest und bleiben nach dem Löschen unverändert. Ihr Bild
ist ein Verweis auf das Foto in der Medienbibliothek: Löscht man das Foto später dort,
zeigt die alte Bestellung kein Bild mehr.

### Ausnahme von der Leitlinie

Die Lagerbuchungen nie verkaufter Stücke gehen mit dem Modell. Sie beschreiben Bestand,
aus dem nie ein Geschäft wurde. Was ein Geschäft belegt, bleibt: Bestellungen und
Zahlungen (auch stornierte) und die Buchungen jedes versendeten oder montierten Stücks.
Gibt es so ein Stück, lässt sich das Modell nicht löschen.

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
- Bewusst nicht abgefangen: Bietet jemand das Modell genau in dem Moment in der
  eBay-Übersicht an, in dem es gelöscht wird, bleibt ein Angebot ohne Modell zurück. Es
  steht mit „Das Produkt gibt es in diesem Maßstab nicht mehr“ in der Übersicht und geht
  nie online.
