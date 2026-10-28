# ADR 0013: Bausatz und Fertigmodell, Farben, Schnellerfassung und Startbestand

Status: angenommen · 28.10.2026

## Kontext

Bis hier kannte der Katalog drei Ausführungen: unbemalt, grundiert und fertig bemalt.
Der Inhaber hat das am 28.10.2026 zurechtgerückt:

- **Grundiert bietet adp-Modelle nicht an.** Es gibt zwei Ausführungen: den **Bausatz**
  zum Selberbauen und das **Fertigmodell**, fertig lackiert.
- **Ein Fertigmodell gibt es oft in mehreren Farben.** Der Autodrehkran ADK III3 Puma etwa
  steht im Shopify-Export in Blau, Grün, Grau und Hellblau, der Wohnanhänger Intercamp in
  Blau, Beige und Gold. Ein Bausatz ist unlackiert und hat keine Farbe.
- **Das Lager ist voll, der Katalog leer.** Ein PDF mit Fotos von 13 Kisten zeigt grob
  600 bis 800 Modelle: Lkw und Kräne der DDR und des Ostblocks, Feuerwehr, Militär, Pkw,
  Busse, K-700, Bausätze von Ostparts; H0 und TT gemischt. Bekannt mit Preis sind nur
  rund ein Dutzend Modelle aus dem Shopify-Export und von der alten Website.

Der Auftraggeber hat entschieden: Bausatz und Fertigmodell; Farben nur beim Fertigmodell;
eine **Schnellerfassung** fürs Handy; die bekannten Modelle als Startbestand, dazu
**Entwürfe aus den Lagerfotos** ohne Preis.

## Entscheidung

### Zwei Ausführungen

- **`unpainted` heißt jetzt „Bausatz“** und trägt in der Artikelnummer den Buchstaben
  **B**; **`painted` heißt „Fertigmodell“** und trägt **F**. Die Codes bleiben, damit
  Bestellungen, Galerien und Verträge nicht umziehen müssen.
- **`primed` bleibt als Zeile, mit `offered = false`.** Neue Varianten in dieser
  Ausführung lehnt die Domäne ab (`finish_code` / `not_offered`). Was es schon gibt,
  bleibt für Lager und Bestellhistorie stehen.
- **`finishes.colored`** sagt, welche Ausführung Farben hat: nur das Fertigmodell.

### Farbe als Teil der Variante

- **`variants.color`** ist Text, höchstens 40 Zeichen, leer für einen Bausatz und für ein
  einfarbiges Fertigmodell.
  - Eindeutig ist jetzt *Maßstab × Ausführung × Farbe*:
    `uq_variants_product_scale_id_finish_code_color`.
  - Die Domäne vergleicht ohne Groß- und Kleinschreibung („gelb“ = „Gelb“) und schreibt
    den ersten Buchstaben groß.
  - `ck_variants_kit_without_color` hält den Bausatz farblos, auch gegen einen Fehler im
    Code.
- **Eine Farbe ohne Namen oder nur benannte Farben.** Je Maßstab hat das Fertigmodell
  entweder genau eine Variante ohne Farbe, das einfarbige Modell, oder nur Varianten mit
  Farbe. Das Gemisch lehnt die Domäne ab (`color` / `required` oder `unnamed_sibling`):
  Neben den Farben ließe sich die Variante ohne Namen im Shop nicht wählen. Gefunden hat
  das der Klicktest, als eine schnell getippte Farbe verloren ging.
- **Freier Text statt Farbtabelle.** Die Farben der Werkstatt sind Lackfarben mit
  Eigennamen („Feuerwehrrot“, „Postgelb“, „Rot-Weiß“). Eine Tabelle wäre eine weitere
  Pflegeliste ohne Mehrwert. Das Frontend kennt die üblichen Namen und zeichnet daraus
  Farbtupfer (`src/lib/catalog/colors.ts`):
  - RAL-nahe Töne statt Bildschirm-Grundfarben;
  - „hell…“ und „dunkel…“ werden gemischt;
  - zwei Farben werden diagonal geteilt;
  - Silber, Gold und Kupfer bekommen Glanz.
  - Unbekannte Namen zeigen einen schraffierten Tupfer. Der Name steht immer daneben.
- **Artikelnummer:** `MB-{Nummer}-{Maßstab}-{Buchstabe}{Folge}`. Die erste Farbe einer
  Ausführung hat keine Folgenummer, die weiteren 2, 3 und so weiter. Nach dem Löschen wird
  die erste freie Nummer wieder vergeben.
- **Titel:** Der Verkauf friert „Produkt · H0 · Fertigmodell, Gelb“ in die Position ein;
  Warenkorb, Kasse, Etiketten und die Artikelliste für die Kasse zeigen dasselbe.
- **Galerie:** Ein Foto kann sagen, welche Farbe es zeigt (`product_media.color`). Die
  Produktbühne und das Bild im Warenkorb nehmen das Foto, das Maßstab, Ausführung und
  Farbe am besten trifft; beide rechnen nach derselben Regel.

### Migration 0007

- **Buchstaben in sicherer Reihenfolge:** erst `painted` B → F, dann `unpainted` U → B.
  Die Artikelnummern werden in derselben Reihenfolge umgeschrieben. Der Shop war noch
  nicht live; gedruckte Etiketten tragen die EAN, die bleibt.
