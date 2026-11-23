# ADR 0046: Werkstatt-Schritte „Im Druck“ und „Lackierung & Montage“ am Bestellpult

Status: angenommen · 23.11.2026 · ergänzt ADR 0029 (Fertigung nach Bestellung) und ADR 0034

## Kontext
Seit ADR 0034 bekommt der Kunde einmal eine Mail, sobald eine Druckplatte für seine Stücke
startet. Wird ohne Druckauftrag im Stellwerk gefertigt, erfährt er nichts. Das Team will ihn
von Hand informieren, wie beim Versand, und zwar bei zwei Schritten: Druck sowie Lackierung
und Montage.

## Entscheidung
- Bezahlte Bestellungen mit „Fertigung nach Bestellung“ zeigen am Bestellpult das Feld
  **Fertigung** mit zwei Schritten (alle Mitarbeiterrollen), jeweils mit Rückfrage.
- **Im Druck**: `POST /admin/orders/{id}/making` setzt `making_started_at` und löst
  `sales.order.making_started` aus (mit `by_hand = true`); die Mail sagt „Dein Modell ist
  jetzt im Druck“. Startet eine Druckplatte, passiert das wie bisher von selbst.
- **Lackierung & Montage**: `POST /admin/orders/{id}/finishing` setzt
  `finishing_started_at` (Migration 0033) und löst `sales.order.finishing_started` aus,
  mit eigener Mail. Ist „Im Druck“ noch leer, wird es mit gesetzt (ohne zweite Mail).
- Jeder Schritt nur einmal: Ein zweiter Druck ändert nichts und schickt keine Mail.
- Der Werkstatt-Ticker auf der Bestellseite des Kunden zeigt den Schritt
  „Lackieren und Montage“.
