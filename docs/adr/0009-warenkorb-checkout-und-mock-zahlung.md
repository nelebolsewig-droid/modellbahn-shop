# ADR 0009: Warenkorb, Checkout und Mock-Zahlung

Status: angenommen · 25.10.2026

## Kontext

Mit Schritt 4 wird im Shop gekauft: Warenkorb, Bestellung mit Konto oder als Gast,
Zahlung, Adressbuch, Bestellhistorie und im Stellwerk Versand und Storno (Konzept §12).
Ein Zahlungsanbieter ist noch nicht ausgewählt. Dabei sollen vier Dinge nicht passieren:
Der Browser bestimmt den Preis. Ein doppelter Klick oder eine abgerissene Verbindung
bestellt oder bucht zweimal. Eine fremde Bestellung wird sichtbar. Der Verkauf greift in
Interna des Katalogs oder der Identität ein. Konzept §9.3 sah für den Warenkorb Routen mit
der Kennung im Pfad vor (`POST /carts`, `/carts/{cartId}`).

## Entscheidung

- **Warenkorb auf dem Server, benannt durch ein Cookie.** `mb_cart` ist HttpOnly,
  `SameSite=Lax`, hinter HTTPS `Secure` (wie die Sitzungscookies, `MB_COOKIE_SECURE`) und
  gilt 31 Tage, einen Tag länger als der Warenkorb selbst.
  Die Routen heißen `GET /store/cart` sowie `PUT` und `DELETE /store/cart/lines/{variantId}`.
  Das weicht von §9.3 ab: Eine Kennung im Pfad hätte im Browser-Speicher gelegen, für
  Skripte lesbar, und jede Route hätte zusätzlich prüfen müssen, wem der Warenkorb gehört.
  Das Cookie entsteht erst beim ersten Artikel; wer nur schaut, bekommt keins. Ein Job
  im Worker löscht alle sechs Stunden abgelaufene Warenkörbe.
- **Preise kommen immer aus dem Katalog.** Der Verkauf liest Varianten über den Vertrag
  `catalog.contracts.load_sale_variants`: Preis, SKU, Titel, Bild, ob kaufbar. Der Browser
  schickt beim Bestellen nur die Summe mit, die er angezeigt hat (`expected_total_cents`).
  Weicht sie von der Summe des Servers ab, wird nichts bestellt (409 `price_changed`); der
  Shop lädt den Warenkorb neu und zeigt die neue Summe.
- **Keine Fremdschlüssel vom Verkauf auf Varianten.** Eine Variante ist keine Aggregatwurzel
  und darf später umbenannt oder archiviert werden. Bestellpositionen frieren SKU, Titel,
  Spurweite, Ausführung, Preis, Produkt-Slug und Bild ein. Den Kunden verknüpft der
  zusammengesetzte Fremdschlüssel `(customer_account_id, customer_kind)` auf
  `identity.accounts(id, kind)`; die Datenbank lässt dort nur Kundenkonten zu.
- **Idempotenz über einen Pflicht-Header.** `POST /store/checkouts` und
  `POST /store/orders/{token}/payments` verlangen `Idempotency-Key` (UUID). Der Schlüssel
  steht eindeutig an der Bestellung (`checkout_key`) bzw. Zahlung (`idempotency_key`),
  daneben ein SHA-256-Fingerabdruck der Anfrage. Dieselbe Anfrage noch einmal liefert das
  erste Ergebnis mit `Idempotent-Replayed: true`; eine andere Anfrage mit demselben
  Schlüssel wird abgelehnt (409 `idempotency_key_reused`). Gegen das Rennen zweier gleicher
  Anfragen sperrt der Checkout zuerst den Warenkorb (`FOR UPDATE`) und prüft dann den
  Schlüssel; eine Verletzung der Eindeutigkeit wird als Wiederholung beantwortet. Der Shop
  verwendet für einen Wiederholungsversuch denselben Schlüssel und nach einem Erfolg einen
  neuen.
