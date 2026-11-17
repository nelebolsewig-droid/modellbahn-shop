# ADR 0030: Farbpalette, Bewegung, einheitliche Fotos und das erste echte Modell

Status: angenommen · 17.11.2026

## Kontext

Das helle Präzisionsdesign (ADR 0007) kennt Lichtgrau, Mattschwarz und Preußischblau. Die
Auftraggeberin wünschte sich am 17.11.2026 mehr Pep: eine weitere Farbe, Animationen im Shop,
Modellfotos, die alle gleich aussehen, und eine Druckdatei der Werkstatt als bewegtes
3D-Modell in Farbe. Die Explosionszeichnung (ADR 0016) zeigte bis dahin einen Platzhalter.

## Entscheidung

- **Eine laute Farbe: Signalorange.** Rohwerte `signal-50/500/600/700`, Bedeutungen
  `highlight` (#FF5A1F, nur Zeichen: Lampe im Logo, Striche, Punkte), `highlight-fill`
  (#CF430C, Flächen mit weißer Schrift, 4,7 : 1), `highlight-ink` (#B93A08, Schrift auf allen
  Gründen, ≥ 4,8 : 1) und `highlight-subtle`. Preußischblau bleibt für Links, Fokusring und
  Zeichnungen; Mattschwarz bleibt der gewöhnliche primäre Knopf. Orange bekommt die eine
  Aktion, für die eine Seite da ist („Zum Katalog“, „In den Warenkorb“, „Zur Kasse“,
  „Scannen“ im Stellwerk), dazu Zähler, Marken und Schwebezustände. `danger` bleibt Rot und
  steht weiter immer mit einem Wort.
- **Eine ganze Palette, im ganzen System.** Die erste Fassung mit Orange allein war der
  Auftraggeberin zu schlicht. Dazu kommen deshalb `sea` (Petrol), `plum` (Violett), `rose`,
  `sky` und `sun` (Gelb, nur als Grund für dunkle Schrift), jede mit hellem Grund, und `night`
  (tiefes Preußischblau) für den Kopf der Startseite, die Fußzeile und die Begrüßung im
  Stellwerk. Das hebt aus ADR 0007 die Regel „nie dunkel“ für diese drei Flächen auf; die
  Seiten selbst bleiben hell. `selected` ist jetzt Preußischblau statt Mattschwarz. Der
  hervorgehobene Knopf trägt einen Verlauf von Orange nach Rosé (`bg-blaze`), ein Band in
  allen Farben (`bg-spectrum`) liegt über jeder Seite, und ein weicher Farbschleier (`wash`)
  hinter ihr.
- **Jeder Bereich des Stellwerks hat seine Farbe** (`SECTION_COLORS`): Modelle Orange,
  Bestellungen Blau, Lager Petrol, Fertigung Violett, Messen Rosé, eBay Grün. Sie färbt den
  aktiven Menüpunkt, den Seitengrund, die Feldkennungen und über `--selected` die primären
  Knöpfe, solange man dort ist.
- **Bewegung mit Maß.** Überschriften und Karten steigen beim Erscheinen auf (`Reveal`,
  `animate-rise-in`), die Zeichnung der Startseite wird wie von einem Plotter gezogen, Karten
  heben sich unter dem Zeiger, der Zähler am Warenkorb springt. Ohne JavaScript ist nichts
  versteckt; bei „reduzierter Bewegung“ steht alles still (bestehende Regel in `globals.css`).
- **Ein Rahmen für jedes Modellfoto** (`ModelPhoto`). Das Foto steht ganz und mittig; was
  sein Format frei lässt, füllt ein weicher Schleier aus dem Foto selbst. So sind Hoch- und
  Querformate, helle und dunkle Hintergründe gleich große, randvolle Felder. Das ersetzt die
  „rahmenlose Bühne“ aus ADR 0007 für Fotos; beschnitten wird weiterhin nichts. Wirklich
  gleiche Hintergründe entstehen nur beim Fotografieren oder durch Freistellen in der
  Medien-Pipeline; das ist hier nicht enthalten.
- **Der Eisenbahndrehkran EDK 6 ist das erste echte Modell** der Explosionszeichnung und
  dreht sich auf der Startseite. `frontend/scripts/build-explosion-mesh.py` liest die
  Druckdateien, setzt die Teile zusammen, dünnt sie auf zusammen rund 40 000 Dreiecke aus und
  schreibt `frontend/public/modelle/edk6.mesh` (rund 350 KiB). Ganz steht das Modell in
  seinen Farben; beim Zerlegen läuft die Farbe in die Zeichnung aus (`paintAt`).

## Folgen

- Die Druckdateien selbst liegen nicht im Repository und nicht auf der Website. Die
  Anzeigedatei ist öffentlich abrufbar, aber grob und auf 16 Bit gerundet: zum Ansehen gut,
  zum Drucken unbrauchbar.
- Wo die Teile am Kran sitzen, steht im Skript und ist nach Augenmaß gesetzt; die Werkstatt
  kann die Werte dort berichtigen und die Datei neu erzeugen.
- Druck- und Handarbeitszeiten des EDK 6 sind noch Beispielwerte (`exampleTimes`). Die Seite
  sagt das, und die Startseite zeigt die Zahlen erst, wenn echte eingetragen sind.
- `tokens.test.ts` prüft die neuen Paare mit; `mesh-file.test.ts` prüft, dass die Datei alle
  Teile enthält und klein bleibt.
