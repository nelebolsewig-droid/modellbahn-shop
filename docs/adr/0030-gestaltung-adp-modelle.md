# ADR 0030: Gestaltung von adp-Modelle – warme Palette, kantige Formen, Scroll-Film

Status: angenommen · 18.11.2026 · ersetzt die Farben, Schriften und Radien aus ADR 0007

## Kontext

Die bisherige Gestaltung (Lichtgrau, Mattschwarz, Preußischblau, dünne Schrift, runde Pills)
war der Inhaberin zu schlicht und passte nicht zur Marke. In mehreren Runden mit Entwürfen
hat sie am 17. und 18.11.2026 festgelegt:

- eine eigene Farbpalette, und nichts Dunkles;
- kräftige, moderne Überschriften;
- kantige, präzise Formen;
- Scroll-Effekte auf der Startseite, mit einem realistisch gerenderten Modell;
- die Wortmarke „adp-Modelle“ in ihrer Schreibweise.

## Entscheidung

### Farben

| Rolle | Wert | Token |
| --- | --- | --- |
| Haupt-Hintergrund, Alabaster-Beige | `#FAF6F0` | `canvas` |
| Karten und Sektionen, Sandbeige | `#EFE7DC` | `stage`, `surface` |
| Haupt-Akzent und Knöpfe, Mandarin-Orange | `#E8632B` | `action` |
| Hover und Highlights, Terrakotta | `#C94B1A` | `action-hover`, `highlight` |
| Texte und Überschriften, Espresso-Anthrazit | `#26211E` | `ink`, `selected` |

Daraus abgeleitet, damit jede Schrift 4,5 : 1 erreicht:

- **Auf Mandarin steht Espresso, nicht Weiß** (`on-action`, 4,7 : 1; Weiß käme auf 3,3 : 1).
  Weiß steht erst auf Terrakotta (`on-action-hover`, 4,7 : 1).
- **Terrakotta als kleine Schrift ist eine Stufe tiefer** (`accent` `#9E380F`, 5,1 : 1 auch
  auf der tiefsten Sandfläche). Das reine Terrakotta (`highlight`) bleibt großer Schrift und
  Marken vorbehalten.
- Vertiefte Flächen sind ein tieferes Sand (`sunken` `#E6DCCD`), Linien Sandtöne.
- Erfolg, Warnung und Fehler bleiben Grün, Bernstein und Rot, je eine Stufe dunkler.
- Technische Zeichnungen sind in Espresso statt Preußischblau.
- Dunkel bleibt allein der Sucher des Scanners.

`tokens.test.ts` prüft alle Paare und hält die fünf Werte der Palette fest.

### Schrift

- Überschriften in **Bricolage Grotesque**, Gewicht 800, eng gesetzt (`font-display`;
  `display-xl`, `display`, `title`, `heading` und alle `h1`–`h3`).
- Fließtext und Bedienelemente bleiben Geist, Maßzahlen Geist Mono.
- Große Zahlen (Maßstab-Kacheln, Kennzahlen) stehen ebenfalls in der Display-Schrift.

### Formen

- Alle Radien sind 0. Rund bleiben nur echte Kreise: Lampen, Punkte, Radioknöpfe.
- Der primäre Knopf ist Mandarin; der Aufruf am Ende des Scroll-Films trägt einen harten,
  versetzten Schatten.

### Wortmarke

`Wordmark` setzt den Shop-Namen (`NEXT_PUBLIC_SHOP_NAME`): der Teil vor dem Bindestrich klein und
rot (`wordmark` `#CC0000`), Times New Roman fett kursiv; Bindestrich und Rest in Espresso, Arial fett. Wo ein Gerät die beiden
Schriften nicht hat, springen die metrisch gleichen Tinos und Arimo ein (über `next/font`
selbst gehostet). Das Signet (`LogoMark`) bleibt als Marke des Stellwerks, jetzt kantig mit
mandarinfarbener Lampe.

### Startseite als Scroll-Film

`ScrollFilm` (`components/site/scroll-film/`) ersetzt den bisherigen Kopf der Startseite. Fünf
Kapitel, jedes ein hoher Abschnitt mit angehefteter Bühne; die Scroll-Position treibt alles:

