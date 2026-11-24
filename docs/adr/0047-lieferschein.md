# ADR 0047: Lieferschein fürs Paket

Status: angenommen · 24.11.2026 · ergänzt ADR 0038 (Rechnungen) und ADR 0023 (Versandlabel)

## Kontext
Ins Paket soll ein ausgedruckter Lieferschein: was drin ist, für wen, von wem. Die Rechnung
(ADR 0038) entsteht erst beim Versand, braucht die Steuernummer und geht per Mail; zum
Packen taugt sie nicht.

## Entscheidung
- `GET /admin/orders/{id}/delivery-note.pdf` (alle Mitarbeiterrollen) zeichnet den
  Lieferschein bei jedem Aufruf neu, für bezahlte und versendete Bestellungen; sonst 409.
  Gespeichert wird nichts, die Bestellung ist der Beleg.
- Inhalt: Logo, Absender aus dem Impressum, Empfänger im Fenster (DIN 5008 B wie die
  Rechnung), Bestellnummer, Bestell- und Lieferdatum (Versandtag, vorher heute),
  Sendungsnummer und bei eBay deren Bestellnummer; je Position Häkchenkästchen, Artikel,
  Art.-Nr., Menge, dazu die Stückzahl im Paket. **Keine Preise.**
- Braucht keine Steuernummer: fehlt das Impressum, steht der Shopname als Absender.
- Stellwerk: Kasten „Lieferschein“ über dem Versandlabel, nach dem Versand ein Knopf neben
  „Label öffnen“.
