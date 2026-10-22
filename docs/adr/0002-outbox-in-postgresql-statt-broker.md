# ADR 0002: Outbox in PostgreSQL statt Broker

Status: angenommen · 22.10.2026

## Kontext

Module reagieren auf Vorgänge anderer Module: Eine Registrierung löst eine Bestätigungs-E-Mail
aus, später teilt das Lager zu, sobald eine Bestellung bezahlt ist. Wer erst die Datenbank
committet und dann eine Nachricht an einen Broker schickt (oder umgekehrt), verliert bei einem
Absturz dazwischen Ereignisse oder verschickt welche für nie gespeicherte Daten. Ein Broker wie
RabbitMQ, NATS oder Kafka wäre außerdem ein weiterer Dienst zum Betreiben, Sichern und
Überwachen, und das bei einer Last, die PostgreSQL mühelos trägt.

## Entscheidung

- Transaktionale Outbox in der Tabelle `platform.outbox`. `uow.commit()` schreibt je
  Domänenereignis eine Zeile in derselben Transaktion wie die Fachdaten und weckt den Worker
  mit `pg_notify('mb_outbox', '')`.
- Der Worker lauscht per `LISTEN` und fragt zusätzlich alle `MB_OUTBOX_POLL_SECONDS` nach. Er
  holt fällige Zeilen mit `FOR UPDATE SKIP LOCKED`, sortiert nach der UUIDv7-ID (ADR 0006),
  und ruft den für den Ereignistyp registrierten Handler auf. Je Ereignistyp gibt es höchstens
  einen Handler: Der Zustellstatus gilt je Ereignis, eine Wiederholung nach dem Fehlschlag
  eines zweiten Handlers ließe den ersten erneut laufen. Braucht ein zweites Modul dasselbe
  Ereignis, bekommt die Outbox zuerst einen Zustellstatus je Handler; bis dahin lehnt die
  Registrierung einen zweiten Handler ab.
- Fehlschläge werden mit 30 s · 2^(Versuche − 1), höchstens einer Stunde, wiederholt; nach
  `MB_OUTBOX_MAX_ATTEMPTS` Versuchen wird die Zeile `dead` und bleibt zur Untersuchung stehen.
- Nach Erfolg meldet der Worker Ereignisse mit Zielgruppe über `pg_notify('mb_events', …)`
  an die API-Instanzen, die sie per Server-Sent Events weiterreichen. Ein Ereignis ohne
  Handler gilt sofort als veröffentlicht.

## Folgen

- Kein Ereignis geht verloren, und keines entsteht ohne Commit der Fachdaten.
- Kein zusätzlicher Dienst. Mehrere Worker teilen sich die Arbeit dank `SKIP LOCKED`.
- Zustellung mindestens einmal: Jeder Handler muss idempotent sein (z. B. eindeutige
  `source_event_id` an erzeugten Tokens). Eine globale Reihenfolge ist nicht zugesichert.
- `NOTIFY` speichert nichts und fasst knapp 8000 Byte. Echtzeitdaten werden daher gekürzt,
  und ein SSE-Client holt nach einem Abbruch Verpasstes mit `Last-Event-ID` aus der Outbox.
- Veröffentlichte Zeilen löscht der Worker nach 30 Tagen; so lange reicht auch das Nachholen
  per `Last-Event-ID`. Tote Zeilen bleiben zur Untersuchung stehen.
- Wird ein Modul herausgelöst, wechselt nur der Transport (z. B. auf NATS JetStream);
  Ereignistypen und JSON-Nutzdaten bleiben.