1. **Auftakt:** Der EDK 6 wächst vor dem Schriftzug, dann zeichnen sich drei Maßlinien.
2. **Zerlegen:** Der Kran löst sich in seine sieben Baugruppen, die Stückliste zählt mit.
3. **Programm:** Vier Tafeln laufen seitwärts durch (Schienenfahrzeuge, Autokrane, Lkw,
   Sonderanfertigung).
4. **Maßstab:** Der Kran schrumpft am Lineal von Spur 0 bis N.
5. **Schluss:** Zwei Schriftbänder und der Weg in den Katalog.

- `film-driver.ts` bewegt die Bühnen direkt im DOM, einmal je Animationsbild, ohne React neu
  zu rendern. Bei „Bewegung reduzieren“ und ohne JavaScript stehen die Kapitel still und
  bleiben vollständig lesbar.
- Der Film beginnt unter dem Seitenkopf (`--site-header-height`), damit die erste Bühne den
  ganzen ersten Bildschirm füllt.
- Die Bilder unter `public/startseite/edk6/` sind Renderings der eigenen Druckdateien: der
  ganze Kran auf einem Stück Schottergleis und jede Baugruppe einzeln aus derselben Kamera,
  damit die Ebenen deckungsgleich übereinander liegen. Es liegen nur Bilder im Repository,
  keine Druckdaten.
- Lage der Teile nach Angabe der Inhaberin: Die Grundplatte greift mit dem Ringwulst nach
  unten in den Unterwagen, die Seilklappe ist hinten angelenkt und zeigt nach vorn oben, jedes
  Drehgestell hat zwei Radsätze (die Druckdatei enthält nur den Rahmen).

### Aufbau des Stellwerks

Die Inhaberin hat drei Entwürfe gesehen und alle angenommen; jeder gilt für die Seite, für die
er gezeichnet war:

- **Leiste statt Kopfzeile.** Auf dem Schreibtisch (ab 1024 px) steht links eine Leiste: oben
  die Wortmarke, darunter die Orte mit Nummer (Heute, Bestellungen, Modelle, Lager, Fertigung,
  Messen, eBay, Einstellungen), am Fuß der große Knopf „Scannen“, Name, Passwort und Abmelden.
  Darunter bleibt es bei der niedrigen Kopfzeile und der Leiste am unteren Rand.
- **Heute (Fahrpult)** ist die Startseite: Gruß, vier Zahlen als Kacheln mit abgeschnittener
  Ecke (zu versenden, zu fertigen, Zahlung offen, ohne Bestand), darunter die Liste zur
  gewählten Kachel, daneben die Druckerhalle im Überblick und die nächste Messe. Ereignisse und
  Systemstatus bleiben darunter. „Knapp im Lager“ aus dem Entwurf heißt „Ohne Bestand“ und zählt
  die Modelle im Shop, von denen nichts im Regal liegt: Einen Meldebestand für Teile gibt es
  nicht. Packer sehen die zwei Zahlen, mit denen sie etwas tun können.
- **Bestellungen als Gleisbild:** Jede offene Bestellung ist ein Wagen an dem Bahnhof, an den
  ihr Zustand sie stellt. Es gibt die Bahnhöfe, die die Daten hergeben: Eingang (Zahlung
  offen), Fertigung (bezahlt, wartet auf ein Stück, ADR 0029), Versand (bezahlt und
  vollständig), Unterwegs (die zuletzt versendeten). „Bezahlt“ und „Montage“ aus dem Entwurf
  entfallen, weil eine Bestellung diese Zustände nicht kennt. Wagen von eBay tragen eine
  Kante in Terrakotta. Die bisherige Liste mit Filter und Suche bleibt als zweite Ansicht.
- **Modelle als Werkbank:** Ab 1280 px steht neben der Liste das Typenschild des gewählten
  Modells (Foto, Stand, Bestand je Ausführung, Lagerplätze). Dort wählt ein Klick aus,
  „Bearbeiten“ öffnet das Modell; schmaler öffnet ein Klick wie bisher das Modell.

## Folgen

- Shop und Stellwerk teilen die Tokens: Das Stellwerk trägt damit dieselben Farben, Schriften
  und kantigen Formen.
- Die Strichzeichnung des Kranwagens auf der Startseite entfällt.
- PR #43 (Signalorange, ADR dort ebenfalls als 0030 nummeriert) ist durch diese Entscheidung
  überholt.
