# ADR 0007: Helles Präzisionsdesign

Status: angenommen · 22.10.2026

## Kontext

Schritt 2 brachte eine erste Gestaltung mit: warmes Grau, Bernstein als Akzent, schmale
Großbuchstaben, ein dunkles Stellwerk und einen dunklen Modus für den Shop. Der Auftraggeber
hat am 22.10.2026 die Richtung festgelegt: hell, freundlich und hochpräzise, orientiert an der
minimalistischen Präzision großer Produktseiten und am Strich einer Architekturzeichnung. Nichts
soll duster oder rein schwarz wirken. Die Produktfotos sollen im Mittelpunkt stehen.

## Entscheidung

- Seitengrund in Shop und Stellwerk ist ein mattes Lichtgrau (`canvas`, #F4F4F1). Es gibt keinen
  dunklen Modus und kein dunkles Stellwerk.
- Produktfotos stehen in rahmenlosen Bühnen (`stage`) mit viel Leerraum.
- Technische Ansichten sind Zeichnungen mit 1-px-Linien in Preußischblau (`drawing-line`,
  #003153) oder Anthrazit, mit Maßlinien und Schriftfeld.
- Aktive Optionen und primäre Knöpfe sind Mattschwarz (`selected`, #1E2124), alternativ
  Preußischblau (`accent`). Konturen sind Haarlinien (`line`).
- Eine Schriftfamilie: Geist, groß und dünn in Überschriften und Kennzeilen; Geist Mono nur für
  abzulesende Werte.
- Farben sind in drei Ebenen organisiert: Rohwerte, Bedeutungen, Komponenten. Komponenten
  verwenden nur Bedeutungen. Einzelheiten: Konzept §11.

## Folgen

- Das Frontend wird in Schritt 3 umgestellt: neue `tokens.css`, `@theme`-Klassen, Komponenten
  nach §11.3, helles Stellwerk. Die Gestaltung aus Schritt 2 gilt bis dahin als Übergang.
- Wer einen dunklen Modus bevorzugt, bekommt keinen. Weil Komponenten nur Bedeutungen kennen,
  ließe er sich später als zweites Thema ergänzen, ohne Komponenten zu ändern.
- Ein Test prüft die Kontraste der Text-Token. Die hauchdünnen Konturen erreichen 3 : 1 bewusst
  nicht; Zustände werden deshalb immer über Füllung, Kontur in `selected` oder den Fokusring
  gezeigt, nie über die Haarlinie allein.
- Geist wird über `next/font` selbst gehostet; Besucher laden keine Schriften von Google.
