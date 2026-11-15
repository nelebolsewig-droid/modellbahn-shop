# ADR 0011: Lager, Barcodes und Lieferbarkeit

Status: angenommen · 28.10.2026

## Kontext

Schritt 5 bringt das Lager: Plätze, einzelne Stücke mit Etikett, Scannen mit dem Handy,
Kommissionieren. Das Konzept (§5.4, §7) war vor drei Klärungen mit dem Inhaber geschrieben:

- **Die Kasse liest nur Strichcodes.** Im Laden und auf Messen kassiert der Inhaber mit
  SumUp; Artikel kommen per Handscanner oder CSV-Import hinein. QR-Codes auf den Etiketten,
  wie im Konzept geplant, könnte die Kasse nicht lesen.
- **Etiketten:** A4-Bögen und ein Brother QL mit 62-mm-Rolle. Der Drucker war in §13 noch
  offen.
- **Zwei Arten von Modellen:** solche, die vorrätig sind, und solche, die erst nach der
  Bestellung gefertigt werden. Der Shop soll das zeigen und danach handeln.

Bis Schritt 4 durfte jede aktive Variante unbegrenzt verkauft werden, und „Versendet“ ging
ohne Blick ins Lager.

## Entscheidung

### Plätze und Stücke

- **Lagerplätze sind ein Baum** mit `ltree`-Pfad und fünf Arten:
  - *Lager* (das Gebäude), darin *Regal* und *Ablage*;
  - im Regal *Fach* und *Box*, im Fach eine *Box*.
  - Ware liegt nur in Fach, Box und Ablage.
- **Der Code** steht auf dem Etikett am Regal und ändert sich nie.
  - Direkt im Lager ist er das Kürzel selbst (`R02`), darunter das Kürzel des
    Elternplatzes plus das eigene (`R02-F04-B12`).
  - Das Kürzel des Lagers bleibt draußen, damit die Etiketten kurz bleiben.
  - Ein Platz lässt sich nur entfernen, solange er leer ist und nichts darunter hängt.
- **Jedes Stück ist eine Einheit** mit eigenem Code:
  - zehn Zeichen Crockford-Base32, das letzte ist ein Prüfzeichen (Luhn mod 32);
  - gelesen wird er in Vierergruppen: `7KQ2 X9F4 MZ`.
  - Der Lebenslauf: *etikettiert* → *im Lager* → *reserviert* → *kommissioniert* →
    *versendet*, dazu *ausgebucht*.
- **Das Journal** (`inventory.stock_ledger`) hält jede Bewegung mit Platz, Zustand, Person
  und Scan fest.
  - Nichts wird gelöscht.
  - „Rückgängig“ ist eine Gegenbuchung, die auf die ursprüngliche verweist (`reverses_id`).
  - Der Server erlaubt das zehn Minuten lang, die Oberfläche bietet es zehn Sekunden groß an.
- **Der Teilebestand** (gedruckte Einzelteile in Boxen, Konzept §5.4) kommt mit der
  Fertigung in Schritt 6. Schritt 5 führt nur fertige Stücke.

### Etiketten: Strichcodes statt QR

- **Etikett eines Stücks:**
  - die **EAN-13 der Variante**, dieselbe Nummer wie in der Kasse (interner Bereich 20…,
    §13 Nr. 2);
  - den **Code 128 der Einheit**;
  - dazu Name, Maßstab, Ausführung und Artikelnummer.
- **Etikett eines Platzes:** der Code groß und als Code 128.
- **Format:** Das Backend erzeugt ein PDF (reportlab, Schrift Geist eingebettet), in zwei
  Formaten:
  - A4-Bogen mit 3 × 8 Etiketten zu 70 × 37 mm, etwa Avery Zweckform 3474. Ein angebrochener
    Bogen wird ab einem freien Feld bedruckt (`skip`).
  - Brother QL, Rolle 62 mm, je Etikett 62 × 29 mm.
