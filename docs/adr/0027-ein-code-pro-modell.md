# ADR 0027: Ein Code pro Modell

Status: angenommen · 15.11.2026

## Kontext

Die Werkstatt druckt ein Etikett mehrmals und klebt es auf mehrere Stücke desselben
Modells. Das Etikett trug aber neben der EAN-13 der Ausführung einen Code 128 mit dem
Code einer Einheit, und das Lager zählte ein Stück je Einheiten-Code (ADR 0011).

- **Sieben Stücke mit einem Etikett zählten als eins.** Shop und eBay boten eins an.
- **Ausbuchen nahm „alle“:** Wurde das Stück verkauft, war es weg, die sechs anderen
  im Regal standen nirgends.
- **Drucken legte Stücke an.** „Stücke erfassen“ erzeugte Einheiten mit Etikett; wer sie
  nicht einlagerte, hatte unverbuchte Stücke, oft von doppelt gedruckten Etiketten.

## Entscheidung

### Ein Code nennt das Modell

- Ein Etikett nennt die Ausführung, nie ein Stück. Wie viele Stücke es sind, sagt die
  Werkstatt beim Scannen (Anzahl).
- Intern bleibt jedes Stück eine Einheit mit eigenem Code. Zuteilung, Journal und
  Lieferbarkeit in Shop und bei eBay bleiben, wie sie sind. Welche Einheit gebucht wird,
  entscheidet das System.
- **Alte Etiketten gelten weiter.** Beim Einlagern, Kommissionieren und Ausbuchen steht
  ein Einheiten-Code für die Ausführung seiner Einheit, in welchem Zustand die Einheit
  auch ist. Nur die Auskunft zeigt das Stück selbst.

### Etiketten

- **Das Etikett eines Modells** trägt die EAN-13, Name, Ausführung und Farbe,
  Artikelnummer, Preis und den Hersteller (GPSR, Nachtrag in ADR 0011). Der Code 128 der
  Einheit entfällt; der Hersteller steht jetzt über die ganze Breite unten.
- Platz- und Teileetiketten bleiben, wie sie sind.
- **Drucken ohne Stücke:** `printLabels` nimmt `variants` (Ausführung und Anzahl) und
  druckt so viele Etiketten, ohne eine Einheit anzulegen. PDF, PNG und ZIP wie bisher; die
  Dateien heißen nach dem Modell (`file_name()`), ohne Einheiten-Code.
- `unit_codes` druckt das Etikett der Ausführung der Einheit. „Etikett neu drucken“ (Seite
  des Stücks, Ausführung ändern) liefert so dasselbe Modell-Etikett.

### Einbuchen statt Erfassen

- „Stücke einbuchen“ (Lager, Bestand, Katalog) fragt Ausführung, Anzahl und Platz.
- **Der Platz ist Pflicht** (`POST /units` verlangt `location_code`). Vorgeschlagen wird
  der Platz, in dem die Ausführung schon liegt (der mit den meisten Stücken), sonst der
  zuletzt benutzte dieses Rechners. „Später beim Einlagern scannen“ entfällt.
- Die Stücke liegen danach frei im Platz; wartende Bestellungen bekommen sie zuerst.
- „Etiketten drucken“ ist vorausgewählt und druckt danach so viele Modell-Etiketten, wie
  eingebucht wurden.
- Drucken allein legt keine Einheit mehr an. Auch „Neues Modell“ bucht Stücke nur mit
  Platz ein. Die Montage bleibt, wie sie ist.

### Scannen mit Anzahl

- **`ScanIn.quantity`** (1 bis 200, ohne Angabe 1). Die Scan-Zeile speichert sie
  (Migration 0019); eine wiederholte `scan_id` muss dieselbe Anzahl bringen, sonst
  `scan_id_reused`. Kommissionieren und Auskunft zählen sie nicht.
