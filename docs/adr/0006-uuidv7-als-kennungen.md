# ADR 0006: UUIDv7 als Kennungen

Status: angenommen · 22.10.2026

## Kontext

Kennungen aus einer Datenbank-Sequenz verraten Mengen (wie viele Bestellungen gab es?),
brauchen vor dem Einfügen einen Datenbankzugriff und kollidieren, sobald ein Modul in eine
eigene Datenbank wandert. Zufällige UUIDv4 vermeiden das, verteilen Einfügungen aber quer über
den B-Baum-Index und lassen sich nicht nach Entstehungszeit sortieren. Outbox und SSE-Replay
brauchen genau diese Reihenfolge (ADR 0002).

## Entscheidung

- Alle Kennungen sind UUIDv7 (RFC 9562): 48 Bit Millisekunden-Zeitstempel, danach Zufall.
- Erzeugt werden sie im Code mit `modellbahn.platform.ids.new_id()`, gespeichert als
  PostgreSQL-Typ `uuid`. Python 3.13 bringt noch kein `uuid.uuid7()` mit; deshalb erzeugt
  `uuid-utils` den Wert, und `new_id()` gibt ein gewöhnliches `uuid.UUID` zurück.
- Die ID eines Domänenereignisses ist zugleich die ID seiner Outbox-Zeile. Der Worker
  arbeitet in ID-Reihenfolge ab, und der SSE-Endpunkt liefert nach `Last-Event-ID` alle
  Ereignisse mit größerer ID nach.
- Lesbare Nummern (Bestellnummer, SKU, Teilenummer) kommen bei Bedarf zusätzlich.

## Folgen

- Die ID steht vor dem Speichern fest. Aggregate und Ereignisse können sich innerhalb einer
  Unit of Work aufeinander beziehen, ohne vorher zu flushen.
- Neue Zeilen landen am Ende des Index; das hält Primärschlüssel-Indizes kompakt.
- Kennungen sind über Module und spätere Dienste hinweg eindeutig.
- Der Entstehungszeitpunkt ist aus der ID ablesbar. Für Geheimnisse taugt sie deshalb nicht;
  Sitzungs- und E-Mail-Tokens sind eigene Zufallswerte (ADR 0003).
- Die Ordnung ist so genau wie die Uhren der Prozesse. Eine strenge globale Reihenfolge
  verspricht das System nirgends.
- 16 statt 8 Byte je Schlüssel gegenüber `bigint`.
