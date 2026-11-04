# ADR 0019: Zahlung mit SumUp Online

Status: angenommen · 04.11.2026

## Kontext

Bis hierher bezahlte der Shop mit einer sichtbaren Testzahlung (ADR 0009): Der Kunde wählte,
wie sie ausgeht, abgebucht wurde nichts. Vor dem Umzug von `www.adp-modelle.de` braucht der
Shop einen echten Zahlungsdienst. Entschieden ist **SumUp Online**, weil adp-Modelle auf
Messen schon mit SumUp kassiert (ADR 0011): ein Konto, eine Abrechnung.

Die Testzahlung antwortete sofort. Bei SumUp bezahlt der Kunde dagegen auf SumUps Seite
(Hosted Checkout), und die Antwort kommt später, auf drei Wegen, von denen keiner sicher ist:

- Der Kunde kommt zum Shop zurück, oder auch nicht (Tab geschlossen, Akku leer).
- SumUp meldet sich beim Shop. Die Meldung trägt keine Signatur; jeder könnte sie schicken.
- Niemand meldet sich, und die Seite läuft ab.

## Entscheidung

### Die Schutzschicht bleibt, ihr Vertrag wächst

- **`PaymentGateway`** (Port der Anwendung) kennt jetzt:
  - `begin`: eine Zahlung beginnen. Die Antwort ist entweder sofort da (Testzahlung) oder
    eine Seite des Anbieters (SumUp).
  - `outcome`: den Anbieter fragen, wie eine Zahlung auf seiner Seite steht.
  - `abandon`: die Seite schließen, damit dort nichts mehr bezahlt werden kann.
  - `refund`: erstatten.
- **Drei Adapter**, gewählt mit `MB_PAYMENT_PROVIDER`:
  - `mock`: die Testzahlung wie bisher, nur in der Entwicklung.
  - `sumup`: SumUp Online mit `MB_SUMUP_API_KEY` (`sup_sk_…`) und `MB_SUMUP_MERCHANT_CODE`.
  - `off`: kein Anbieter. Der Shop nimmt dann keine Bestellungen an (409 `checkout_closed`),
    statt Bestellungen zu sammeln, die niemand bezahlen kann.
  - Der echte Betrieb startet nicht mit `mock`: Bestellungen gälten sonst ohne Geld als
    bezahlt.
- **SumUps Modell bleibt im Adapter** (Konzept §2.6). Die Domäne kennt nur
  *offen*, *eingegangen* und *gescheitert*:
  - SumUp `PAID` → eingegangen, mit der Transaktion, die eine Erstattung braucht.
  - SumUp `EXPIRED` → gescheitert (`expired`).
  - Alles andere bleibt offen, auch SumUp `FAILED`: Ein abgelehnter Versuch lässt sich auf
    derselben Seite wiederholen.

### Eine Zahlung kann offen sein

- **Neuer Zustand `pending`** einer Zahlung, solange der Kunde auf SumUps Seite ist.
  - Sie trägt die Adresse der Seite (`checkout_url`), genau solange sie offen ist; das prüft
    die Datenbank.
  - Höchstens eine offene Zahlung je Bestellung (eindeutiger Teilindex). Wer erneut auf
    „Bezahlen“ drückt, bekommt dieselbe Seite.
  - Die Kennung der Zahlung geht als `checkout_reference` an SumUp. SumUp lehnt eine zweite
    Seite mit derselben Kennung ab, ein Doppelklick kann also keine zweite anlegen.
- **Die Seite läuft ab, wenn die Bestellung abläuft:** `valid_until` ist die Zahlungsfrist
  der Bestellung (24 Stunden nach dem Bestellen).
- **Eine abgelaufene Seite macht Platz für eine neue.** Bevor eine neue Zahlung beginnt,
  fragt der Shop SumUp nach der offenen. Ist dort inzwischen bezahlt, ist die Bestellung
  bezahlt, und es gibt nichts mehr zu bezahlen.

### Der Shop glaubt nur, was er selbst fragt

Jeder der drei Wege führt zur selben Frage an SumUp (`GET /v0.1/checkouts/{id}`) und bucht
deren Antwort:

