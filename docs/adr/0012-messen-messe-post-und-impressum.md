# ADR 0012: Messen, Messe-Post und Impressum

Status: angenommen · 28.10.2026

## Kontext

Der Shop läuft ab jetzt als **adp-Modelle**. Der Inhaber verkauft nicht nur online,
sondern auch auf Messen und Modellbahnausstellungen; 2026 sind es vier, von Leuna bis
Kühlungsborn. Seine bisherige Website hatte dafür eine Seite „Termine“. Dazu kamen drei
Klärungen:

- **Neue Anschrift:** Glambecker Straße 2, 17235 Neustrelitz. Name, Anschrift und Kontakt
  gehören ins Impressum und in jede E-Mail, aber nicht in den Code.
- **Versand in die EU:** Deutschland 5,90 €, alle übrigen 26 EU-Länder 16,90 €,
  versandkostenfrei nie. Bis Schritt 5 lieferte der Shop nur nach Deutschland und
  Österreich, ab einem Warenwert kostenlos.
- **Der Shopname** ist „adp-Modelle“ und bleibt konfigurierbar.

Die Besucher sollen erfahren, wann und wo sie die Modelle in die Hand nehmen können: auf
der Website, im eigenen Kalender und auf Wunsch per E-Mail.

## Entscheidung

### Ein eigenes Modul `site`: der Auftritt

- **Messen, Messe-Post und Impressum** bilden einen eigenen Kontext „Auftritt“: Modul `site`,
  Schema `site`, Migration 0006. Das sind drei Tabellen:
  - `fairs`: die Messen;
  - `subscriptions`: die Anmeldungen zur Messe-Post;
  - `mailings`: wer welche Ankündigung bekommen hat.
- **Warum nicht im Katalog oder im Verkauf:** Messen ändern sich selten. Sie haben andere
  Rechte und eine andere Sprache als Produkte oder Bestellungen.
- **Der Verkauf liest nur die nächste Messe**, über einen Vertrag wie die übrigen Module:
  - `NextFair` ist rein;
  - `load_next_fair` ist die SQL-Fassade dazu.
  - Bestell- und Versandmails schließen damit: „Als Nächstes stellen wir auf der Messe … aus“.

### Messen

- **Eine Messe** hat:
  - Name, Ort, Straße, PLZ und Stadt;
  - den Stand, die Öffnungszeiten (eine Zeile je Tag), eine Website und einen Hinweis;
  - den ersten und den letzten Tag, höchstens 14 Tage auseinander.
- **Im Shop** erscheint eine Messe nur, wenn sie veröffentlicht ist.
  - Sie gilt als kommend, bis ihr letzter Tag vorbei ist, gerechnet in deutscher Zeit.
  - Von den vergangenen zeigt der Shop die letzten vier als „Rückblick“.
- **`/termine`** zeigt die Messen als Halte auf einem Streckenband:
  - Der nächste Halt ist blau, mit Countdown („In 10 Tagen“, „Heute geöffnet“).
  - Der Stand steht als Bahnsteigschild.
  - Die Startseite nennt die nächste Messe in einem eigenen Band.
- **Route:** Der Link führt zu OpenStreetMap. Das braucht keine Einwilligung und keine
  Karte im Shop; erst der Klick öffnet die fremde Seite.

### Kalender

- **iCalendar nach RFC 5545**, mit eigenem Schreiber (`application/ical.py`) statt einer
  Bibliothek. Das Format ist klein; die Regeln stehen in Tests:
  - ganztägige Termine mit ausschließendem `DTEND`;
  - Escaping von `,`, `;` und `\`;
  - Zeilen nach 75 Oktetten gefaltet;
  - die UID ist `fair-{id}@{host}`, damit ein Abo Änderungen erkennt.
- **Zwei Wege:**
  - `GET /store/fairs/{id}/calendar.ics` ist ein einzelner Termin, verlinkt aus Seite und Mail.
  - `GET /store/fairs/calendar.ics` ist der Feed aller veröffentlichten Messen, als
    `webcal://`-Abo. Für Google Kalender gibt es „Adresse kopieren“.

### Messe-Post mit Double-Opt-in

- **Anmelden** speichert die Adresse als *pending*, mit Zeitpunkt und der Fassung des
  Einwilligungstexts (`messe-post-2026-10`). Der Worker schickt dann einen Link.
  - Der Bestätigungslink ist 7 Tage gültig.
  - Gespeichert wird nur sein SHA-256-Hash.
  - Ein neuer Link ersetzt den alten.
  - Erneutes Anmelden schickt frühestens nach 10 Minuten wieder eine Mail.
- **Die Antwort ist immer dieselbe (202).** Niemand erfährt über das Formular, ob eine
  Adresse schon eingetragen ist.
- **Bestätigen** macht die Anmeldung zu *confirmed*.
- **Unbestätigte Anmeldungen** löscht ein Job im Worker nach 7 Tagen; er läuft alle
  6 Stunden.
- **Abmelden** löscht die Zeile sofort.
  - Der Abmeldetoken steht im Klartext in der Tabelle, anders als der Bestätigungstoken:
    Jede Mail trägt ihn, und er kann nur beenden.
  - Ein unbekannter Token ist kein Fehler (204).
