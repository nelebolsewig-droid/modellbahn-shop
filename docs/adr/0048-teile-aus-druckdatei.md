# ADR 0048: Teile entstehen aus der Druckdatei

Status: angenommen · 24.11.2026 · ergänzt ADR 0017 und ADR 0047

## Kontext
Teile und Material von Hand anzulegen war dem Team zu aufwendig; die Seite blieb leer.
Ohne Teile bucht die Drucker-Brücke aber keinen Druck, und Lagerwert und Planung hängen
an den Teilen.

## Entscheidung
- **Druckt ein Drucker eine Datei, zu der es kein Teil gibt, legt die Brücke es an:**
  - Name = Dateiname ohne Endung, ohne `.stl`, ohne `#4` (Plattennummer von Chitubox) und
    ohne Stückzahl;
  - Teilenummer = Buchstaben und Ziffern des Namens mit Bindestrichen, groß
    (`Wartburg 353 4x TT.ctb` → `WARTBURG-353-TT`); belegt → `-2`, `-3` …;
  - Teile je Platte = `x4` oder `4x` im Dateinamen, sonst 1;
  - Maßstab = ein Maßstabscode im Namen (`TT`, `N` …), sonst H0;
  - Material = das erste aktive Material der Druckertechnik (euer Resin);
  - Notiz „Automatisch angelegt aus der Druckdatei …“.
- **Was ein Teil noch nicht hat, lernt es vom Druck:** Druckzeit je Platte vom Drucker;
  Resin je Teil und Schichthöhe, wenn die Brücke die Druckdatei mitliest (`volume_ml`,
  `layer_height_um` in der Meldung, beide freiwillig). Von Hand Eingetragenes bleibt.
- **„Teile & Material“** steht nicht mehr in der Druckerhalle, sondern unter
  Einstellungen.

## Folgen
- Die Teileliste füllt sich mit dem Drucken. Stücklisten (welches Modell aus welchen
  Teilen) bleiben Handarbeit; ohne sie plant die Automatik keine Platten.
- Resin je Teil gibt es erst, wenn die Brücke die .ctb-Dateien lesen kann (Ordner auf dem
  Werkstatt-Rechner, folgt); bis dahin zählt der Lagerwert ohne Materialkosten.