- **Artikelliste für die Kasse:** `GET /admin/catalog/articles.csv`.
  - Format: Semikolon, UTF-8 mit BOM, Preise mit Dezimalkomma.
  - Inhalt: Name, Variante, Artikelnummer, EAN, Preis, MwSt., Kategorie und Lieferbarkeit,
    zum Import in SumUp.

### Zuteilung, Kommissionieren, Versand

- **Zuteilung je Stück.** Ist eine Bestellung bezahlt, bekommt jedes bestellte Stück eine
  Zuteilung (`inventory.allocations`).
  - Ist eine freie Einheit da, wird sie reserviert: die älteste zuerst (FIFO).
  - Sonst wartet das Stück auf die Fertigung (*backordered*), und das Ereignis
    `inventory.allocation.backordered` geht ins Stellwerk.
  - Neu eingelagerte Stücke bedienen zuerst die wartenden Zuteilungen, ebenfalls nach
    Eingang.
  - Eine Einheit gehört höchstens einer Zuteilung. Die Eindeutigkeit ist
    `DEFERRABLE INITIALLY DEFERRED`, damit zwei Stücke in einer Transaktion die Zuteilung
    tauschen können.
- **Kommissionieren** heißt, jedes Stück der Pickliste zu scannen.
  - Die Pickliste ist in Laufreihenfolge sortiert, nach Platz; die wartenden Stücke stehen
    am Ende.
  - Ein gleiches, freies Stück aus einem anderen Fach darf das reservierte ersetzen; das
    reservierte wird dann wieder frei.
  - Falsche Artikel und Stücke anderer Bestellungen werden abgelehnt.
- **Versand erst nach dem Kommissionieren:** `POST /admin/orders/{id}/ship` antwortet sonst
  mit 409 `order_not_picked`.
- **Ereignisse:**
  - Storno gibt die Stücke frei: Reserviertes geht zurück ins Lager, Kommissioniertes wartet
    mit Etikett aufs Einlagern.
  - Versand bucht die Stücke aus.
- **Mehrere Abnehmer je Ereignis.** `sales.order.paid` braucht jetzt Verkauf und Lager. Die
  Outbox merkt sich deshalb je Ereignis, welche Handler es schon verarbeitet haben
  (`outbox.handled_by`). Schlägt einer fehl, wird nur er wiederholt.

### Lieferbarkeit

- **Jede Variante ist „vorrätig“ oder „auf Bestellung“** (`allow_backorder`, im Stellwerk
  „Auf Bestellung“).
  - Eine Variante auf Bestellung hat eine Lieferzeit von–bis in Wochen, 1 bis 52.
  - Ohne Angabe gilt 4 bis 6 Wochen. (Seit ADR 0013: 1 bis 2 Wochen.)
- **Die Regel**, gleich im Lager (`availability()`) und im Frontend:
  - Liegen genug freie Stücke im Lager: **sofort lieferbar**.
  - Sonst bei einer Variante auf Bestellung: **wird gefertigt**, mit Lieferzeit.
  - Sonst **derzeit nicht lieferbar**.
- **Durchgesetzt** wird die Regel beim Erhöhen der Menge im Warenkorb und an der Kasse
  (409 `insufficient_stock`). Die Produktseite fragt die Lieferbarkeit live ab
  (`GET /store/products/{slug}/availability`, 15 s im Cache), denn die Seite selbst bleibt
  gecacht.
- **Die Lieferzeit steht vor dem Kauf da:** auf der Produktseite, im Warenkorb und an der
  Kasse („wir schicken alles zusammen in voraussichtlich 4–6 Wochen“).

### Scannen

- **Ein Scan ist eine Anfrage mit Gerätekennung** (`scan_id`, UUID).
  - Die API speichert die Antwort.
  - Eine Wiederholung bekommt dieselbe Antwort, ohne erneut zu buchen. Das macht die
    Offline-Warteschlange sicher.
- **Modi:**
  - *Einlagern:* Platz, dann Ware. Ein Stück, das schon woanders liegt, wird umgelagert.
  - *Kommissionieren:* Bestellung, dann Ware.
  - *Auskunft:* bucht nichts.
  - Umlagern als eigener Modus, Wareneingang und Inventur folgen mit der Fertigung.