- **Grundierte Varianten:** ohne Stücke im Lager werden sie gelöscht, mit Stücken
  abgeschaltet. Fotos mit dem Tag „grundiert“ verlieren den Tag.
- **Zurück** geht nur, solange keine Variante eine Farbe hat; sonst bricht der Downgrade
  mit einer Meldung ab.

### Schnellerfassung

- **`POST /admin/catalog/quick-entries`** (`createQuickEntry`) erfasst ein Modell in einer
  Transaktion:
  - Es nimmt ein Produkt, etwa einen Entwurf aus den Lagerfotos, oder legt eines mit dem
    Namen neu an.
  - Es setzt die Kategorie, wenn das Produkt noch keine hat.
  - Es legt Maßstab und Variante an, wo sie fehlen. Eine bestehende Variante bekommt den
    neuen Preis.
  - Gibt es nur die eine Variante ohne Farbe und kommt eine Farbe dazu, bekommt diese
    Variante den Namen. Der Startbestand kennt die meisten Modelle ohne Farbe; das erste
    Modell aus der Kiste sagt, welche es hat.
  - Ein Foto kommt in die Galerie, markiert mit Maßstab, Ausführung und Farbe.
  - Der Zustand des Produkts bleibt: Ein Entwurf bleibt Entwurf.
- **Die Stücke** registriert weiter das Lager (`POST /admin/inventory/units`) mit der
  zurückgegebenen Variante. Katalog und Lager bleiben getrennt.
- **`/admin/erfassen`** ist dafür gemacht, mit dem Handy an der Kiste zu stehen:
  - Das Foto kommt aus der Kamera, der Upload beginnt sofort.
  - Modell suchen oder neu anlegen; die Kategorie wird nur gefragt, wo sie fehlt.
  - Maßstab und Ausführung sind Tippflächen. Farben kommen als Tupfer, die des Produkts
    zuerst.
  - Dazu Preis, Stückzahl mit Etiketten und Platz.
  - Eine Zeile über dem Knopf sagt vorher, was passiert: neues Produkt, neue Variante,
    bestehende Variante mit ihrem bisherigen Preis, oder welche Variante ihre Farbe bekommt.
  - Danach: Artikelnummer, Stückcodes, Etikettendruck, „Nächstes Modell“ und „Gleiches
    Modell, andere Farbe“.
- **`POST /admin/catalog/publish-ready`** (`publishReadyProducts`) veröffentlicht am Ende
  eines Tages alle Entwürfe, denen nichts mehr fehlt. Der Rest bleibt Entwurf; im Editor
  steht, was fehlt. Der Knopf steht in der Produktliste.

### Startbestand

- **`backend/seed/startbestand.json`** enthält den Kategorienbaum, die bekannten Modelle
  mit Preisen und Farben und 16 Entwürfe aus den Lagerfotos. Die Entwürfe haben weder
  Preis noch Variante; ihre Beschreibung sagt „Bitte prüfen“ und was zu prüfen ist.
- **`make catalog-import`** (`python -m modellbahn.cli import-catalog PATH`) spielt die
  Datei ein und lässt sich wiederholen:
  - Kategorien werden über Elternteil und Namen wiedererkannt, Produkte über ihre Adresse.
  - Das Format ist streng: Unbekannte Felder oder nicht angebotene Ausführungen fallen auf.
  - Unbekannte Kategorien oder Maßstäbe stoppen den Import, bevor etwas geschrieben ist.
  - Hinweise aus der Datei („laut Shopify 2 Stück“) werden nur ausgegeben, nie
    gespeichert.
- **Warum nur Familien:** Auf den Kistenfotos ist ein Modell 60 bis 100 Pixel groß. Typen
  sicher zu bestimmen geht so nicht. Die Entwürfe benennen deshalb Familien wie
  „Tatra 148 Kipper“ oder „Militär-Lkw mit Plane“. Aufteilen, benennen und mit Preisen
  versehen gehört in die Schnellerfassung, Kiste für Kiste.

## Folgen

- **Shop:** Auf der Produktseite folgt der Ausführung die Farbwahl. Die Fotobühne springt
  auf die gewählte Farbe; ein Wechsel des Maßstabs behält Ausführung und Farbe, wo es sie
  gibt.
- **Stellwerk:** Im Produkteditor lassen sich Varianten je Farbe anlegen und umbenennen.
  Eine Vorschlagsliste hilft beim Tippen. Grundierte Altvarianten stehen als „nicht mehr
  angeboten“ da.
- **Alte Etiketten:** Artikelnummern auf schon gedruckten Etiketten stimmen nicht mehr. Der
  Scanner liest aber die EAN und den Stückcode, und die bleiben.
- **Smoke-Test:** Er prüft jetzt auch:
  - Farbe am Fertigmodell, abgelehnte Farbe am Bausatz, abgelehnte Grundierung;
  - eine Schnellerfassung mit Foto und eine zweite Farbe mit `-F2`;
  - „Fertige veröffentlichen“ mit beiden Farben im Shop.
- **Noch offen:** die übrigen Preise und Farben aus den Kisten, Modell für Modell.
