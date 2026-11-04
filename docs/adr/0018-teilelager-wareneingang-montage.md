# ADR 0018: Teilelager, Wareneingang und Montage

Status: angenommen · 04.11.2026

## Kontext

Mit Schritt 6a kennt das System Drucker, Teile, Stücklisten und Druckaufträge (ADR 0017).
Was eine fertige Platte hervorbringt, verschwand bisher aber im Nichts:

- Das Lager führte nur fertige Stücke (ADR 0011).
- Gedruckte Einzelteile in ihren Boxen kannte es nicht.
- Eine Einheit entstand nur „von Hand“ (Einheiten erfassen), ohne Bezug zu den Teilen,
  aus denen sie gebaut ist.

Das Konzept (§5.4, §7) sieht dafür Teilebestand, Wareneingang und Montage vor. Schritt 6b
setzt das um.

## Entscheidung

### Teilebestand

- **Teile liegen in Boxen und werden gezählt, nicht einzeln geführt**
  (`inventory.part_stock`: Teil, Platz, Menge).
  - Die Menge ist nie negativ; das prüft die Datenbank.
  - Eine geleerte Box behält ihre Zeile mit 0.
  - Teile liegen dort, wo auch Einheiten liegen dürfen: Fach, Box, Ablage.
- **Ein eigenes Teilejournal** (`inventory.part_ledger`), abweichend vom Konzept, das ein
  gemeinsames Journal für Teile und Einheiten vorsah.
  - Begründung: Eine Einheit wechselt ihren Zustand, ein Teil seine Menge. Ein gemeinsames
    Journal hätte für jede Zeile die Hälfte seiner Spalten leer gelassen.
  - Jede Zeile ist eine Bewegung mit Menge: woher (Eingang, Platz) und wohin (Platz,
    Einheit, nirgends). Gründe: *eingelagert*, *montiert*, *gezählt*, *ausgebucht*,
    *rückgängig*.
  - Eine Prüfung (`ck_part_ledger_shape`) legt je Grund fest, welche Seiten gesetzt sind.
    Eine Montage ohne Einheit oder eine Zählung ohne Platz lehnt die Datenbank ab.
  - Nichts wird gelöscht. Rückgängig ist eine Gegenbuchung mit `reverses_id`.
- **Teile kommen aus der Fertigung:** Fremdschlüssel auf `manufacturing.parts` über den
  Vertrag des Moduls (`PART_REFERENCE`). Ein Teil im Lager lässt sich archivieren, aber nicht
  löschen (409 `part_in_use`).

### Wareneingang

- **Eine fertige Platte legt ihre guten Teile in den Wareneingang:**
  - Der Worker reagiert auf `manufacturing.print_job.completed`. Er liest die Zeilen der
    Platte über den Vertrag der Fertigung, nicht aus dem Ereignis.
  - Je Teil entsteht ein *Eingang* (`inventory.part_receipts`).
  - Der Eingang hängt mit einem zusammengesetzten Schlüssel an der Zeile der Platte, von der
    die Teile stammen. Je Platte und Teil gibt es höchstens einen.
  - Eine doppelte Zustellung bucht also nichts doppelt.
  - Das Ereignis `inventory.parts.arrived` erscheint im Stellwerk („Druck 17 · 11 Teile“).
- **Eingelagert wird per Scan, ohne eigenen Modus:**
  - Im Modus *Einlagern* zuerst die Box scannen, dann das **Teileetikett**.
  - Alle offenen Teile dieses Teils kommen dann in die Box, die ältesten Eingänge zuerst.
  - Das Konzept sah einen eigenen Modus „Wareneingang“ vor (Druckauftrag wählen, Box
    scannen). Eine Platte trägt aber oft mehrere Teile, die in verschiedene Boxen gehören.
    Erst das Teileetikett sagt, welches gemeint ist.
  - Ein Scan lässt sich zehn Minuten lang zurücknehmen, solange die Teile noch in der Box
    liegen. Sie warten dann wieder im Wareneingang.
- **Was nie in einer Box ankommt**, bucht ein Mitarbeiter aus, mit Grund
  (`POST /admin/inventory/receiving/{id}/write-off`). Gute plus ausgebuchte Teile sind
  nie mehr als die Platte hergab; das prüft die Datenbank.

### Teileetiketten

- **Das Etikett klebt an der Box, nicht am Teil** (Konzept §5.4).
  - Es zeigt die Teilenummer als Code 128 (`STW-ALT-DACH-H0`), den Namen, Maßstab und
    Technik, im Layout der Platzetiketten.
  - Formate wie bei allen Etiketten: A4-Bogen 70 × 37 mm oder Brother QL 62 mm.
