# ADR 0015: Löschmeldungen von eBay (Marketplace Account Deletion)

Status: angenommen · 29.10.2026

## Kontext

eBay verlangt von jeder App, die eBay-Daten speichert, einen Empfang für seine
**Löschmeldungen**: Schließt jemand sein eBay-Konto, schickt eBay jeder App eine Meldung,
und die App löscht, was sie über diese Person hat. Ohne diesen Empfang (oder eine Befreiung
für Apps ohne gespeicherte Daten) **gibt eBay die Produktions-Schlüssel nicht frei**.

Der Shop speichert eBay-Daten: Jede eBay-Bestellung (ADR 0014) bringt Benutzername, E-Mail,
Name und Anschrift des Käufers mit. Eine Befreiung kommt also nicht in Frage.

eBays Vorgaben, nach dem offiziellen SDK (`eBay/event-notification-nodejs-sdk`):

- **Prüfung der Adresse.** Beim Eintragen schickt eBay `GET …?challenge_code=…`. Die
  Antwort ist `{"challengeResponse": "<hex>"}`, der SHA-256 aus Challenge-Code,
  Prüftoken und Adresse, in dieser Reihenfolge. Das Prüftoken ist 32 bis 80 Zeichen lang
  (Buchstaben, Ziffern, `_`, `-`) und steht mit der Adresse im Entwicklerkonto.
- **Meldung.** `POST` mit JSON: `metadata.topic = MARKETPLACE_ACCOUNT_DELETION` und
  `notification.data` mit `username`, `userId` und `eiasToken`. Quittiert wird mit 2xx;
  sonst versucht eBay es wieder.
- **Signatur.** Der Kopf `X-EBAY-SIGNATURE` ist Base64 eines JSON-Objekts mit `alg`
  (ECDSA), `kid`, `signature` und `digest` (SHA1). Den öffentlichen Schlüssel liefert eBays
  Notification API (`/commerce/notification/v1/public_key/{kid}`) gegen ein Token der App
  selbst (Client Credentials).

Zwei Umstände prägen die Entscheidung:

- **Die Meldungen betreffen fast nie Kunden des Shops.** eBay meldet jede Kontoschließung
  an jede App. Es kommen Meldungen über tausende Fremde.
- **Henne und Ei.** Die Adresse muss eBays Prüfung bestehen, *bevor* die
  Produktions-Schlüssel gelten. Der Live-Shop läuft dann noch mit `MB_EBAY_MODE=off`, denn
  Produktion erlaubt nur `off` oder `production`, und für `production` fehlen die Schlüssel.

## Entscheidung

### Ein Empfang unter `/api/v1/webhooks/ebay/account-deletion`

- **Webhooks bekommen einen eigenen Pfad.** `csrf_guard` lässt `/api/v1/webhooks/`
  ohne den Kopf `X-Modellbahn-Client` durch. Ein gefälschter Aufruf richtet nur mit dem
  Cookie des Opfers Schaden an, und Webhooks lesen keine Sitzung; ihr Nachweis ist die
  Signatur des Absenders. Alle anderen Pfade bleiben geschützt.
- **Er antwortet in jeder Betriebsart.** Die Prüfung braucht nur
  `MB_EBAY_VERIFICATION_TOKEN` und die Adresse (`MB_PUBLIC_BASE_URL` und der feste Pfad).
  Ohne Token antwortet sie mit 404 `deletion_endpoint_not_ready`.
- **Produktion verlangt das Token.** `MB_EBAY_MODE=production` startet nicht ohne
  `MB_EBAY_VERIFICATION_TOKEN`. Das Entwicklungs-Token aus `.env.example` ist in Produktion
  verboten.

### Die Meldung

1. **Lesen.** Kein JSON oder ohne Benutzername ergibt 400 `notification_invalid`.
2. **Signatur prüfen.**
   - Der Schlüssel kommt von eBay und wird je `kid` behalten, höchstens 16 Stück.
   - Unbekannte `kid` werden nicht behalten, damit erfundene Kennungen den Speicher
     nicht füllen.
   - Geprüft wird der Inhalt wie empfangen und, falls nötig, wie eBays SDK ihn neu
     schreibt (kompaktes JSON).
   - Ungültig ergibt 412 `signature_invalid`. Ist eBay nicht erreichbar oder lehnt es das
     App-Token ab, kommt 503, und eBay versucht es wieder.
