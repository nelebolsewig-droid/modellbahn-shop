# ADR 0005: Kundenkonten ab Start, Gastbestellung mit späterer Übernahme

Status: angenommen · 22.10.2026

## Kontext

Der Auftraggeber hat am 21.10.2026 entschieden (Konzept §13, Nr. 3): Kundenkonten gibt es ab
dem ersten Tag, eine Bestellung als Gast bleibt trotzdem möglich. Gastbestellungen sollen im
Konto auftauchen, sobald sich der Kunde registriert. Würde allein die gleiche E-Mail-Adresse
genügen, könnte jemand mit einer fremden Adresse ein Konto anlegen und fremde Bestellungen
einsehen. Außerdem darf die Registrierung nicht verraten, welche Adressen schon ein Konto haben.

## Entscheidung

- Schritt 2 liefert das vollständige Kundenkonto: Registrierung mit E-Mail-Bestätigung,
  Anmeldung, Passwort ändern und zurücksetzen, Anzeigename, Konto löschen.
- Kunden und Mitarbeiter stehen in `identity.accounts`, unterschieden durch `kind`. Die
  E-Mail-Adresse ist je Kontoart eindeutig, ohne Groß- und Kleinschreibung (`citext`).
- Kunden melden sich erst mit bestätigter Adresse an. Die Bestätigung erzeugt das Ereignis
  `identity.account.email_verified`, öffentlich in `contracts.events` des Moduls.
- Ab Schritt 4 ordnet der Verkauf auf dieses Ereignis hin alle Gastbestellungen mit derselben
  Adresse dem Konto zu. Bis dahin hat das Ereignis keinen Handler; der Dispatcher markiert
  es als veröffentlicht und meldet es dem Stellwerk.
- Registrierung, Passwort-Reset und erneuter Versand antworten immer gleich. Wer sich mit
  einer vergebenen Adresse registriert, bekommt eine E-Mail statt einer Fehlermeldung.
- Löschen (DSGVO) anonymisiert die Zeile statt sie zu entfernen: Adresse
  `deleted+<id>@invalid.local`, Name „Gelöschtes Konto“, unbrauchbarer Passwort-Hash,
  Sitzungen und Tokens weg.

## Folgen

- Nur wer die Adresse kontrolliert, sieht die zugehörigen Gastbestellungen.
- Der Verkauf kennt vom Identitätsmodul nur das Ereignis, keine Interna.
- Registrierung braucht von Anfang an E-Mail-Versand und den Worker; lokal fängt Mailpit
  alle E-Mails ab.
- Anonymisierte Zeilen bleiben, damit spätere Bestellungen gültig auf sie verweisen.
- Dieselbe Person kann Mitarbeiter und Kunde sein, mit zwei getrennten Konten.
