# ADR 0031: Fotostudio – einheitliche Modellfotos

Status: angenommen · 18.11.2026 · ergänzt ADR 0030 (Gestaltung adp-Modelle)

## Kontext

Die Modelle werden in einer Fotobox mit dem Handy fotografiert und bisher von Hand (teils
mit ChatGPT) nachbearbeitet. Im Shop stehen die Fotos nebeneinander und passen nicht
zusammen: mal warm, mal kalt, mal hell, mal dunkel, das Modell mal groß, mal klein, mal
oben, mal unten. Gewünscht ist „eine gerade Linie durch die Seite“.

## Entscheidung

Der Worker bringt jedes hochgeladene Modellfoto selbst in eine Form (`media`,
`infrastructure/studio.py`), bevor er wie bisher die Größen rendert:

1. **Freistellen** mit einem neuronalen Modell (ISNet „general use“, ONNX, auf der CPU).
   Kleine Flecken fallen weg, kleine Löcher werden geschlossen, die Kante bleibt weich.
   Der Schatten der Fotobox gehört nicht zum Modell. Ausnahme: Schwarze Teile im
   schwarzen Schatten, etwa Reifen unter einem Auto, kann das Modell nicht vom Schatten
   unterscheiden und ließ sie weg. Was vor hellem Hintergrund fast schwarz ist und am
   Modell hängt, bleibt deshalb beim Modell (`_with_dark_parts`); der hellere Schatten
   darum herum läuft weich aus.
2. **Licht angleichen** am Hintergrund der Fotobox, der weiß ist: Sein Farbstich wird
   herausgerechnet (Weißabgleich), seine Helligkeit auf einen festen Wert gebracht. So
   sieht jedes Foto aus wie unter derselben Lampe. Die Korrekturen sind begrenzt; ein
   farbiger Hintergrund (etwa aus einer Bearbeitung) wird nur zum Teil geglaubt.
3. **Kante säubern:** Das Licht des Hintergrunds wird aus der weichen Kante
   herausgerechnet, damit auf Sand kein heller Saum bleibt.
4. **Bühne:** quadratisch, 2048 px. Das Modell füllt ein festes Feld (84 % der Breite,
   64 % der Höhe), steht waagrecht mittig und mit dem tiefsten Punkt auf der **Standlinie**
   bei 80 % der Höhe (`domain/studio.py`). Darunter liegt der **eigene Schatten aus dem
   Foto**: Was neben dem Modell dunkler ist als der glatt angenommene Hintergrund, wird
   als Schatten in Espresso übernommen, nur nah am Modell, nur am Boden und ohne das,
   was eine ganze Bildzeile verdunkelt (Wand, Knick im Hintergrund). So steht jedes
   Modell auf dem Schatten, den es wirklich wirft; ein gezeichneter Schatten ließ die
   Fahrzeuge schweben oder lag als Platte unter ihnen. Nur Fotos ohne eigenen Schatten
   (bearbeitet, auf reinem Weiß) bekommen einen weichen gezeichneten.
5. **Durchsichtiger Grund:** Die Bühne hat keinen eigenen Hintergrund. Im Shop scheint der
   Token `stage` (Sand `#EFE7DC`) durch, auch beim Überfahren der Karte. Nur das
   Vorschaubild für geteilte Links (`og`) steht fest auf Sand.

Regeln:

- **Das Original bleibt**, wie bisher, im privaten Speicher. Jede Entscheidung lässt sich
  zurücknehmen.
- **Je Foto abschaltbar:** `media.assets.studio` (Stellwerk → Modell → Galerie, Haken
  „Fotostudio“; `PUT /admin/media/{id}/studio`). Umschalten rendert das Foto neu.
- **Neue Fotos** gehen durchs Fotostudio. **Fotos, die schon im Shop sind,** bleiben, wie
  sie sind (Migration 0022 setzt sie auf „aus“), und lassen sich einzeln einschalten.
- **Alle auf einmal:** „Alle Fotos umstellen …“ in der Galerie
  (`PUT /admin/media/studio`) schaltet das Fotostudio für jedes fertige Foto ein, das noch
  aus ist; der Worker rechnet sie nacheinander neu. Der Haken je Foto bleibt.
- **Beim Ausspielen von selbst:** Migration 0025 schaltet einmalig jedes fertige Foto
  ein, das noch aus ist, und lässt es neu rechnen, ohne Klick. Die Aufträge werden im
  Abstand von 20 Sekunden fällig, damit Bestellungen und Mails nicht hinter den Fotos
  warten. Wer danach ein Foto ausschaltet, behält es aus.
- **Findet das Fotostudio kein Modell** (Ausschnitt zu klein, zu groß, an drei Rändern
  abgeschnitten oder überwiegend unsicher, etwa bei einem Foto einer ganzen Kiste), erscheint das Foto unverändert; `image_details.studio_applied` sagt, was
  gezeigt wird, die Galerie schreibt es dazu.