- **Was gescannt wurde,** erkennt das Backend (`interpretations`).
  - Ein Code mit Vierergruppen wie `7KQ2-X9F4-MZ` wird als Einheit *und* als Platz gelesen;
    die Einheit gewinnt.
  - Eine EAN beim Einlagern lagert das älteste etikettierte Stück dieses Artikels ein.
  - Eine EAN beim Kommissionieren nimmt das reservierte Stück.
- **Kamera:**
  - wo vorhanden, der `BarcodeDetector` des Browsers (Chrome auf Android);
  - sonst dieselbe Schnittstelle aus zxing-wasm (Paket `barcode-detector`), etwa auf dem
    iPhone.
  - Das WebAssembly liegt unter `/zxing/` auf dem eigenen Server.
  - Die Content-Security-Policy erlaubt `'wasm-unsafe-eval'` nur unter `/admin`; der Shop
    bleibt bei der strengen Policy.
  - `html5-qrcode` aus dem Konzept entfällt.
- **Zwei Codes auf einem Etikett:** Die Kamera sieht EAN und Einheiten-Code zugleich.
  - Der Einheiten-Code gewinnt.
  - Eine EAN zählt erst, wenn sie 400 ms allein im Bild war.
  - Dieselbe Erkennung zählt einmal je 1,5 s.
- **Handscanner** werden am Tipprhythmus erkannt: mindestens sechs Zeichen, unter 35 ms
  Abstand, dann Enter. Ihr Enter löst keinen Knopf aus, der gerade den Fokus hat.
- **Die Scan-Sitzung ist eine reine Funktion** (Reducer, `src/lib/inventory/scan-session.ts`),
  kein XState wie im Konzept:
  - Drei Modi und ein linearer Ablauf brauchen keinen Automatenbaukasten.
  - Der Reducer läuft ohne Browser in Tests.
  - Die Seite wendet ihn zuerst auf einen Ref an, sodass der nächste Scan den gerade
    gewählten Platz schon mitschickt.
- **Ohne Netz:**
  - Die Scans warten in IndexedDB und gehen in der Reihenfolge ihres Entstehens mit
    derselben `scan_id` hinaus, sobald das Netz zurück ist.
  - Ein offline gescannter Platz gilt vorläufig, damit die folgende Ware weiß, wohin sie
    gehört; der Server prüft ihn beim Nachreichen.
- **Rückmeldung:** heller Doppelton oder tiefer Brummton (WebAudio), Vibration, ein
  farbiger Blitz im Sucher und eine große Antwortkarte.

### Rechte

- **Einlagern, Kommissionieren, Etiketten drucken und Ansehen** dürfen alle Mitarbeiter,
  auch Packer.
- **Plätze anlegen, Einheiten erfassen, Ausbuchen und Zuteilen von Hand** dürfen Inhaber
  und Mitarbeiter.

## Folgen

- **Kasse:** Die Kasse kennt jedes Etikett. Ein Stück an der Kasse zu verkaufen, bucht es
  im Shop aber noch nicht aus; dafür bräuchte es eine Anbindung an SumUp. Bis dahin
  bucht der Inhaber verkaufte Stücke im Stellwerk aus.
- **Zwei Etiketten je Bestand:**
  - Am Regal hängen Platzetiketten.
  - Jedes Stück hat seins.
  - Wer ein Stück ohne Etikett findet, druckt es auf der Seite der Einheit nach; der Code
    bleibt derselbe.
- **Ausverkauft:** Ein vorrätiger Artikel ist ausverkauft, sobald das Lager leer ist. Der
  Shop sagt es auf der Produktseite und nimmt keine Bestellung darüber hinaus an.
- **Lieferzeit:** Für Modelle auf Bestellung verspricht der Shop eine Lieferzeit. Sie ist
  je Variante gepflegt; eine Fertigungsplanung, die sie aus der Auslastung ableitet,
  kommt mit Schritt 8.
