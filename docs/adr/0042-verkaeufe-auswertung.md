# ADR 0042: Auswertung der Verkäufe – Bestseller, Prognose, Messen im Vergleich

Status: angenommen · 20.11.2026

## Kontext

Die Seite „Verkäufe“ (ADR 0039) zeigt, *wie viel* in einem Zeitraum eingenommen wurde.
Gefragt war zusätzlich, *was* sich verkauft: welche Modelle, in welchem Maßstab, zu
welchem Preis, wie eine laufende Messe ausgehen wird und wie die Messen und der
Onlineshop untereinander abschneiden.

## Entscheidung

- `GET /admin/sales/report` liefert je Zeile zusätzlich `variant_id`, `product_name`,
  `product_slug`, `scale_code` und `variant_name`. Bei Onlinebestellungen kommen Modell
  und Ausführung aus dem Titel der Bestellzeile (so, wie verkauft), bei Stücken aus dem
  Katalog.
- Die Auswertung rechnet im Browser aus diesen Zeilen (`lib/sales/insights.ts`, ohne
  neue Tabellen) und folgt dem Zeitraum und dem Kanalfilter der Seite:
  - **Was läuft am besten?** Rangliste nach Modell, Maßstab oder Ausführung, nach Umsatz,
    mit Stück, Ø-Preis, Anteil und Trend in Stück gegenüber dem gleich langen Zeitraum
    davor (bei einer Messe ohne Trend).
  - **Prognose.** Während einer gewählten, laufenden Messe: Umsatz bis zum letzten
    Messetag beim Schnitt der bisherigen Messetage (der heutige zählt voll, also eher
    vorsichtig). Sonst, ab sieben Tagen: die nächsten 30 Tage bei gleichem Tempo.
  - **Reicht der Bestand?** Die fünf meistverkauften Ausführungen gegen den freien
    Bestand (`in_stock`): reicht, wird knapp (mehr als zwei Drittel gebraucht) oder reicht
    nicht.
  - **Messen im Vergleich.** Alle Messen der letzten 12 Monate aus der Messeliste mit
    Umsatz, Stück, € je Messetag und Bestseller; gezählt wird Kanal „Messe“ an den
    Messetagen. Ein Klick wählt die Messe als Zeitraum.

## Folgen

- Keine Migration, keine neuen Rechte (wie „Verkäufe“: Inhaber und Mitarbeiter).
- Die Prognose ist eine einfache Hochrechnung, keine Saison- oder Wochentagslogik.
- Umbenannte Modelle erscheinen bei alten Onlinebestellungen unter dem alten Namen, aber
  über `product_slug` in derselben Zeile.