- **Der Scanner erkennt Teilenummern als dritte Lesart:**
  - Eine Teilenummer sieht aus wie ein Platzcode. Deshalb kommt sie nach den Plätzen: Gibt
    es einen Platz mit diesem Code, gewinnt der Platz.
  - Teilenummern mit Abschnitten über acht Zeichen (`STW-SCHORNSTEIN-H0`) sind nur
    Teilenummern.
  - Die Auskunft zeigt zu einem Teil den Bestand, die Boxen und den Wareneingang.

### Zählen

- **„Gezählt“ setzt die Menge in einer Box auf das, was dort liegt.** Das Journal bucht den
  Unterschied, mit Hinweis („Altbestand“, „zwei zerbrochen“).
- So kommen auch Teile ins Lager, die schon vor dem System gedruckt wurden.

### Montage

- **Die Montage nimmt Teile nach der Stückliste der Variante** (Produkt im Maßstab) und
  erzeugt Einheiten mit Etikett.
- **Der Plan** (`GET /admin/inventory/assembly-plan`) sagt, bevor etwas gebucht wird:
  - je Teil den Bedarf (je Stück × Anzahl), den Bestand und was fehlt;
  - aus welchen Boxen genommen wird, in Laufreihenfolge;
  - wie viele Stücke der Bestand hergibt.
  - Angebrochene Boxen werden zuerst geleert.
- **Die Buchung** (`POST /admin/inventory/assemblies`, 1 bis 50 Stück) läuft in einer
  Transaktion:
  1. Die Bestände der Teile werden gesperrt, in fester Reihenfolge, damit zwei Montagen
     nicht übers Kreuz warten.
  2. Der Plan wird neu berechnet. Fehlt inzwischen etwas: 409 `parts_missing`.
  3. Die Einheiten werden etikettiert, auf Wunsch gleich eingelagert. Wartende Bestellungen
     bekommen sie zuerst, wie beim Einlagern.
  4. Jede Entnahme nennt im Teilejournal ihre Einheit. **Jedes Stück weiß, aus welchen
     Boxen seine Teile stammen**; die Seite der Einheit zeigt es.
- Ohne Stückliste gibt es nichts zu montieren: 409 `no_bill_of_materials`.
  „Einheiten erfassen“ bleibt für Stücke ohne Stückliste.

### Live und Rechte

- **Ereignisse:**
  - `inventory.part_stock.changed`, je Teil und Weg zusammengefasst (eine Montage von zehn
    Stück meldet „20 Schornsteine aus R02-F04-B12“ einmal);
  - `inventory.parts.arrived`.
  - Teilelager, Wareneingang, Teileseite und Montageplan laden sich damit von selbst neu.
- **Rechte:**
  - Einlagern per Scan, Etiketten und Ansehen: alle Mitarbeiter, auch Packer.
  - Zählen, Ausbuchen und Montieren: Inhaber und Mitarbeiter, wie „Einheiten erfassen“.

### Im Stellwerk

- **„Lager“** zeigt zusätzlich:
  - den **Wareneingang** als Lieferscheine, einen je Platte;
  - das **Teilelager**, je Teil mit einer Zeichnung des Sichtlagerkastens, der sich mit dem
    Bestand füllt, und den Boxen als Marken.
- **`/admin/lager/teile/{Teilenummer}`:** Boxen, Wareneingang, Journal, Etikett.
- **`/admin/lager/montage`:**
  - Artikel wählen, Stückzahl, Platz;
  - die **Entnahmeliste** wie die Positionsliste einer Zeichnung, mit „nimm 3“ je Box;
  - eine Reihe Bausatz-Felder, die zeigt, wie viele Stücke der Bestand hergibt.
- Lagerplätze zeigen ihre Teile, Einheiten die Teile, aus denen sie montiert wurden.

## Folgen

- **Die Planung (Schritt 8)** liest Teilebestand, Wareneingang und Stücklisten. Damit lässt
  sich der Nettobedarf an Teilen ausrechnen (Konzept §8.2).
- **Umlagern von Teilen** zwischen Boxen gibt es noch nicht. Bis dahin: zweimal zählen. Es
  kommt mit dem Modus Umlagern für Einheiten.
- **Inventur** bleibt ein Vorhaben (Konzept §7). Das Zählen je Box ist ihr Anfang.
- **Ohne Netz** gilt ein Teileetikett im Scanner vorläufig als Platz, wie jeder Code dieser
  Form. Der Server entscheidet beim Nachreichen.