- **Smoke-Test:** Er prüft den ganzen Weg: Plätze anlegen, Etiketten-PDF, Einlagern per
  Einheiten-Code und EAN, Lieferbarkeit, Kommissionieren per Scan mit Ereignis im Strom,
  Versand, und ein bemaltes Modell, das in die Fertigung geht.
- **Altbestand:** Migration 0005 setzt bestehende Varianten mit Rückstand auf 4 bis
  6 Wochen. Alle anderen sind ab jetzt erst nach dem Einlagern kaufbar.

## Nachtrag 09.11.2026: Hersteller auf dem Etikett

Die EU-Produktsicherheitsverordnung (GPSR, Art. 9 Abs. 6) verlangt Name, Postanschrift
und elektronische Kontaktmöglichkeit des Herstellers auf dem Produkt oder seiner
Verpackung.

- **Wo:** Das Etikett jeder Einheit trägt den Hersteller rechts neben dem Code 128, hinter
  dessen Ruhezone. Kassen- und Lagerstrichcode bleiben unverändert.
- **Was:** Firma, Inhaber, Straße, Postleitzahl und Ort (bei Deutschland als `DE-17235`)
  und E-Mail, alles aus dem Impressum (`MB_IMPRINT_*`). Es gibt keine zweite Einstellung,
  und im Code steht keine Anschrift.
- **Wie groß:** bis 5 pt auf dem A4-Bogen und 4,6 pt auf der QL-Rolle. Reicht der Platz
  nicht, bricht die Zeile um und wird kleiner, höchstens auf 75 %. Weggelassen wird nichts.
- **Ohne vollständiges Impressum** (Entwicklung) bleibt der Platz leer.
- Lager- und Teileetiketten bleiben ohne Hersteller; sie verlassen die Werkstatt nicht.

## Nachtrag 09.11.2026: Tiefschwarz und als Bild für die Brother-App

- **Schwarz:** Alle Texte der Etiketten sind tiefschwarz, auch Überschrift, Ausführung und
  Artikelnummer. Thermodrucker kennen nur Schwarz; Grau käme als Punktmuster heraus.
- **Als Bild:** Brothers Apps (iPrint&Label, P-touch Editor) drucken Bilder, keine PDFs.
  Für die QL-Rolle gibt `printLabels` mit `format: png` jedes Etikett als PNG aus, mit
  300 dpi in reinem Schwarzweiß; bei mehreren als ZIP.
  - Das Stellwerk zeigt die Bilder einzeln zum Speichern und alle zusammen als ZIP.
  - Gerendert wird das PDF mit PDFium (`pypdfium2`), damit Bild und PDF gleich aussehen.
- **DHL-Label als Bild:** `…/shipping-label.png` liefert das DHL-Label ebenso als PNG.

## Nachtrag 09.11.2026: Preis auf dem Etikett

- **Preis:** Das Etikett einer Einheit nennt den Preis der Ausführung groß oben rechts,
  auf Höhe von „EINHEIT“, wie ein Preisschild (`79,90 €`). Es ist der Preis, den auch die
  Kasse per EAN berechnet, inklusive Mehrwertsteuer.
- **Stand des Drucks:** Ändert sich der Preis im Katalog, gilt das gedruckte Etikett nicht
  mehr; neue Etiketten druckt man auf der Seite der Einheit oder im Lager nach.
- Ohne Preis (z. B. ein Entwurf) bleibt die Stelle leer.
- **Lange Namen:** Auf der QL-Rolle passt eine zweite Zeile des Namens nur, wenn sie
  Ausführung und Artikelnummer nicht berührt; sonst wird der Name auf eine Zeile gekürzt.

## Nachtrag 11.11.2026: Stücke in Listen ein-, um- und ausbuchen

Im Stellwerk lagen mehr Stücke „unverbucht“ (etikettiert, nie eingelagert) als im Lager.
Shop und eBay zählen nur eingelagerte Stücke; ohne Scanner kam man an diesen Rückstand
nicht heran. Und Stücke ließen sich nur einzeln ausbuchen.

