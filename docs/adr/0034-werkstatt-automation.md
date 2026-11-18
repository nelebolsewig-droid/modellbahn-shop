# ADR 0034: Werkstatt-Automation

Status: angenommen · 18.11.2026 · ergänzt ADR 0029 (Nachfertigen)

## Kontext

Bis jetzt lief nichts von selbst. Kam eine bezahlte Bestellung für ein Modell ohne
Bestand, stand sie unter „Zu fertigen“, und jemand musste die Teile aus der Stückliste
heraussuchen und die Druckplatten von Hand planen. Die Kundschaft hörte nach der
Bestellbestätigung nichts mehr, bis das Paket unterwegs war. Und wer morgens in die
Werkstatt kam, musste erst das Stellwerk öffnen, um zu wissen, was ansteht.

## Entscheidung

1. **Druckplatten planen sich selbst** (`manufacturing/application/automation.py`,
   `domain/planning.py`). Nach jedem Rückstand (`inventory.allocation.backordered`) und
   einmal in der Stunde rechnet der Worker je Teil: was die Stücklisten der wartenden
   Stücke brauchen, abzüglich der Teile in den Kisten und im Wareneingang und der Teile
   auf offenen Platten. Was fehlt, kommt in volle Platten (`parts_per_plate`) auf den
   Drucker der passenden Technik mit der kürzesten Warteschlange, der in Betrieb ist.
   Die Notiz der Platte nennt die Bestellungen („Automatisch geplant für MB-…“).
   - Es wird nur geplant, was fehlt. Ein zweiter Lauf, ein wiederholtes Ereignis oder
     zwei Bestellungen zugleich planen nichts doppelt; die Drucker werden für den Lauf
     gesperrt, zwei Läufe warten aufeinander.
   - Ohne Stückliste oder ohne passenden Drucker wird nichts geplant; der stündliche Lauf
     holt es nach, sobald es eine Stückliste oder einen Drucker gibt.
   - Platten werden nicht mit Bestellungen verknüpft. Welche Bestellung eine Platte
     bedient, ergibt sich aus Stücklisten und wartenden Stücken. So bleibt die Planung
     frei: Platten verschieben, stornieren oder von Hand ergänzen bricht nichts.
   - `MB_AUTOPLAN=false` schaltet die Planung ab.
2. **Mail, wenn der Drucker startet.** Startet eine Platte, notieren alle bezahlten
   Bestellungen, deren wartende Stücke Teile dieser Platte brauchen, den Zeitpunkt
   (`sales.orders.making_started_at`, einmal). Die Kundschaft bekommt einmal die Mail
   „Deine Bestellung … ist in der Werkstatt“. Bestellungen von eBay bekommen keine.
3. **Werkstatt-Ticker** auf der Bestellseite: Für eine bezahlte Bestellung mit Fertigung
   zeigt er „Eingeplant“ und, sobald gedruckt wird, seit wann.
4. **Morgenmail „Heute dran“** an die Adresse des Shops (Impressum), ab 7 Uhr deutscher
   Zeit, einmal am Tag (`sales.daily_digests`): Pakete zum Packen, was in der Werkstatt
   entsteht, Drucker und Platten, gestörte Drucker, Bestellungen, die seit drei Tagen auf
   Geld warten, und was gestern bezahlt wurde. Scheitert der Versand, versucht der Worker
   es zehn Minuten später wieder; nach 18 Uhr nicht mehr.

## Folgen

- Migration 0023: `sales.orders.making_started_at`, Tabelle `sales.daily_digests`.
- Neue Fassaden: `inventory.contracts.demand` (wartende Stücke, Teilevorrat),
  `manufacturing.contracts.parts.load_print_job_parts` und `load_workshop_state`.
- Wer viele Drucker hat oder Platten mischt, plant weiterhin von Hand nach; die
  Automatik füllt nur die Lücke. Gemischte Platten (mehrere Teile auf einer) plant sie
  nicht, weil die Druckzeit dann nur der Slicer kennt.
