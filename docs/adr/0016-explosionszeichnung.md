# ADR 0016: Explosionszeichnung „So entsteht ein Modell“

Status: angenommen · 29.10.2026

## Kontext

Wer ein Fahrzeugmodell kauft, sieht das fertige Stück, aber nicht die Arbeit darin. Das
Modell entsteht so:

1. Konstruktion am Rechner;
2. Zerlegen in druckbare Teile;
3. Druck auf den 12 Druckern der Werkstatt;
4. Nacharbeit, Lack und Montage.

Der Auftraggeber wünscht sich eine 3D-Ansicht, die ein Modell in seine Einzelteile zerlegt
und wieder zusammenfährt.

Dabei gilt:

- **Der Shop soll schnell bleiben.** three.js ist rund 600 KB groß (min.), und nicht jede
  Seite braucht es.
- **Die Konstruktion ist das Kapital der Werkstatt.** Was ein Browser als 3D-Modell
  bekommt, kann man herunterladen. Echte Druckdateien dürfen deshalb nie ausgeliefert
  werden.
- **Nicht jedes Gerät kann WebGL**, und manche Besucher wollen keine Bewegung (reduzierte
  Bewegung im Betriebssystem).
- **Das Designsystem** (KONZEPT §11) zeichnet Modelle wie Architekturpläne: feine Linien in
  Preußischblau auf Raster, mit Schriftfeld.

## Entscheidung

### Eine eigene Seite, ein Weg dorthin

- **`/so-entsteht-ein-modell`** zeigt die Explosionszeichnung über eine Scroll-Strecke:
  - Die Zeichnung bleibt stehen, während die Seite vorbeiläuft.
  - Das Modell fährt auseinander, hält, solange die Teile „drucken“, und setzt sich wieder
    zusammen.
  - Die drei Arbeitsschritte, die Kennzahlen (Teile, Druckstunden, Handarbeit) und die
    **Stückliste** laufen mit.
  - Zeile, Positionsnummer und Teil leuchten gemeinsam auf.
  - Ein Regler zerlegt von Hand. Ziehen dreht das Modell.
- **Die Startseite** führt mit einem Abschnitt „So entsteht ein Modell“ dorthin, ohne
  three.js. Der Fuß verlinkt die Seite unter „Werkstatt“.

### three.js aus dem eigenen Build, erst bei Bedarf

- three.js 0.186 kommt über npm in den Build, nicht von einem CDN. Die CSP des Shops
  (`script-src 'self'`) bleibt unverändert.
- Die Szene (`components/workshop/explosion-scene.tsx`) ist ein eigener Chunk. `React.lazy`
  lädt ihn erst, wenn die Zeichnung einen Bildschirm vor dem Sichtfeld ist
  (IntersectionObserver). Andere Seiten laden ihn nie.
- **Gezeichnet wie ein Plan:**
  - orthografische Kamera, schräg von oben;
  - helle Flächen in `stage`, Kanten in `drawing-line`, die hervorgehobene Fläche in
    `drawing-grid`;
  - Positionsnummern als Kreise mit Hinweislinie und ein Schriftfeld.
  - Die Farben liest die Szene aus den CSS-Tokens.

### Das Modell als Daten

- **`lib/workshop/explosion.ts` beschreibt ein Modell als Positionen der Stückliste:**
  - Name, Stückzahl, Druckminuten;
  - wann die Position abgeht;
  - Teile aus einfachen Körpern (Quader, Zylinder), je mit Richtung und Weg.
- **Die Rechnung ist reine Arithmetik und getestet:** Scroll zu Zerlegung, Arbeitsschritt,
  Vorlauf früher Teile, Sichtbarkeit der Nummern.
- **Bis ein Modell der Werkstatt da ist, steht ein Platzhalter bereit:** ein nachgebautes
  Löschfahrzeug (`placeholder-model.ts`, `placeholder: true`).
  - Die Seite sagt das, mit Hinweis im Schriftfeld und unter der Stückliste.
  - Die Startseite zeigt die Beispielzahlen eines Platzhalters nicht.

### Ohne WebGL, ohne Bewegung

- **Ohne WebGL** bleibt die Seite vollständig: Statt der Zeichnung steht ein Hinweis, die
  Stückliste zeigt alle Teile.
- **Bei reduzierter Bewegung** gibt es keine Scroll-Strecke und keine Drehung. Die
  Zeichnung steht zerlegt still; der Regler bewegt sie von Hand.
- **Für Screenreader** sind Positionsnummern Schaltflächen mit Namen, die Stückliste ist
  eine Tabelle, und ein unsichtbarer Satz fasst Teile und Stunden zusammen.

## Folgen

- **Das echte Modell kommt aus den Druckdateien, aber vereinfacht:**
  - grob vernetzt;
  - nur die sichtbaren Außenformen;
  - im Maßstab der Darstellung, nicht druckbar.

  Vorgesehen ist glTF (`.glb`) mit einem Knoten je Position. Das Datenformat bekommt dafür
  eine Teil-Art „Netz aus der Datei“ neben Quader und Zylinder; `GLTFLoader` aus three.js
  liest sie.
- **Die Zahlen der Stückliste** (Teile, Druckzeiten, Handarbeit) liefert die Werkstatt. Mit
  ihnen fällt der Hinweis „Platzhalter“ weg, und die Startseite zeigt die Kennzahlen.
- **Je Produkt** kann später eine Explosionszeichnung auf der Produktseite stehen; die
  Komponente nimmt dafür ein beliebiges Modell.
- **Kosten:** Der Chunk mit three.js und der Szene wiegt 535 KB, gepackt rund 140 KB, und
  lädt nur auf `/so-entsteht-ein-modell`. Die Startseite bleibt bei 740 KB JavaScript
  (ungepackt), wie zuvor.