- **Stücke-Liste** (`/admin/lager/einheiten`, `GET /units`): die Stücke eines Artikels
  oder alle in einem Zustand, etwa alle unverbuchten über alle Artikel, nach Artikel
  gruppiert. Erreichbar aus dem Bestand („Stücke“ je Artikel, Hinweis „… unverbucht“).
- **Ankreuzen und gemeinsam buchen**, in der Stücke-Liste und im Inhalt eines Platzes:
  - „Einlagern …“ (nur Unverbuchte) oder „Umlagern …“: `POST /units/moves`. Gebucht wie der
    Einlager-Scan (Journal mit Person, ohne Scan; `inventory.stock.changed` je Stück;
    ein frei gewordenes Stück geht an die älteste wartende Bestellung). Reservierte
    behalten ihre Bestellung.
  - „Ausbuchen …“ mit Grund: `POST /units/scraps`, nur Inhaber und Mitarbeiter, wie das
    Ausbuchen einer Einheit.
  - Eine Transaktion, alles oder nichts. Alle Wege sperren Stücke nach ihrer Kennung
    (Sammelbuchungen, Freigeben und Versenden einer Bestellung, Scanner), so dass keine
    zwei Anfragen einander über Kreuz warten.
  - Bekannt, nicht behandelt: Wird eine bezahlte Bestellung genau in der Sekunde
    zugeteilt, in der ein ganzer Platz umgelagert wird, kann sie auf Nachbestellung
    landen, obwohl Bestand da ist (`skip_locked`). Über den Scanner lässt sie sich
    trotzdem kommissionieren.
  - Was schon am Ziel liegt oder schon ausgebucht ist, bleibt unberührt. Eine Wiederholung
    nach einem Netzfehler bucht deshalb nichts doppelt.
- **Was nicht geht:** Kommissionierte und versendete Stücke gehören zu einer Bestellung.
  Ausgebuchte und unbekannte lassen sich nicht verlegen. Ist eins dabei, lehnt der Server
  die ganze Anfrage ab (409 `units_not_movable` bzw. `units_not_scrappable`, `detail` nennt
  die Codes). Die Liste bietet für solche Stücke kein Kästchen an.
- **Reservierte Stücke ausbuchen:** wie bisher bei einem Stück. Die Zuteilung wird frei und
  bekommt ein anderes freies Stück, sonst wartet sie auf die Fertigung
  (`inventory.allocation.backordered`). Ein Stück aus derselben Auswahl springt dabei nie
  ein.
- **Grund des Ausbuchens** (Migration 0017, `inventory.units.scrap_reason`): verkauft
  (Messe, Laden, privat), beschädigt, fehlt bei Inventur, falsch erfasst. Er ist Pflicht im
  Stellwerk, auch auf der Seite einer Einheit; die Notiz bleibt frei. Ältere ausgebuchte
  Stücke haben keinen Grund.
- **Ein Stück von Hand verlegen:** Auf der Seite einer Einheit „Einlagern …“ bzw.
  „Umlagern …“, mit demselben Dialog und Endpunkt.
- **Einheiten erfassen ohne Platz** sagt jetzt, dass die Stücke bis zum Einlagern im Shop
  nicht lieferbar sind.

## Nachtrag 12.11.2026: Wieder einbuchen, Ausführung korrigieren, Inventur je Platz

Ausbuchen war eine Einbahnstraße, ein falsch etikettiertes Stück ließ sich nur ausbuchen und
neu erfassen (mit neuem Code), und gezählt wurde ein Platz, indem man die fehlenden Stücke
in der Liste suchte.

- **Wieder einbuchen** (`POST /units/restores`, Stücke und Platz): ein ausgebuchtes Stück
  liegt danach frei im gewählten Platz. Grund und Notiz des Ausbuchens entfallen; das
  Journal bucht `restore` (von *ausgebucht* ohne Platz nach *im Lager*). Wie beim Einlagern
  bekommt die älteste wartende Bestellung das Stück. Eine Bestellung, der es vor dem
  Ausbuchen gehörte, hat längst ein anderes oder wartet; sie bekommt es nicht bevorzugt
  zurück. Inhaber und Mitarbeiter, wie das Ausbuchen. Alles oder nichts, Stücke nach
  Kennung gesperrt; was schon im Zielplatz liegt, bleibt unberührt (409
  `units_not_restorable` für ein Stück, das nicht ausgebucht ist).