- **Fehlt die Modelldatei**, rendert der Worker alle Fotos wie hochgeladen und meldet es
  beim Start (`media.studio_unavailable`). Kein Upload scheitert daran.

## Betrieb

- Modelldatei: `isnet-general-use.onnx` (Apache 2.0), rund 170 MB. Das Backend-Image lädt
  sie beim Bauen und prüft die SHA-256; ohne Zugang zu GitHub legt man sie vorher nach
  `backend/models/`. Pfad: `MB_STUDIO_MODEL_PATH`.
- Neue Abhängigkeiten: `onnxruntime`, `numpy`, `scipy`.
- Ein Foto braucht auf vier Kernen etwa fünf Sekunden und in der Spitze rund 1,3 GB
  Arbeitsspeicher im Worker. Es läuft immer nur ein Foto zugleich durchs Freistellen.
- **Schonung kleiner Server** (Nachtrag 18.11.2026: der Server mit 4 GB blieb beim
  Ausspielen stehen, als viele Fotos nacheinander umgerechnet wurden): Ein Foto fürs
  Fotostudio beginnt erst, wenn der Worker fünf Minuten (seit 23.11.: 90 Sekunden) läuft, 20 Sekunden nach dem
  vorigen Foto und nur, wenn der Server noch 1800 MB frei hat (`MemAvailable`;
  `MB_STUDIO_WARMUP_SECONDS`, `MB_STUDIO_PAUSE_SECONDS`, `MB_STUDIO_MIN_FREE_MB`).
  Sonst wird das Ereignis zurückgestellt (`PostponedError`), ohne dass ein Versuch
  zählt. Das Modell wird je Foto geladen und danach freigegeben. Der Worker-Container
  hat ein Speicherlimit (`WORKER_MEM_LIMIT`, 2 GB): Im schlimmsten Fall startet der
  Worker neu, nicht der Server.
  Nachtrag am selben Abend: 1800 MB frei und 20 Sekunden Pause waren zu vorsichtig,
  die Umrechnung kam kaum voran. Jetzt 1000 MB (ein Foto braucht etwa 750 MB über dem
  Grundbedarf des Workers) und 5 Sekunden.
- **Neue Fotos zuerst:** Ein Foto, das neu gerechnet wird, zeigt so lange seine
  bisherigen Größen (`ImageView.is_ready`) und tritt zurück, solange ein frisch
  hochgeladenes Foto wartet, das noch nichts zu zeigen hat.
- **Nichts hängt für immer** (Nachtrag 23.11.2026: Straßenbahn-Fotos standen über Nacht
  auf „wird bearbeitet“). Zwei Wege führten dorthin, beide ohne Fehlermeldung:
  1. Der Server hat dauerhaft weniger als `MB_STUDIO_MIN_FREE_MB` frei; das Foto wird
     endlos zurückgestellt. Jetzt geht ein Foto nach `MB_STUDIO_MAX_WAIT_SECONDS`
     (20 Minuten) Wartezeit trotzdem durch; das Speicherlimit des Workers fängt einen
     Engpass ab.
  2. Der Kernel beendet den Worker mitten im Foto (Speicherlimit). Die Transaktion der
     Outbox rollt zurück, kein Versuch zählt, nach dem Neustart beginnt dasselbe Foto
     von vorn. Jetzt zählt `media.assets.studio_tries` jeden Lauf, festgeschrieben vor
     dem Lauf; nach zwei Läufen ohne Ergebnis wird das Foto ohne Fotostudio gerechnet
     (`media.studio_skipped`). Haken „Fotostudio“ aus/an versucht es erneut.
  Schneller: Anlauf nach dem Start 90 statt 300 Sekunden, Speicher wird alle 30 statt
  120 Sekunden neu geprüft.

- **Schon freigestellte Bilder** (Nachtrag 23.11.2026, EDK 80-3: Renderbilder als PNG mit
  durchsichtigem Grund): `convert("RGB")` machte den durchsichtigen Grund schwarz, das
  Fotostudio hielt ihn für einen dunklen Hintergrund mit riesigem Schatten (grauer
  Kasten, ausgefranste Kanten). Jetzt geht ein solches Bild auf Weiß ins Fotostudio,
  wie ein Fotobox-Foto. Der gezeichnete weiche Schatten reicht nur noch 6 % der
  Modellgröße über die Standlinie (`SOFT_SHADOW_RISE`, vorher 30 %), sonst stand er
  neben schmalen Aufbauten als Kasten im Bild.

## Verworfen

- **Freistellen ohne neuronales Modell** (Hintergrund aus dem Bildrand schätzen): bei
  schwarzen und grauen Modellen vor grauem Schatten nicht verlässlich, im Versuch gingen
  ganze Teile verloren.
- **Fester Sand-Hintergrund im Bild:** passt nicht mehr, sobald die Karte beim Überfahren
  dunkler wird oder der Token sich ändert.
- **Fremder Dienst** (remove.bg, ChatGPT): Fotos verlassen das Haus, kosten je Bild, und
  das Ergebnis ist nicht bei jedem Foto gleich.
