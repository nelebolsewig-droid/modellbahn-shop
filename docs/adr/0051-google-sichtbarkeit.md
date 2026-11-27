# ADR 0051: Sichtbarkeit bei Google (strukturierte Daten, Produkt-Feed)

Status: angenommen · 23.11.2026 · ergänzt ADR 0036 (sitemap.xml, robots.txt)

## Kontext
Der Shop soll bei Google mehr Bestellungen bringen. Sitemap und robots.txt gibt es seit
ADR 0036, aber Google bekam keine Produktdaten (Preis, Lieferbarkeit, Bilder), keine
eindeutige Adresse je Modell und eine Startseite ohne Suchbegriffe im Titel.

## Entscheidung
- Produktseiten tragen schema.org-JSON-LD `Product` (ein `Offer` je Variante, Preis in EUR,
  Lieferbarkeit: Lager → InStock, Fertigung nach Bestellung → MadeToOrder) und `BreadcrumbList`.
- Produktseiten setzen `canonical` auf `/produkte/<slug>` (ohne `?massstab=`) und absolute
  Open-Graph-Bilder; der Titel nennt die Maßstäbe („EDK 6 – Modell H0“).
- Die Startseite hat einen eigenen Titel und eine Beschreibung mit Suchbegriffen und trägt
  `OnlineStore` (Daten aus dem Impressum, MB_IMPRINT_*).
- `/google-produkte.xml`: Feed für Google Merchant Center (kostenlose Einträge in Google
  Shopping), eine Zeile je Variante. Fertigung nach Bestellung wird als `in_stock` mit
  `min/max_handling_time` (Wochen × 5 Arbeitstage) gemeldet, so wie Google es verlangt.
  Modelle ohne Bild fehlen, Google nimmt sie nicht an.
- Keine neue Einstellung, keine Migration; die Adresse kommt aus MB_PUBLIC_BASE_URL.
