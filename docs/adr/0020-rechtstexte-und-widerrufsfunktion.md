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
  - Die Widerrufe stehen live über der Bestellliste. Einer ohne passende Bestellung ist
    markiert, etwa ein eBay-Kauf.
  - Am Bestellpult steht ein Hinweis mit dem nächsten Schritt.
  - Noch nicht versendet: stornieren, das erstattet automatisch.
  - Schon versendet: Ware zurücknehmen und im SumUp-Konto erstatten.

## Folgen

- **Eine anwaltliche Prüfung** der drei Texte vor dem ersten echten Verkauf bleibt
  empfohlen. Die Texte folgen den gesetzlichen Mustern und den Pflichten nach BGB, EGBGB,
  DSGVO und TDDDG, sind aber keine Rechtsberatung.
- **Der EU-Gewährleistungshinweis fehlt noch.** Er ist eine amtliche Grafik, die aus dieser
  Umgebung nicht zu laden war. Sobald die Datei vorliegt, gehört sie in den Warenkorb und
  auf die Seite „Versand und Lieferung“.
- **Erstattungen nach einer Rücksendung** laufen bis auf Weiteres im SumUp-Konto. Ein
  Knopf „Erstatten“ für versendete Bestellungen im Stellwerk wäre der nächste Schritt.
- **Mit Strato** ist ein Vertrag zur Auftragsverarbeitung abzuschließen, im
  Strato-Kundenlogin. Die Datenschutzerklärung setzt ihn voraus.
- **Heruntergeladene Sicherungen** gehören nach 14 Tagen gelöscht, wie auf dem Server; sonst
  stimmt die Zusage in der Datenschutzerklärung nicht.
