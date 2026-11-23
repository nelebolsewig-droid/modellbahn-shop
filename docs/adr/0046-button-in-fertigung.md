# ADR 0046: Button „In Fertigung“ am Bestellpult

Status: angenommen · 23.11.2026 · ergänzt ADR 0029 (Fertigung nach Bestellung) und ADR 0034

## Kontext
Seit ADR 0034 bekommt der Kunde einmal eine Mail, sobald eine Druckplatte für seine Stücke
startet. Wird ohne Druckauftrag im Stellwerk gefertigt (oder die Stücke hängen an keiner
Platte), erfährt er nichts. Das Team will ihn von Hand informieren, wie beim Versand.

## Entscheidung
- Bezahlte Bestellungen mit „Fertigung nach Bestellung“ zeigen am Bestellpult das Feld
  **Fertigung** mit dem Button „In Fertigung“ (alle Mitarbeiterrollen).
- `POST /admin/orders/{id}/making` setzt `making_started_at` und löst dasselbe Ereignis
  `sales.order.making_started` aus, mit `by_hand = true`. Die Mail sagt dann „Dein Modell
  ist jetzt in Fertigung“ statt „der Drucker läuft“.
- Nur einmal: Ist `making_started_at` gesetzt (von Hand oder durch den Drucker), ändert ein
  zweiter Druck nichts und schickt keine Mail. Keine Migration nötig.
