# ADR 0037: Druckdaten aus der geslicten Druckdatei

Status: angenommen · 18.11.2026 · ergänzt ADR 0017 (Fertigung) und ADR 0035 (Herstellwert)

## Kontext

Der Herstellwert (ADR 0035) braucht je Teil die Harzmenge. Chitubox zeigt sie vor jedem
Druck an (Volumen, Gewicht, Preis, Zeit); sie von dort abzutippen ist umständlich. Bei
adp-Modelle slict Chitubox für alle Drucker, und alle bekommen dieselbe Art Datei: eine
`.ctb` (geprüft an einer echten Platte für die Saturn 4 Ultra 16K am 18.11.2026).

Die Projektdatei `.chitubox` ist nicht lesbar. Die geslicte `.ctb` schreibt die Werte in
ihren Kopf, seit Chitubox 1.9 in einem AES-verschlüsselten Einstellungsblock. Den
Schlüssel veröffentlicht das freie Programm UVtools, das das Format liest und schreibt.

## Entscheidung

- **Nur der Kopf der Datei** wird gelesen. Der Browser schickt die ersten 512 KiB
  (`HEAD_BYTES`) Base64 in JSON an `POST /admin/manufacturing/slice-files/read`, auch
  wenn die Datei Hunderte MB groß ist. Gespeichert wird nichts. Die API bleibt JSON-only
  (ADR 0004), und der Proxy lässt bis 1 MB durch.
- **Formate** (`domain/slice_files.py`, rein): CTB verschlüsselt (`0x12FD0107`), CTB und
  CBDDLP unverschlüsselt (`0x12FD0086`, `0x12FD0019`), dazu Elegoo GOO `V3.0`. GOO ist
  nur nach der Formatbeschreibung gebaut, ohne echte Datei.
- **Die Antwort** ist die ganze Platte: ml, g, Slicer-Preis, Sekunden, Schichthöhe,
  Schichten, Druckerprofil. Das Teil-Formular übernimmt daraus Plattenzeit, Schichthöhe
  und *Material je Teil = ml ÷ Teile je Platte*. Gespeichert wird wie bisher erst mit
  „Speichern“.
- **Der Slicer-Preis wird nur gezeigt.** Gerechnet wird mit dem Literpreis des Materials
  (ADR 0035), damit ein neuer Harzpreis alle Teile auf einmal trifft.

## Folgen

- Stützen sind in der Menge enthalten, weil Chitubox sie mitrechnet.
- Ein unbekanntes oder abgeschnittenes Format wird mit `slice_file_unreadable`
  abgelehnt, statt zu raten. Eine STL-Datei ist keine Druckdatei.
- Ändert Chitubox den Schlüssel oder das Format, schlägt das Auslesen fehl, und die
  Werte lassen sich weiter von Hand eintragen.
