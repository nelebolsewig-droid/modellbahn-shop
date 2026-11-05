# ADR 0020: Rechtstexte und Widerrufsfunktion

Status: angenommen · 04.11.2026

## Kontext

Vor der ersten echten Zahlung (ADR 0019) brauchte der Shop seine Rechtstexte. AGB,
Widerrufsbelehrung und Datenschutzerklärung waren bisher Platzhalter. Zwei Änderungen
des Rechts kamen 2026 hinzu:

- **Widerrufsbutton:** Seit dem 19. Juni 2026 muss ein Online-Shop eine elektronische
  Widerrufsfunktion bereitstellen (§ 356a BGB, Umsetzung der Richtlinie (EU) 2023/2673,
  BGBl. 2026 I Nr. 28).
  - Die Funktion heißt „Vertrag widerrufen“ und ist während der Widerrufsfrist ständig
    verfügbar und hervorgehoben.
  - Sie fragt nach Name, Vertrag und dem Weg für die Bestätigung.
  - Ein zweiter Schritt „Widerruf bestätigen“ beugt Versehen vor.
  - Danach geht unverzüglich eine Eingangsbestätigung auf einem dauerhaften Datenträger
    hinaus, mit dem Inhalt des Widerrufs sowie Datum und Uhrzeit des Eingangs.
  - Die Muster-Widerrufsbelehrung (Gestaltungshinweis 3) weist seitdem auf die Funktion
    hin.
- **Gewährleistungshinweis:** Seit dem 27. September 2026 muss ein Shop mit dem
  harmonisierten EU-Hinweis auf die gesetzliche Gewährleistung aufmerksam machen
  (Richtlinie (EU) 2024/825). Der Hinweis ist eine amtliche, nicht veränderbare Grafik.

## Entscheidung

### Texte aus der Konfiguration

- **Daten aus der Konfiguration:** AGB, Widerrufsbelehrung und Datenschutzerklärung lesen
  Anbieter und Anschrift aus `MB_IMPRINT_*`, wie das Impressum (ADR 0012). Nichts davon
  steht im Code.
- **Öffentliche Adresse:** `GET /store/imprint` nennt dazu `site_url` (`MB_PUBLIC_BASE_URL`).
  Die Belehrung braucht die Internetadresse der Widerrufsfunktion.
- **Die Widerrufsbelehrung folgt dem gesetzlichen Muster** (Anlage 1 zu Art. 246a § 1
  Abs. 2 Satz 2 EGBGB, Stand 19.06.2026) und bleibt beim „Sie“ des Musters. Sonst
  duzt der Shop.
  - Variante: Waren in einer Lieferung; die Rücksendekosten trägt der Kunde (entschieden am
    04.11.2026).
  - Das Muster-Widerrufsformular steht darunter.
  - Ein Absatz außerhalb des Musters nennt den Ausschluss für Sonderanfertigungen
    (§ 312g Abs. 2 Nr. 1 BGB). Katalogmodelle, die erst nach der Bestellung entstehen, sind
    keine Sonderanfertigung.
  - Den Wortlaut des neuen Absatzes zur Widerrufsfunktion gab es nur aus Fachquellen; das
    Bundesgesetzblatt war aus der Entwicklungsumgebung nicht erreichbar.
- **Die AGB beschreiben den Ablauf, wie er programmiert ist:**
  - „Zahlungspflichtig bestellen“ ist das verbindliche Angebot.
  - Die Eingangsbestätigung ist noch keine Annahme.
  - Der Vertrag kommt mit der Bestätigung des Zahlungseingangs zustande.
  - Die Bindung dauert 24 Stunden; Geld, das danach kommt, geht zurück (ADR 0019).
  - Die Versandkosten nennen die AGB nicht selbst, sondern verweisen auf die Seite
    „Versand und Lieferung“. Es gibt sie damit nur an einer Stelle.
- **Die Datenschutzerklärung nennt nur Fristen, die der Shop umsetzt:**
  - Warenkorb 30 Tage, Kundensitzung 30 Tage, Stellwerk 12 Stunden;
  - Zähler gegen Missbrauch 10 Minuten, Sicherungen 14 Tage;
  - Protokolle höchstens 50 MB je Dienst.
  - Ändert sich eine davon im Code, ändert sich der Text mit; der Kopf der Seite nennt die
    Quellen.
- **Am Beginn des Bestellvorgangs** nennt der Warenkorb Liefergebiet und Zahlungsarten
  (§ 312j Abs. 1 BGB), je nach eingestelltem Anbieter.

### Die Widerrufsfunktion

- **`/widerruf/erklaeren`:**
  - Felder: Name, Bestellnummer, E-Mail-Adresse für die Bestätigung, auf Wunsch die
    Artikel, die widerrufen werden; leer heißt die ganze Bestellung.
  - Der Knopf heißt „Widerruf bestätigen“.
  - Kein Login: Gäste haben keins, und die Funktion soll leicht zugänglich sein.
- **Wo „Vertrag widerrufen“ steht:**
  - hervorgehoben im Fuß jeder Shop-Seite;
  - auf der Seite der Widerrufsbelehrung;
  - an jeder bezahlten oder versendeten Bestellung, mit vorausgefüllter Nummer.
