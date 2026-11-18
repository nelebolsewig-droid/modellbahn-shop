# ADR 0032: Kaufen ohne Umwege

Status: angenommen · 18.11.2026

## Kontext

Ein Durchgang durch den Shop am 18.11.2026 (zwei Gastkäufe, Laptop und Handy) zeigte:

- **Am Handy** lag „In den Warenkorb“ etwa 1.450 px tief, knapp zwei Bildschirme unter
  dem Foto.
- **Nach dem Hinzufügen** erschien nur eine kleine Zeile unter dem Knopf; der Weg zur
  Kasse führte über die Warenkorb-Seite.
- **Die Bestellseite** sagte nach der Zahlung „wir schreiben dir, sobald das Paket
  unterwegs ist“, obwohl die Kasse 2–4 Wochen Fertigung genannt hatte; die Zeitleiste
  sprang von *Bezahlt* zu *Versendet*.
- **Wiederkehrende Besucher** beginnen jedes Mal bei „Welcher Maßstab?“.
- **Gastkunden** müssen für ein Konto Name und Adresse ein zweites Mal eintippen.

## Entscheidung

- **Kaufbalken am Handy:** Solange der Kaufknopf außer Sicht ist, steht unten ein Balken
  mit Preis, Lieferbarkeit und „In den Warenkorb“ (ein Stück der gewählten Ausführung).
  Er beobachtet den echten Knopf (IntersectionObserver) und fehlt ab `lg`.
- **Mini-Warenkorb:** Nach jedem Hinzufügen öffnet ein Fenster mit dem Modell, der
  Zwischensumme und „Zur Kasse“ (bekommt den Fokus), dazu „Warenkorb“ und „Weiter
  stöbern“. Nicht modal: Die Seite bleibt bedienbar, Escape oder ein Klick daneben
  schließt es, ein Seitenwechsel auch. Am Handy ein Blatt von unten.
- **Maßstab merken:** Die Seite eines Maßstabs merkt ihn im Browser (`localStorage`,
  kein Cookie, nichts geht an den Server). „Katalog“ im Kopf und „Zum Katalog“ auf der
  Startseite führen dann direkt dorthin; die Brotkrumen „Katalog“ bleiben bei der Wahl
  der Maßstäbe.
- **Postleitzahl füllt den Ort:** Für Deutschland schlägt die Kasse (und das Adressbuch)
  den Ort vor. Gibt es genau einen, wird er eingetragen, solange der Kunde keinen eigenen
  getippt hat; mehrere stehen als Vorschlagsliste am Feld. Die Daten liegen statisch unter
  `frontend/public/plz/` (je zwei Ziffern eine Datei, zusammen 0,7 MB, geladen wird eine
  von wenigen KB), erzeugt mit `scripts/plz_orte.py` aus GeoNames (CC BY 4.0, genannt im
  Impressum unter „Datenquellen“). Ortsteile („Dresden Innere Altstadt“) fallen weg, wenn
  der Ort selbst unter derselben Postleitzahl steht.
- **Fertigung auf der Bestellseite:** Hat die Kasse eine Lieferzeit genannt
  (`orders.lead_time_*`, ADR 0029), steht zwischen *Bezahlt* und *Versendet* die Station
  *Wird gefertigt* mit „bis ca. …“ (Zahlung plus längste Lieferzeit), sie pulsiert, solange
  gearbeitet wird. Der Text nennt Lieferzeit und Datum.
- **Konto in einem Schritt:** Auf der Bestellseite fragt ein Gast nur noch nach einem
  Passwort; Name und Adresse kommen aus der Bestellung. Danach läuft alles wie bei jeder
  Registrierung (Bestätigungsmail, die Bestellung wandert ins Konto, ADR 0005).

## Folgen

- Kein neuer Endpunkt, keine Migration; alles im Frontend.
- Die Postleitzahlen veralten langsam. Neu erzeugen: CSV von GeoNames holen und
  `python3 scripts/plz_orte.py zipcodes.de.csv frontend/public/plz` laufen lassen.
- Der Werkstatt-Ticker (welcher Drucker gerade am Modell druckt) baut auf der Station
  *Wird gefertigt* auf.
