# ADR 0040: Rückzahlungen bei Vorkasse mit GiroCode

Status: angenommen · 20.11.2026

## Kontext

Bei Vorkasse (ADR 0022) kann der Shop Geld nicht selbst zurückzahlen: Es liegt auf dem
Bankkonto, und jede Überweisung von dort braucht eine Freigabe mit TAN. Bisher vermerkte
der Shop die Erstattung sofort und schickte eine Mail „Rücküberweisung: …“. Ob das Geld
wirklich zurückging, stand nirgends, und die IBAN musste jemand aus dem Kontoauszug
abtippen.

Eine automatische Rückzahlung (Bank-Schnittstelle, Zahlungsauslösung) scheidet aus: Sie
braucht trotzdem eine TAN, einen Vertrag mit einem Zahlungsdienst und gäbe dem Server
Zugriff aufs Geschäftskonto.

## Entscheidung

- **Offen, bis überwiesen:** Jede Zahlung per Überweisung merkt sich neben dem Erstatteten
  (`refunded_cents`), was schon zurücküberwiesen ist (`repaid_cents`). Die Differenz ist die
  offene Rückzahlung. Mehrere Teilerstattungen vor der Überweisung werden eine Rückzahlung.
- **Konto aus dem Kontoauszug:** Das Team trägt Kontoinhaber und IBAN ein (Prüfziffer
  nach ISO 13616). Daraus zeigt das Stellwerk einen GiroCode (EPC069-12) mit Betrag und
  Verwendungszweck „Erstattung MB-…“, den die Banking-App scannt.
- **Überwiesen:** Ein Klick schließt die Rückzahlung. Kontoinhaber und IBAN werden dabei
  gelöscht; der Kontoauszug hat sie ohnehin.
- **Sichtbar:** Offene Rückzahlungen stehen über den Bestellungen und als nächster Schritt
  der Bestellung, nur für Inhaber und Team. Kunden sehen weder Konto noch Code.
- **Bestand:** Vorkasse-Erstattungen von vor dieser Änderung gelten als offen, bis jemand
  „Überwiesen“ drückt.
- **SumUp von Hand:** Eine Kartenzahlung, die schon im SumUp-Konto zurückging, lässt sich
  ohne erneute Anfrage an SumUp als erstattet vermerken.

## Folgen

- Kein neuer Dienst, kein Zugriff aufs Konto; der Shop erzeugt nur den Code.
- Die IBAN des Kunden liegt nur so lange in der Datenbank, wie die Rückzahlung offen ist.
- Was die Banking-App aus dem Code macht, prüft der Mensch vor der TAN.