- **Einlagern:** Mit gewähltem Platz bucht ein Modell-Code N Stücke dorthin.
  1. Zuerst unverbuchte Stücke der Ausführung, die ältesten zuerst.
  2. Dann neue Stücke, gleich im Bestand.
  - Ein frei gewordenes Stück geht an die älteste wartende Bestellung, wie bisher.
  - Die Antwort `booked_in` nennt in `stock_effect` die Anzahl, den Platz, wie viele
    Stücke des Modells dort jetzt liegen, wie viele unverbucht waren, wie viele neu sind
    und welche Bestellungen sie bekamen. Das Stellwerk zeigt „+7 · jetzt 9 hier“.
  - Der Code eines Stücks, das schon im Lager liegt, zählt ebenso als „+N“ seines
    Modells. Umlagern per Scan gibt es nicht mehr; dafür bleibt „Umlagern …“ in den Listen.
  - **Neue Stücke legen nur Inhaber und Mitarbeiter an**, wie beim Einbuchen
    (`ScanRequest.may_add_units`). Ein Packer lagert per Scan nur unverbuchte Stücke ein;
    bräuchte der Scan neue, bucht er nichts (`book_in_not_allowed`), alles oder nichts.
- **Ausbuchen** (neuer Modus `scrap`, nur Inhaber und Mitarbeiter wie jedes Ausbuchen):
  - Kontext `reason` (die Gründe des Ausbuchens, ohne Angabe `sold`) und optional der
    Platz; ein Platz-Scan wählt ihn wie beim Einlagern.
  - N freie Stücke (im Lager, keiner Bestellung zugeteilt) verlassen den Bestand: aus dem
    Platz, ohne Platz die ältesten, wo sie auch liegen. `booked_out` nennt Grund und
    Herkunft.
  - Sind weniger frei, bucht der Scan nichts (`not_enough_free`). `variant.free_units`
    und mit Platz `variant.free_here` sagen, wie viele frei sind.
- **Kommissionieren:** Jeder Modell-Code nimmt ein Stück der Ausführung, das der
  Bestellung zugeteilt ist; nennt ein alter Code eins davon, genau dieses. Auch der Code
  eines anderen Stücks (frei, für eine andere Bestellung reserviert, unverbucht) nimmt ein
  Stück der Bestellung. Für ein wartendes Stück nimmt der Scan das älteste freie. Das
  Tauschen „gescanntes freies Stück statt reserviertem“ entfällt.
- **Eine Buchung je Scan:** Ein Scan hält alle seine Bewegungen (Journal mit `scan_id`),
  alles oder nichts. Die gebuchten Stücke werden auf einmal nach Kennung gesperrt, wie auf
  allen anderen Wegen. Ändert sich eins zwischen Suche und Sperre, sucht der Scan die
  nächsten ältesten, bis die Anzahl erreicht ist oder keins mehr da ist; diese sperrt er
  nur, wenn niemand sonst sie hält (`SKIP LOCKED`), damit nichts über Kreuz wartet.
  Beim Kommissionieren sperrt er alle reservierten Stücke der Ausführung für die
  Bestellung und nimmt das erste, das noch reserviert ist: Zwei gleichzeitige Scans
  derselben EAN nehmen zwei Stücke. `inventory.stock.changed` geht je Bewegung hinaus, wie
  beim Einlagern und Ausbuchen von Hand.

### Rückgängig

- **Eingelagert:** Die Stücke gehen zurück; unverbuchte sind wieder unverbucht. Stücke, die
  der Scan angelegt hat, verlassen den Bestand mit Grund `mistake` („Versehen“) und Notiz
  „Scan zurückgenommen“. Der Bestand stimmt danach wieder.
  - Warum kein Löschen: Das Journal löscht nichts, und `label_starts` lässt keine Buchung
    vor das Etikett zurück. Jede Bewegung bekommt ihr `undo`, das Ausbuchen ist ein
    gewöhnliches `scrap`. Die CHECKs des Journals bleiben, wie sie sind.
  - Eine Bestellung, die ein angelegtes Stück bekommen hatte, wartet danach wieder.
