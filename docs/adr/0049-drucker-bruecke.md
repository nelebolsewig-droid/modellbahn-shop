# ADR 0049: Drucker-Brücke: die Drucker füllen die Fertigung selbst

Status: angenommen · 24.11.2026 · ergänzt ADR 0017 (Fertigung) und ADR 0034 (Automation)

## Kontext
Die Druckerhalle (`/admin/fertigung`) lebt nur, wenn jemand „Start“ und „Fertig“ drückt.
Das tut in der Werkstatt niemand, also blieb sie leer. Die Resin-Drucker (Elegoo Saturn 3
Ultra und 4 Ultra) sprechen im WLAN aber SDCP: Suche per UDP (Port 3000), Zustand per
WebSocket (Port 3030) mit Datei, Schicht, Druckzeit und einer eigenen Kennung je Druck
(`TaskId`). Der Server steht bei STRATO und erreicht das Werkstatt-WLAN nicht.

## Entscheidung
- **Ein kleines Programm in der Werkstatt** (`scripts/werkstatt/drucker_bruecke.py`, Mac
  oder Raspberry Pi) liest alle Drucker und schickt alle 15 s die Lage an
  `POST /api/v1/webhooks/printer-bridge`. Es baut nur Verbindungen nach außen auf.
- **Schlüssel:** `Authorization: Bearer <MB_PRINTER_BRIDGE_TOKEN>`. Ist er leer, antwortet
  der Endpunkt 404. Kein Cookie, kein CSRF-Header (Webhook-Pfad), nicht im OpenAPI.
- **Der Code im Stellwerk** (`D01`) ordnet den Drucker zu; die Brücke kennt Code → IP.
- **Druck startet:** die wartende Platte des Druckers mit dem Teil, dessen Teilenummer im
  Dateinamen steht (`STW-ALT-DACH-H0 x4.ctb`), sonst eine neue Platte mit diesem Teil
  (Stückzahl = Teile je Platte). Kennt das Stellwerk das Teil nicht, legt die Brücke es an
  (ADR 0050). Die Druckdauer kommt vom Drucker.
- **Druck fertig** → Nachbearbeitung. Die guten Teile zählt weiter ein Mensch beim
  Abschließen, denn erst das bucht sie ins Lager.
- **Druck abgebrochen** → Platte fehlgeschlagen („Am Drucker abgebrochen“).
- **Einmal buchen:** `print_jobs.printer_task_id` (eindeutig) und `slice_file`
  (Migration 0034). Jede Meldung sagt den ganzen Zustand; doppelte oder verlorene Meldungen
  ändern nichts. Läuft ein anderer Druck als der gebuchte, ging der alte in die
  Nachbearbeitung.
- Ein Drucker, der im Stellwerk nicht „in Betrieb“ ist, startet keine Platte.

## Folgen
- Startet eine Platte für eine Bestellung, bekommt der Kunde wie bisher seine Mail
  „Im Druck“ (ADR 0034), jetzt ohne Klick.
- Die Planung sieht echte Druckzeiten.
- Dateinamen sollten die Teilenummer tragen; sonst nimmt die Brücke die nächste Platte.