- **Zahlung hinter einem Port.** Der Anwendungskern kennt nur `PaymentGateway` mit
  `charge` und `refund`. Bis ein Anbieter feststeht, steht dort `MockPaymentGateway`; der
  Kunde wählt im Shop sichtbar „Testzahlung“ das Ergebnis: gelingt, wird abgelehnt (die
  Bestellung bleibt offen, ein neuer Versuch ist möglich) oder Dienst gestört (503 mit
  `Retry-After: 30`, es wird nichts gespeichert). Ein Anbieter wie Stripe wird ein weiterer
  Adapter; Webhooks kommen dann dazu.
- **Lebenslauf einer Bestellung.** `pending_payment` → `paid` → `shipped`; storniert wird
  aus `pending_payment` (nach 24 Stunden ohne Zahlung automatisch, Job alle 15 Minuten)
  oder durch den Shop aus `paid` mit Erstattung. Die Nummer `MB-{Jahr}-{fünfstellig}` kommt
  aus einer Sequenz. Owner und Mitarbeiter dürfen alles; Packer sehen und versenden, dürfen
  aber nicht stornieren (403).
- **Gäste sehen ihre Bestellung über einen geheimen Link.** `public_token` ist ein
  zufälliger Token mit 256 Bit; die Seite `/bestellung/{token}` ist `noindex` und sendet
  keinen Referrer. Mit Konto gibt es die Bestellung zusätzlich unter
  `/store/account/orders/{nummer}`; ein fremdes Konto bekommt 404.
- **Übernahme von Gastbestellungen** (ADR 0005). Auf `identity.account.email_verified`
  ordnet der Verkauf alle Gastbestellungen mit derselben Adresse dem Konto zu; bestellt ein
  Gast mit der Adresse eines schon bestätigten Kontos, wird die Bestellung sofort
  zugeordnet. `identity.account.deleted` löscht das Adressbuch; Bestellungen bleiben für die
  Aufbewahrungsfristen.
- **E-Mails nach § 312i BGB.** Direkt nach dem Bestellen geht eine Eingangsbestätigung
  mit Positionen, Summe, Zahlungslink und Frist (deutsche Zeit) raus. Danach folgen
  Zahlungseingang, Versand mit Sendungsnummer und Storno mit Hinweis und Erstattung. Alle
  E-Mails verschickt der Worker aus der Outbox. Kommt die Eingangsbestätigung erst nach der
  Zahlung an, verlinkt sie die Bestellung statt der Zahlung.
- **Adressbuch.** Höchstens 20 Adressen je Konto, genau eine ist Standard: Die erste wird es
  von selbst, beim Löschen übernimmt die älteste übrige. Die Datenbank erzwingt höchstens
  einen Standard mit einer aufschiebbaren `EXCLUDE`-Bedingung, damit ein Wechsel in einer
  Transaktion möglich ist.
- **Versand in zwei Zonen.** Deutschland 4,90 €, ab 50 € frei; Österreich 9,90 €, ab 100 €
  frei. Die Preise enthalten 19 % Umsatzsteuer, ausgewiesen wird der enthaltene Betrag,
  kaufmännisch auf den Cent gerundet.

## Folgen

- Kein Preis, keine Versandkosten und keine Steuer werden im Browser festgelegt. Der Shop
  rechnet dieselben Formeln nur nach, um vor dem Absenden die Summe für das gewählte Land zu
  zeigen.
- Wiederholte oder parallele Anfragen sind ungefährlich. Der Preis: Jeder Client muss den
  Header senden; ohne ihn antwortet die API mit 422. Das Frontend erledigt das in
  `useIdempotencyKeys`.
- Weil es keine Fremdschlüssel auf Varianten gibt, prüft der Verkauf Kaufbarkeit selbst
  über den Vertrag. Ein Warenkorb mit nicht mehr kaufbaren Artikeln geht nicht zur Kasse
  (409 `cart_items_unavailable`), bis der Kunde sie entfernt.
- Der Mock ist für den Betrieb mit echtem Geld nicht geeignet. Vor dem Start muss ein
  Anbieter angebunden werden; die Auswahl ist offen (Konzept §13).
- Die Zuteilung von Lagerbestand nach Zahlungseingang (Konzept §5.5) kommt mit Schritt 5.
  Bis dahin kennt der Verkauf keine Lieferzeit.
- Bestellen und Bezahlen haben eine eigene Drossel je Client-Adresse
  (`MB_CHECKOUT_RATE_LIMIT`, 30 Anfragen in 10 Minuten), getrennt von der Anmeldedrossel.
