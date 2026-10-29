# ADR 0017: Fertigung: Drucker mit Zustand, Teile, Stücklisten, Druckaufträge

Status: angenommen · 29.10.2026

## Kontext

Die Werkstatt druckt auf 12 Druckern; defekte werden repariert (Entscheidung 15). Bis
hierher wusste das System davon nichts: Die Lieferzeit war je Variante gepflegt, und
ob ein Drucker gerade druckt, defekt ist oder auf ein Ersatzteil wartet, stand nirgends.

Das Konzept sieht dafür das Modul Fertigung vor (§2.2, §5.2): Teile, Stücklisten, Drucker,
Druckaufträge. Schritt 6 des Fahrplans umfasst dazu Wareneingang und Montage. Er wird
geteilt:

- **6a (dieser ADR):** Drucker mit Zustand, Material, Teile, Stücklisten, Druckaufträge.
- **6b:** Teilebestand in Boxen, Wareneingang fertiger Platten, Montage zu Einheiten.

## Entscheidung

### Drucker und ihr Zustand

- **Ein Drucker** hat den Code von seinem Etikett (`D01` bis `D12`), Name, Modell, Bauraum
  und eine Drucktechnik: Filament oder Resin. Die Technik ist fest.
- **Der Zustand** ist *in Betrieb*, *defekt*, *in Reparatur* oder *ausgemustert*.
  - Jede Meldung kommt mit Hinweis, Person und Zeit in den Verlauf
    (`manufacturing.printer_status_reports`).
  - Derselbe Zustand mit neuem Hinweis („Ersatzteil bestellt“) hält den Hinweis fest; die
    Dauer („defekt seit Dienstag“) beginnt nicht neu.
- **„Druckt gerade“ wird nicht gespeichert** (Leitlinie „Nichts Abgeleitetes speichern“):
  Ein Drucker druckt, solange einer seiner Aufträge druckt.
- **Ein Defekt mitten im Druck** macht den Druck zum Fehldruck, in derselben Transaktion.
  - Reparatur und Ausmustern warten, bis nichts mehr druckt (409 `printer_busy`).
  - Ausmustern wartet außerdem, bis keine Platte mehr auf den Drucker wartet
    (409 `printer_has_queue`).
- **Entfernen** lässt sich nur ein Drucker ohne Druckaufträge (409 `printer_in_use`); jeder
  andere behält seinen Verlauf und wird ausgemustert.
- **Rechte:** Zustand melden, Platten starten, abnehmen und fertig melden dürfen alle
  Mitarbeiter, auch Packer. Drucker, Teile, Stücklisten und die Planung bleiben bei Inhaber
  und Mitarbeitern.

### Material und Teile

- **Material** hat einen Namen und gehört zu einer Technik (*PLA grau*, *Resin ABS-like*).
  Es lässt sich archivieren. Ein Materialbestand folgt später.
- **Ein Teil** ist ein druckbares Einzelstück für einen Maßstab, mit seinen Druckdaten:
  - Teilenummer (`STW-ALT-DACH-H0`) und Name;
  - Maßstab und Technik, beide fest; ein Teil für einen anderen Maßstab ist ein anderes Teil;
  - Material derselben Technik;
  - Schichtdicke, Minuten je volle Platte, Teile je Platte;
  - Material je Teil in Gramm (Filament) oder Milliliter (Resin).
- **Im Einsatz** (in einer Stückliste oder auf einer Platte) lässt sich ein Teil archivieren,
  aber nicht löschen.
- **Druckdateien** (STL, 3MF) am Teil folgen mit der 3D-Verarbeitung der Medien (Konzept §6).

### Stücklisten

- **Eine Stückliste gehört zu einem Produkt in einem Maßstab.** Alle Varianten teilen sie,
  Bausatz wie Fertigmodell in jeder Farbe: Lackiert wird nach dem Druck.
- **Nur Teile ihres Maßstabs.** Zusammengesetzte Schlüssel prüfen das in der Datenbank:
  - die Stückliste gegen `catalog.product_scales (id, scale_code)`;
  - jede Zeile gegen das Teil mit demselben Maßstab.
  - Ein N-Dach kommt so nicht in einen H0-Bausatz, auch nicht durch einen Fehler im Code.
