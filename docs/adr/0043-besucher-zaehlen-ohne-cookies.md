# ADR 0043: Besucher zählen ohne Cookies

Status: angenommen · 22.11.2026

## Kontext

Gefragt war, wie viele Besucher die Website jeden Tag hat. Ein Analysedienst (Google
Analytics) bräuchte ein Cookie-Banner und gibt Daten an Dritte; ein eigener Container
(Umami, Plausible) kostet Arbeitsspeicher, den der Server für das Fotostudio braucht.

## Entscheidung

- Jede Seite des Shops schickt einmal `POST /store/visits` (`VisitBeacon` im
  Shop-Rahmen). Kein Cookie, nichts im Browser gespeichert. Seiten ohne Skript (fast alle
  Crawler) zählen damit nicht; Bots, die sich in der Browserkennung zu erkennen geben,
  verwirft der Server.
- Ein Besucher ist der BLAKE2b-Hash aus IP-Adresse und Browserkennung mit einem
  zufälligen Schlüssel des Tages (`site.visit_days.salt`). Der Hash steht in
  `site.visit_marks` nur, damit derselbe Besucher am Tag einmal zählt.
- Mit dem ersten Aufruf eines neuen Tages werden die Hashes und Schlüssel der Vortage
  gelöscht. Übrig bleiben je Tag `visitors` und `page_views`.
- Das Stellwerk zeigt auf „Heute“ (Büro) die Kachel „Besucher“: heute, gestern,
  Ø 30 Tage und die letzten 30 Tage als Balken (`GET /admin/visits?days=30`).
- Die Datenschutzerklärung (Abschnitt 2) beschreibt das.

## Folgen

- Kein Cookie-Banner, keine Auftragsverarbeitung mit Dritten, kein neuer Dienst.
- Mehrere Personen hinter einer Adresse mit gleichem Browser zählen als einer; wer am
  Tag Browser oder Netz wechselt, als zwei. Für die Frage „wie viele am Tag“ genügt das.
- Keine Herkunft, keine Einzelseiten, keine Verweildauer. Ließe sich später als weitere
  Tageszahlen ergänzen.
