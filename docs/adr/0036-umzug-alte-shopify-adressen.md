# ADR 0036: Alte Shopify-Adressen, Sitemap und Zweitnamen beim Umzug

Status: angenommen · 18.11.2026 · ergänzt „Später: www.adp-modelle.de übernehmen“ in `docs/BETRIEB.md`

## Kontext

Bis zum Umzug verkauft Shopify unter `www.adp-modelle.de`. Google, Stammkunden und Links in
Foren kennen dessen Adressen: `/products/<handle>`, `/collections/<handle>`,
`/collections/<x>/products/<handle>`, `/pages/<seite>`, `/policies/<richtlinie>`, `/cart`,
`/account`, `/search?q=`. Nach dem Umzug liefen sie alle ins Leere, und Google würde die
Seiten erst nach Wochen neu finden. `docs/BETRIEB.md` behauptete schon, der Shop leite sie
weiter; im Code gab es das nicht. Es fehlten auch `sitemap.xml` und `robots.txt`, und
`adp-modelle.de` ohne `www` war nirgends vorgesehen.

Die Handles kennt nur der Shopify-Export. Viele Produkte heißen hier anders, weil der Shop
Slugs aus dem Namen bildet (Umlaute ausgeschrieben, ADR 0013).

## Entscheidung

- **Feste Seiten** (Richtlinien, bekannte `/pages/…`, Warenkorb, Konto, `/products`,
  `/collections`) stehen als `SHOPIFY_PAGE_REDIRECTS` in `frontend/next.config.ts` und
  antworten mit 301, wie Shopify selbst.
- **Produkte** beantworten Route-Handler unter `frontend/src/app/(shopify)`
  (`/products/[handle]` und `/collections/[collection]/products/[handle]`), in dieser Reihenfolge:
  1. Der Handle steht in `frontend/src/lib/site/shopify-produkte.json` (Handle → Slug): 301.
  2. Es gibt ein Produkt mit diesem Slug: 301.
  3. Sonst 302 auf die Katalogsuche mit den Wörtern des Handles, ohne Cache. Nicht 301,
     damit ein späterer Eintrag in der JSON-Datei übernimmt.
- **Kollektionen** gehen mit 301 auf `/katalog?kategorie=<handle>`; die Katalogseite leitet
  das schon auf den Maßstab mit den meisten Modellen dieser Kategorie weiter und zeigt bei
  unbekannter Kategorie den ganzen Katalog. `all` und `frontpage` gehen auf `/katalog`.
  **Suche:** `/search?q=` geht auf `/katalog?suche=`.
- Die Antworten tragen eine **relative** `Location`: Hinter Caddy kennt Next.js das
  öffentliche Schema nicht, eine `http://`-Adresse kostete einen Sprung mehr.
- **Die JSON-Datei** schreibt `scripts/shopify_weiterleitungen.py` aus dem Produkt-Export
  von Shopify: gleicher Handle (kein Eintrag), gleicher Name, oder ähnlich (zum Prüfen).
  Von Hand ergänzte Einträge bleiben erhalten.
- **`/sitemap.xml`** nennt die festen Seiten, jeden Maßstab und jede Kategorie mit Modellen
  und jedes Produkt im Shop, mit `MB_PUBLIC_BASE_URL` als Adresse (der Web-Container bekommt
  die Variable jetzt auch). Ist die API weg, stehen nur die festen Seiten darin, statt 500.
  **`/robots.txt`** sperrt Stellwerk, API, Konto, Kasse, Warenkorb und Bestellseiten und
  nennt die Sitemap.
- **Zweitnamen:** `SITE_ALIASES` (z. B. `adp-modelle.de, neu.adp-modelle.de`) leitet Caddy
  mit 301 auf `SITE_ADDRESS`, Pfad und Query bleiben. Ohne Wert antwortet der Block nur auf
  den nie auflösbaren Namen `alias.invalid` über HTTP und holt kein Zertifikat.

## Folgen

- Nach dem Umzug findet jede alte Produktadresse ihr Produkt, sobald der Export einmal
  durch das Skript gelaufen ist; vorher immerhin die passende Suche.
- Neue 404 aus der Google Search Console trägt man in die JSON-Datei oder in
  `SHOPIFY_PAGE_REDIRECTS` nach.
- `SITE_ALIASES` erst setzen, wenn die Namen per DNS auf den Server zeigen, sonst versucht
  Caddy das Zertifikat immer wieder.