- **Keine Fassungen, abweichend vom Konzept (§2.4):** Was in ein Stück eingeht, hält die
  Montage (6b) im Journal fest. Jedes Stück behält damit seine Teile, ohne eine zweite
  Buchführung über Fassungen.
- **Der Katalog** kann einen Maßstab, zu dem es eine Stückliste gibt, nicht entfernen:
  409 `product_scale_has_bom`. Die Stückliste wird zuerst geleert.
- **Druckzeit je Bausatz:** die Anteile der Teile an ihren Platten, zusammengezählt
  (Plattenzeit ÷ Teile je Platte × Menge). Auf Resin ist eine volle Platte vieler Bausätze
  schneller, weil das langsamste Teil die Zeit bestimmt.

### Druckaufträge

- **Ein Druckauftrag ist eine Platte auf einem Drucker**, nummeriert für Menschen
  („Druck 17“). Sein Weg:
  - *wartet* → *druckt* → *Nachbearbeitung* → *fertig*;
  - dazu *Fehldruck* (beim Drucken oder danach) und *abgebrochen* (nur solange er wartet).
- **Höchstens ein Druck je Drucker**, gesichert durch einen eindeutigen Teilindex auf
  `status = 'printing'`. Starten lässt sich nur auf einem Drucker in Betrieb.
- **Die Nachbearbeitung** (Waschen, Aushärten, Entstützen) läuft neben dem Drucker; er ist
  dann schon frei für die nächste Platte.
- **Fertig melden** heißt, die guten Teile je Teil anzugeben; der Rest zählt als Ausschuss.
  Ein Fehldruck macht alle Teile der Platte zu Ausschuss.
- **Die Dauer** kommt aus dem Slicer oder wird geschätzt:
  - auf Filament die Summe der Anteile aller Teile;
  - auf Resin das langsamste Teil, denn das Licht härtet eine ganze Schicht auf einmal.
  - Die Druckerhalle zeigt damit Fortschritt und Ende.
- **Die Datenbank prüft die Technik:** Drucker, Auftrag und Teile tragen sie, verbunden über
  Schlüssel auf `(id, technology)`. Gute und fehlerhafte Teile zusammen sind nie mehr als
  geplant.
- **Ereignisse**, live im Stellwerk:
  - `manufacturing.printer.status_changed`;
  - `manufacturing.print_job.changed`;
  - `manufacturing.print_job.completed`;
  - `manufacturing.print_job.failed`.
  - Die Startseite des Stellwerks zeigt Meldungen, fertige Drucke und Fehldrucke.

### Im Stellwerk

- **`/admin/fertigung` ist die Druckerhalle:**
  - eine Anzeigetafel wie im Stellwerk (in Betrieb, drucken, warten, Nachbearbeitung,
    defekt, in Reparatur);
  - je Drucker eine Karte mit Lampe, laufender Platte, Fortschritt und Warteschlange;
  - auf jeder Karte eine Zeichnung des Druckers, in der das Teil mit dem Fortschritt wächst:
    auf Filament vom Druckbett nach oben, auf Resin unter der steigenden Bauplattform;
  - darunter die Platten in der Nachbearbeitung und die zuletzt fertigen.
- **`/admin/fertigung/drucker/{id}`:** der Drucker mit seinem Verlauf und den letzten Platten.
- **`/admin/fertigung/teile`:** Teile mit Druckdaten und Material.
- **Die Stückliste** steht im Produkt-Editor, je Maßstab, wie die Positionsliste einer
  Zeichnung.

## Folgen

- **6b** schließt an:
  - `manufacturing.print_job.completed` bucht die guten Teile in den Teilebestand;
  - Teile bekommen Etiketten (Code 128 mit der Teilenummer, Konzept §7);
  - die Montage entnimmt Teile nach Stückliste und erzeugt Einheiten mit Etikett.
- **Die Planung (Schritt 8)** liest Drucker, Zustände, Stücklisten und Druckzeiten. Mit ihr
  wird die Lieferzeit aus der Auslastung abgeleitet; bis dahin bleibt sie je Variante
  gepflegt.
- **Die Drucker der Werkstatt** legt der Inhaber im Stellwerk an, mit dem Code von ihrem
  Etikett, Modell und Technik; Teile und Stücklisten folgen mit den Druckdaten der Modelle.