3. **Andere Themen** werden quittiert (204) und nicht weiter beachtet.
4. **Löschen.** Gesucht werden die eBay-Bestellungen mit diesem Benutzernamen, ohne
   Groß- und Kleinschreibung (Index `marketplace_orders_buyer_idx`).
   - Bei Treffern gehen Benutzername, E-Mail, Empfänger, Straße, PLZ und Ort;
     `buyer_erased_at` hält den Zeitpunkt fest. Betrag, Positionen und eBay-Nummer bleiben.
   - Eine zweite Meldung findet nichts mehr.
5. **Nichts über Fremde.** Ohne Treffer wird nichts gespeichert und nichts
   protokolliert. Auch bei Treffern steht im Protokoll nur die Kennung der Meldung und die
   Zahl der Bestellungen, nie der Benutzername.

### Die Shop-Bestellung bleibt

Die Shop-Bestellung, die aus einer eBay-Bestellung wurde, behält Name und Anschrift: Sie
ist der Beleg für die gesetzlichen Aufbewahrungsfristen. Das ist dieselbe Regel wie beim
Löschen eines Kundenkontos (KONZEPT §5.6); anonymisiert wird nach Ablauf der Fristen.

### Solange eBay aus ist

Ohne Gateway gibt es keinen Schlüssel und keine Signaturprüfung.

- **Keine eBay-Bestellung trägt noch Käuferdaten:** Die Meldung wird quittiert (204).
  Das stimmt, denn es gibt nichts zu löschen. So ist es im Live-Shop, solange die Schlüssel
  ausstehen.
- **Es liegen noch Käuferdaten vor** (eBay wurde nach echtem Betrieb abgeschaltet): Die
  Antwort ist 503 `ebay_off_with_buyer_data`. eBay versucht es wieder, und mit
  eingeschaltetem eBay wird die Meldung geprüft und erledigt. Ungeprüft gelöscht wird nie.

### Testmarktplatz

- **Signiert wie eBay.** Der eingebaute Testmarktplatz signiert Meldungen wie eBay, mit
  einem P-256-Schlüssel aus einem festen Startwert (`kid` `test-marketplace-1`). Er steht
  bewusst im Code, damit Tests signieren können. Testbetrieb ist in Produktion verboten.
- **Testknopf im Stellwerk.** „Konto des Testkäufers schließen“ schickt eine solche Meldung
  durch dieselbe Prüfung.
- **Geprüft gegen eBays eigene Testvektoren:** Die Signaturprüfung besteht die Fälle aus
  eBays SDK (gültig, verändert, fremd).

### Im Stellwerk

Das Panel „Löschmeldungen von eBay“ zeigt:

- die Adresse fürs Entwicklerkonto, zum Kopieren;
- ob das Prüftoken gesetzt ist;
- ob Signaturen geprüft werden.

Es erscheint auch bei ausgeschaltetem eBay, denn genau dann wird es gebraucht. Eine
gelöschte eBay-Bestellung zeigt „Käuferdaten gelöscht am …“.

## Folgen

- **Reihenfolge beim Freischalten:**
  1. Ein eigenes Token erzeugen und als `MB_EBAY_VERIFICATION_TOKEN` setzen; eBay darf
     dabei noch `off` sein.
  2. Im Entwicklerkonto unter „Alerts & Notifications“ die Adresse aus dem Stellwerk und
     dasselbe Token eintragen. eBay prüft die Adresse sofort.
  3. Die Produktions-Schlüssel eintragen und auf `production` stellen.
- **Das Token ist ein Geheimnis zweiter Klasse.** Es beweist nur, dass die Adresse zur App
  gehört. Es gehört trotzdem nur in die Server-Umgebung und ins Entwicklerkonto, nicht
  in E-Mails oder auf Laufzettel.
- **Benutzernamen können sich ändern.** Hat jemand seinen eBay-Namen nach dem Kauf
  geändert, findet die Meldung seine Bestellung nicht; eBays Bestellungen nennen keine
  `userId`. Die allgemeine Löschfrist der Shop-Bestellungen deckt diesen Fall ab.
- **Last.** Jede Meldung kostet eine Index-Abfrage und eine Signaturprüfung mit
  behaltenem Schlüssel. Caddy begrenzt den Inhalt auf 1 MB, der Empfang selbst auf 64 KB.