- **Ausgebucht:** Die Stücke liegen wieder frei, wo sie lagen. Wartet inzwischen eine
  Bestellung auf das Modell, bekommt sie eins.
- Wie bisher zehn Minuten lang, und nur, solange keins der Stücke weiter gebucht wurde
  (`scan_changed_since`). Rückgängig sperrt zuerst alle Stücke des Scans, nach Kennung.
- Einen Ausbuch-Scan nehmen nur Inhaber und Mitarbeiter zurück (403
  `insufficient_role`): Das bucht Stücke wieder ein.

### Stellwerk

- **Scanner:** Modus „Ausbuchen“ mit dem Feld „Grund“, nur für Inhaber und Mitarbeiter.
  Ohne Platz steht dort „alle“: die ältesten freien Stücke.
- **Anzahl** bei Einlagern und Ausbuchen (−, Zahl, +). Ein Modell-Etikett nimmt sie beim
  Scannen mit, und das Feld steht sofort wieder auf 1: Ein zweites Etikett, gescannt bevor
  die Antwort kam oder ohne Netz, zählt ein Stück. Ein Platz- oder Teileetikett lässt sie
  stehen.
  - Tippt ein Handscanner in das Feld, erkennt das Stellwerk den Code am Rhythmus und
    scannt ihn mit der Zahl, die vorher getippt war. Das Feld „Grund“ gibt den Fokus nach
    der Wahl ab, damit der nächste Code keinen anderen Grund wählt.
- **„Versehen“:** Der Grund `mistake` heißt im Stellwerk „Versehen“ (bisher „Falsch
  erfasst“). In der Liste „Unverbucht“ wählt „Alle auswählen“ alle Stücke; „Ausbuchen …“
  schlägt bei nur unverbuchten Stücken „Versehen“ vor.

### Migration 0019

- `inventory.scans.mode` darf `scrap` sein (`ck_scans_mode`).
- Neue Spalte `inventory.scans.quantity` (`ck_scans_quantity_range`: 1 bis 200); bestehende
  Scans haben 1.
- Zurückrollen macht aus Ausbuch-Scans Einlager-Scans; ihre Journalbuchungen sagen weiter
  `scrap`.

## Folgen

- Sieben Stücke mit einem Etikett sind sieben Stücke, wenn beim Einlagern 7 eingetippt
  wird. Verkauft die Messe drei, bucht ein Scan mit Anzahl 3 sie aus.
- **Der heutige Bestand ist zu niedrig** (ein Stück je Etikett) und hat unverbuchte Stücke
  aus doppelt gedruckten Etiketten. Er wird von Hand richtiggestellt: am Platz das Etikett
  scannen und die fehlende Zahl eintippen, alte unverbuchte als „Versehen“ ausbuchen
  (BETRIEB, „Bestand auf Modell-Etiketten umstellen“).
- Welches Stück eines Modells in welchem Fach liegt, weiß das Lager nur noch als Zahl je
  Platz. Nimmt der Packer ein Stück aus einem anderen Fach als dem auf der Pickliste, bucht
  der Scan das Stück der Pickliste; beide Fächer weichen dann um eins ab, bis eine Inventur
  sie richtigstellt.
- Packer lagern per Scan nur ein, was unverbucht da ist; neue Stücke einbuchen und
  ausbuchen bleiben bei Inhaber und Mitarbeiter.
- **Noch nicht umgestellt:** Die Inventur je Platz zählt weiter Stück für Stück und erkennt
  Modell-Etiketten nicht; dort hakt man ab. Seite und Listen der Stücke zeigen weiter
  Einheiten-Codes.
- Der Smoke-Test druckt Modell-Etiketten, lagert per EAN mit Anzahl 2 ein und kommissioniert
  per EAN.