- **Ausführung korrigieren** (`POST /units/{code}/correction`): nur für unverbuchte oder
  freie Stücke, die nie kommissioniert wurden (kein `pick` im Journal), sonst 409
  `unit_not_correctable`. Ein Stück, das einmal in einem Paket lag, bleibt, was die
  Bestellung verkauft hat. Das Stück bleibt, wo es liegt; ein freies geht an eine
  Bestellung, die auf die neue Ausführung wartet.
  - **Journal:** Das Journal bekommt keine Spalte für die alte Ausführung. Jede Buchung
    trägt die Ausführung des Stücks zu ihrer Zeit (`variant_id`); die Buchung `correct`
    trägt die neue, die Buchung davor die alte. Der Lebenslauf liest beide daraus
    (`from_variant`, `to_variant`). Eine Spalte, die nur eine Art Buchung füllt, hätte nichts
    gespeichert, was nicht schon dasteht.
  - **Ereignisse:** `inventory.stock.changed` geht für beide Ausführungen hinaus, damit
    Stellwerk und eBay beide neu zählen.
  - **Etikett:** Die EAN darauf gehört zur Ausführung, der Code des Stücks bleibt. Der
    Dialog endet deshalb mit „Etikett neu drucken“.
- **Inventur je Platz** (`POST /locations/{code}/stocktakes`): Das Stellwerk listet die
  Stücke, die laut Journal im Platz selbst liegen (nicht in Plätzen darunter). Gezählt wird
  nur im Browser: abhaken oder scannen; ein Stück, das anderswo gebucht, unverbucht oder
  ausgebucht ist, wird als *gefunden* notiert; kommissionierte und versendete nicht, und
  auch keine aus einem Platz darin (eine Box im Fach wird für sich gezählt).
  - **Anfrage:** Sie nennt jedes erwartete Stück als vorhanden oder fehlend und die
    gefundenen. Fehlende werden ausgebucht (Grund `missing`, Notiz „Inventur R01-F01“; ihre
    Bestellung bekommt ein anderes Stück oder wartet), gefundene wie beim Umlagern
    eingelagert, ausgebuchte unter ihnen wieder eingebucht. Eine Transaktion; alle
    beteiligten Stücke werden nach Kennung gesperrt.
  - **Warum auch die fehlenden in der Anfrage stehen:** Der Server prüft, dass der Platz
    noch so ist, wie gezählt wurde. Kam während der Zählung ein Stück hinzu (jemand lagert
    gerade ein) oder ging ein vorhandenes weg, bucht er nichts (409 `stocktake_outdated`,
    `detail` nennt die Stücke). Würde er „fehlend“ selbst als „erwartet minus vorhanden“
    ausrechnen, buchte er ein eben eingelagertes Stück als fehlend aus. Das Stellwerk lädt
    den Platz dann neu; die Haken bleiben.
  - **Wiederholung:** Schon ausgebuchte fehlende und schon eingelagerte gefundene Stücke
    bleiben unberührt; dieselbe Anfrage nach einem Netzfehler bucht nichts doppelt.
  - Inhaber und Mitarbeiter, weil fehlende Stücke ausgebucht werden.
- **Migration 0018** erweitert `ck_stock_ledger_reason` um `restore` und `correct`. Das
  Zurückrollen macht aus `restore` ein `put_away` und aus `correct` ein `move`; das ältere
  Modell kennt beide nicht.
- **Modellseite:** Der Katalog zeigt je Ausführung freie, reservierte und unverbuchte
  Stücke (aus `GET /stock`), mit „Stücke“ und „Stücke erfassen“. Im Bestand des Lagers führt
  „Modell“ zurück in den Katalog.
