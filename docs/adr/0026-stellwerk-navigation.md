# ADR 0026: Navigation im Stellwerk

Status: angenommen · 12.11.2026

## Kontext

Das Stellwerk wuchs Schritt für Schritt, und jeder Schritt hängte seinen Menüpunkt hinten
an. Am Ende standen elf gleichrangige Punkte in der Reihenfolge, in der sie gebaut wurden:
Übersicht, Bestellungen, Lager, Fertigung, Scanner, Erfassen, Katalog, Kategorien,
Maßstäbe, Messen, eBay.

- **Für jede Rolle gleich:** Packer sahen alle elf Punkte. Bei sechs davon kam nur „Deine
  Rolle erlaubt das nicht“, und im Lager standen Knöpfe, die mit derselben Meldung
  scheiterten.
- **Auf dem Handy** passten vier Punkte in einen Streifen, den man seitlich wischen musste.
  Ausgerechnet der Scanner, das Werkzeug des Packers am Regal, lag außer Sicht.
- **Tägliches neben Seltenem:** Kategorien, Maßstäbe und die Einrichtung von eBay braucht
  man einmal, Bestellungen und Lager jeden Tag.
- **Mehrere Wörter für dasselbe:** Produkt, Artikel und Modell; Variante und Ausführung;
  Einheit und Stück; Lagerplatz und Platz.

## Entscheidung

### Jede Rolle sieht nur, was sie benutzen kann

- Packer: Übersicht, Bestellungen, Lager, Fertigung und Scannen.
- Inhaber und Mitarbeiter: Übersicht, Bestellungen, Lager, Fertigung, Katalog, Messen,
  eBay, Einstellungen und Scannen.
- Knöpfe, die eine Rolle nicht benutzen darf, fehlen ebenso, etwa „Stücke erfassen“ und
  „+ Stück“ im Lager für Packer.
- Die Prüfung im Backend bleibt, wie sie ist. Die Oberfläche verbirgt nur Sackgassen.

### Einstellungen

- Neue Seite `/admin/einstellungen` mit je einer Karte für Kategorien, Maßstäbe und die
  eBay-Einrichtung. Nur für Inhaber und Mitarbeiter.
- Kategorien und Maßstäbe behalten ihre Adressen unter `/admin/katalog/…`. Auf ihnen ist
  „Einstellungen“ markiert.
- **eBay geteilt:** `/admin/ebay` zeigt die tägliche Arbeit (Angebote, eBay-Bestellungen,
  was eBay abgelehnt hat). Verbindung, Versand und Zahlung, eBay-Kategorien und
  Löschmeldungen stehen unter `/admin/einstellungen/ebay`.
  - eBays Rücksprung nach der Anmeldung führt weiter auf `/admin/ebay?ebay=…`. Die Seite
    leitet ihn an die Einrichtung weiter; das Backend bleibt unverändert.

### Scannen ist ein Knopf

- **Am Schreibtisch:** ein schwarzer Knopf „Scannen“ rechts im Kopf, neben Passwort und
  Abmelden.
- **Auf dem Handy:** eine feste Leiste am unteren Rand: Übersicht · Bestellungen ·
  Scannen (in der Mitte, hervorgehoben) · Lager · Mehr. „Mehr“ öffnet ein Blatt von unten
  mit dem Rest: Fertigung, Katalog, Neues Modell, Messen, eBay, Einstellungen. Bleibt für
  eine Rolle nur ein Punkt übrig (Packer: Fertigung), steht er selbst an der Stelle von
  „Mehr“.
- Die Leiste hält die sicheren Ränder des Geräts frei (`viewport-fit=cover` im Stellwerk);
  Seiten und mitlaufende Aktionsleisten enden über ihr.
- „Erfassen“ verlässt das Menü. Die Schnellerfassung heißt „Neues Modell“: ein Knopf im
  Kopf des Katalogs und ein Eintrag unter „Mehr“, unter derselben Adresse wie bisher.

### Ein Wortschatz

Im Stellwerk gelten Modell (nicht Produkt oder Artikel), Ausführung (nicht Variante),
Stück (nicht Einheit), Platz (nicht Lagerplatz) und Teil für ein gedrucktes Teil. Das gilt
für die Oberfläche und die Fehlermeldungen des Stellwerks; Bezeichner, API und der Shop
bleiben, wie sie sind.

- „In Fertigung“ im Lager heißt „Wartet auf Fertigung“: Gezählt werden bestellte Stücke,
  die es noch nicht gibt, nicht laufende Drucke.
- Leere Werte stehen als Wort da („neu“, „keine Angabe“, „kein“), nie als Strich, der
  sich als Minus lesen lässt.

### Kleinere Wege

- Die Bestellliste öffnet mit „Zu versenden“, den bezahlten Bestellungen, die gepackt
  werden.
- Auf dem Handy steht beim Bestellpult „Kommissionieren“ über Verlauf und Modellen.
- „Neues Modell“ legt ohne Nachfrage kein Stück mit Etikett an. Die Anzahl beginnt bei 0
  und fragt: „Wie viele Stücke liegen fertig da?“
- Die Liste für die Kasse (CSV für SumUp) gibt es nur noch im Katalog, nicht mehr im
  Lager.

## Folgen

- Packer begegnen keinem Menüpunkt und keinem Knopf mehr, der mit „Deine Rolle erlaubt das
  nicht“ endet. Rufen sie eine Adresse direkt auf, antwortet das Backend wie bisher.
- Auf dem Handy liegt Scannen immer einen Daumen weit entfernt; der Kopf ist eine Zeile
  niedrig, die Kamera beginnt weit oben.
- Wer Kategorien, Maßstäbe oder die eBay-Einrichtung sucht, findet sie unter
  „Einstellungen“. Alte Lesezeichen funktionieren weiter.
- Welche Rolle was sieht, steht an einer Stelle (`src/components/admin/sections.ts`); ein
  neuer Bereich wird dort mit seinen Rollen eingetragen.
- Die Betriebsanleitung nennt die neuen Namen (BETRIEB, „Etiketten der Modelle“).