- **Rückkehr:** SumUp schickt den Kunden zur Bezahlseite des Shops zurück
  (`redirect_url`). Die Seite fragt über `POST /store/orders/{token}/payments/sync`, und noch
  zweimal im Abstand von drei Sekunden, falls SumUp einen Moment braucht.
- **Meldung:** SumUp schickt die Kennung der Seite an `POST /api/v1/webhooks/sumup`
  (`return_url`, vom Shop bei jeder Zahlung selbst genannt).
  - Die Meldung sagt nur, *wen* der Shop fragen soll. Unbekannte Kennungen und Unsinn
    werden still verworfen.
  - Die Antwort ist immer 204, damit sie niemandem verrät, ob eine Kennung existiert.
  - Wie Kasse und Bezahlen ist der Weg im Tempo begrenzt.
- **Abgleich im Worker:** `sales.reconcile_payments` fragt alle zwei Minuten nach offenen
  Zahlungen, die älter als eine Minute sind.

Die Buchung sperrt die Bestellung. Kommen Rückkehr und Meldung gleichzeitig, bucht der
zweite Weg nichts mehr: Die Zahlung ist dann nicht mehr offen.

### Geben und Zurückgeben

- **Stornieren schließt zuerst die Seite** (`DELETE /v0.1/checkouts/{id}`):
  - Gelingt das, kann dort niemand mehr bezahlen; die Zahlung scheitert mit `cancelled`.
  - Lehnt SumUp ab, wurde die Seite gerade benutzt. Der Shop fragt dann nach. Ist Geld
    eingegangen, ist die Bestellung bezahlt, und das Stornieren erstattet es.
  - Antwortet SumUp gar nicht, wird nicht storniert (503). Beim Ablauf nach 24 Stunden
    versucht es der Worker in der nächsten Runde wieder.
  - Wurde in letzter Minute bezahlt, bleibt die Bestellung bestehen, statt abzulaufen.
- **Geld auf einer stornierten Bestellung geht von selbst zurück:**
  - Fall: Die Seite ließ sich nicht schließen, und jemand bezahlt danach.
  - Die Bestellung bleibt storniert; es gibt kein `sales.order.paid`.
  - Die Zahlung wird erstattet und so gebucht. Das Log zeigt
    `sales.payment.refunded_after_cancel`.
  - Scheitert die Erstattung, bleibt die Zahlung eingegangen, und die nächste Runde versucht
    es wieder.
- **Erstattungen nennen SumUps Transaktion**
  (`POST /v1.0/merchants/{code}/payments/{transaction}/refunds`, ohne Betrag, also voll).

### Im Shop

- Die Bezahlseite fragt `GET /store/payment-provider` und zeigt danach:
  - mit SumUp: Betrag und „Sicher bezahlen mit SumUp“, dann die Weiterleitung;
  - nach der Rückkehr: den Stand, den die Seite selbst erfragt hat, mit „Weiter zu SumUp“ und
    „Erneut prüfen“, solange die Zahlung offen ist;
  - mit `mock`: die Testzahlung wie bisher;
  - mit `off`: einen Hinweis.
- `OrderOut.payment_url` ist die offene Seite. Die Bestellung zeigt eine offene Zahlung als
  „Offen bei SumUp“.

## Folgen

- **Kartendaten berührt der Shop nie.** Sie gehen nur an SumUp; der Shop sieht Bestellnummer,
  Betrag und Ausgang. Die Datenschutzseite sagt das.
- **Teilerstattungen** gibt es nicht: Storniert wird immer die ganze Bestellung. Kommen
  Teilstornos, bekommt `refund` einen Betrag (SumUp nimmt ihn an).
- **SumUps Meldungen sind unsigniert**, also ohne Wert als Beweis. Der Shop braucht sie
  nicht: Fehlen sie, findet der Worker die Zahlung eine Minute später.
- **Der Shop braucht von SumUp nur zwei Werte** (Schlüssel, Händlercode), die das
  Einrichtungsskript verdeckt abfragt. Im SumUp-Konto ist keine Adresse einzutragen.
- **Ohne Netz zu SumUp** bleibt eine Zahlung offen und wird nachgeholt. Neue Zahlungen
  scheitern mit 503 `payment_unavailable`, ohne etwas zu buchen.
- **Die Testzahlung bleibt** für Entwicklung, Tests und den Smoke-Test, als gleichwertiger
  Adapter.