- **`POST /store/withdrawals` nimmt jede Erklärung an**, so wie ein Brief angenommen würde.
  - Ob der Widerruf gilt (rechtzeitig, Verbraucher, eine Bestellung des Shops), beurteilen
    Mitarbeiter.
  - Die Antwort ist immer dieselbe. Sie verrät nicht, ob es eine Bestellung mit der Nummer
    gibt.
  - Im Tempo begrenzt wie Kasse und Bezahlen.
- **`sales.withdrawals` (Migration 0013)** hält jede Erklärung mit ihrem Eingang fest.
  - Die Bestellung wird nur zugeordnet, wenn Nummer und E-Mail-Adresse zu ihr passen.
  - Nichts wird geändert oder gelöscht; der Widerruf ist ein Beleg wie die Bestellung.
- **Ereignis `sales.withdrawal.received`.** Der Worker schickt daraufhin:
  - die Eingangsbestätigung an die angegebene Adresse. Sie wiederholt nur, was eingegeben
    wurde, samt Eingangszeit, und sagt, wie es weitergeht (Rücksendung binnen 14 Tagen auf
    eigene Kosten, Erstattung binnen 14 Tagen);
  - eine Meldung an `MB_IMPRINT_EMAIL`, mit dem Link ins Stellwerk.
  - Die Nutzdaten des Ereignisses nennen keine Person.
- **Im Stellwerk:**
  - Die Widerrufe stehen live über der Bestellliste, jeder mit seinem Stand. Einer ohne
    passende Bestellung ist markiert, etwa ein eBay-Kauf.
  - Am Bestellpult steht ein Hinweis mit dem nächsten Schritt.

### Was danach geschieht: so wenig Handarbeit wie möglich

- **Vor dem Versand storniert der Shop von selbst.** Ein Widerruf der ganzen Bestellung, der
  zu ihr passt, löst im Worker das Storno aus (Stornogrund `withdrawn`, Migration 0014).
  - Eine offene SumUp-Seite wird geschlossen; eine eingegangene Zahlung geht zurück.
  - Der Kunde bekommt die Stornomail: „widerrufen, bevor wir sie verschickt haben“.
  - Ein Widerruf nur einzelner Artikel und eBay-Bestellungen bleiben für Mitarbeiter.
- **Nach dem Versand ein Klick.** Das Bestellpult hat ein Feld „Erstattung“: alles Offene
  oder die Artikel, die zurückgekommen sind.
  - „Rücksendung erhalten – erstatten“ fragt einmal nach und lässt SumUp sofort zurückzahlen.
  - `POST /admin/orders/{id}/refunds` erstattet höchstens, was von der Zahlung noch offen
    ist (`payments.refunded_cents`); mehr ergibt 409 `refund_not_possible`.
  - Teilerstattungen gehen mehrmals, die letzte macht die Zahlung „erstattet“.
  - Der Kunde bekommt eine Mail (`sales.order.refunded`).
  - SumUp bekommt immer den Betrag (`{"amount": …}`), auch bei der ganzen Summe.
- **Erinnerung statt Wiedervorlage.** Der Worker sieht täglich nach (`sales.remind_refunds`).
  - Steht eine Erstattung nach einem Widerruf noch aus und ist sie in vier Tagen fällig
    oder überfällig, geht eine Mail an `MB_IMPRINT_EMAIL`.
  - Die Frist: 14 Tage nach Eingang des Widerrufs.
  - Die Mail kommt täglich, bis erstattet ist.
- **Der Stand eines Widerrufs wird nicht gespeichert, sondern aus der Bestellung abgeleitet:**
  - keine passende Bestellung;
  - storniert;
  - wartet auf Rücksendung;
  - erstattet;
  - prüfen.

### Der EU-Gewährleistungshinweis

- Der amtliche Hinweis (Durchführungsverordnung (EU) 2025/1960, deutsche Fassung) liegt als
  Bild unter `frontend/public/rechtliches/eu-gewaehrleistung.jpg`. Er stammt aus der vom
  Inhaber gelieferten Datei und ist unverändert.
- Er erscheint vor Vertragsschluss gut sichtbar:
  - im Warenkorb und in der Kasse über „Zahlungspflichtig bestellen“, verkleinert und zum
    Vergrößern;
  - auf der Seite „Versand und Lieferung“ in voller Größe.
- Ein ausführlicher Alternativtext gibt seinen Inhalt für Screenreader wieder.

## Folgen

- **Eine anwaltliche Prüfung** der drei Texte vor dem ersten echten Verkauf bleibt
  empfohlen. Die Texte folgen den gesetzlichen Mustern und den Pflichten nach BGB, EGBGB,
  DSGVO und TDDDG, sind aber keine Rechtsberatung.
- **Zurückgekommene Ware** bucht das Lager noch nicht von selbst wieder ein; das bleibt
  „Einheiten erfassen“, bis es eine Rücknahme per Scan gibt.
- **Ändert die EU den Hinweis**, wird nur die Bilddatei getauscht.
- **Mit Strato** ist ein Vertrag zur Auftragsverarbeitung abzuschließen, im
  Strato-Kundenlogin. Die Datenschutzerklärung setzt ihn voraus.
- **Heruntergeladene Sicherungen** gehören nach 14 Tagen gelöscht, wie auf dem Server; sonst
  stimmt die Zusage in der Datenschutzerklärung nicht.