- **Die Seiten `/termine/bestaetigen` und `/termine/abmelden`** handeln erst auf einen Klick.
  Mail-Scanner öffnen Links von selbst; sie dürfen weder bestätigen noch abmelden.
- **Bremse:** höchstens 10 Anfragen je Adresse in 10 Minuten
  (`MB_FAIR_NEWS_RATE_LIMIT`, `MB_FAIR_NEWS_RATE_WINDOW_SECONDS`), denn jede Anmeldung
  verschickt eine Mail.

### Ankündigen

- **Einmal je Messe**, nur veröffentlicht und noch nicht vorbei. Sonst antwortet die API
  409 mit `fair_not_published`, `fair_past` oder `fair_already_announced`.
- **Das Stellwerk** fragt vorher nach und nennt die Zahl der Empfänger.
  - Ohne Bestätigte bleibt „Jetzt senden“ gesperrt, damit die eine Ankündigung nicht an
    niemanden geht.
- **Der Worker** verschickt die Ankündigung in Blöcken zu 50.
  - Jede gesendete Mail hält er in `site.mailings` fest (Fremdschlüssel auf Messe und
    Anmeldung, Primärschlüssel aus beiden).
  - Bricht der Versand ab, schickt der Neuversuch nur die fehlenden.
  - Wer sich zwischendurch abmeldet, bekommt nichts mehr.
- **Im Ereignisstrom** des Stellwerks erscheint `site.fair.announced` („Messe angekündigt“).

### Impressum aus der Konfiguration

- **Die Anbieterangaben** stehen in `MB_IMPRINT_*`:
  - Pflicht: Firma, Inhaber, Straße, PLZ, Stadt und E-Mail;
  - optional: Telefon, Land und USt-IdNr. Die USt-IdNr. wird geprüft: `DE` und 9 Ziffern.
  - In Produktion startet das Backend nicht ohne die Pflichtangaben.
- **Echte Werte** gehören nur in `.env`; `.env.example` hat Platzhalter. Personenbezogene
  Daten des Inhabers stehen nirgends im Code.
- **`GET /store/imprint`** liefert die Angaben. `/impressum` zeigt sie als Schriftfeld wie
  auf einer technischen Zeichnung, mit:
  - § 5 DDG;
  - der Verantwortung nach § 18 Abs. 2 MStV;
  - der Erklärung zur Verbraucherstreitbeilegung.
  - Einen Link zur OS-Plattform der EU gibt es nicht mehr; die Plattform ist seit Juli 2025
    abgeschaltet.
- **Jede E-Mail** schließt mit Anbieter, Anschrift und Kontakt (`compose(…, sender=…)`):
  Bestätigung, Passwort, Bestellung, Versand und Messe-Post.

### Versand in die EU

- **Versandzonen:** Deutschland und die übrigen 26 EU-Länder, jede mit Postleitzahlmuster.
  - Postleitzahlen werden vor der Prüfung vereinheitlicht: Großbuchstaben, einfache
    Leerzeichen.
  - `free_from_cents` ist `null`: Es gibt keine Versandkostenfreiheit.
- **Das Frontend** hält dieselbe Liste (`src/lib/sales/countries.ts`) und fasst gleiche
  Bedingungen zusammen („Übrige EU-Länder“).

### Rechte

- **Messen pflegen und ankündigen:** Inhaber und Mitarbeiter. Packer bekommen 403.

## Folgen

- **Texte für adp-Modelle:**
  - Neue Seiten „Über uns“ und „Sonderanfertigung“, aus der bisherigen Website und in
    der Du-Form.
  - Die Startseite spricht von Handarbeit statt von 3D-Druck. 3D-Druck und Lasercutting
    bietet adp-Modelle als Sonderanfertigung an.
  - Das Bild der Startseite ist ein Autodrehkran als Blaupause.
- **E-Mail-Versand:** Eine Ankündigung geht über denselben SMTP-Relay wie alle Mails. Bei
  einigen hundert Empfängern genügt das. Bei Tausenden bräuchte es einen Versanddienst
  mit eigener Abmeldeverwaltung.
- **Nachweis der Einwilligung:** Gespeichert werden Fassung des Einwilligungstexts,
  Zeitpunkt der Anmeldung und Zeitpunkt der Bestätigung, keine IP-Adresse. Der Inhalt der
  Fassung `messe-post-2026-10` steht im Frontend (`fair-news-form.tsx`). Ändert sich seine
  Bedeutung, braucht es eine neue Fassung im Backend.
- **Noch offen:** die USt-IdNr. Sobald der Inhaber sie nennt, genügt `MB_IMPRINT_VAT_ID`
  in `.env`.
- **Smoke-Test:** Er prüft jetzt auch:
  - eine Messe auf `/termine` und als `.ics`;
  - die Anmeldung mit Link aus Mailpit;
  - eine Ankündigung, eine zweite wird abgelehnt;
  - Abmelden mit dem Link aus der Mail;
  - Impressum und die 27 Lieferländer.
