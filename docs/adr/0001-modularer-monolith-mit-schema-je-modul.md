# ADR 0001: Modularer Monolith mit Schema je Modul

Status: angenommen · 22.10.2026

## Kontext

Der Shop umfasst neun fachliche Bereiche (Konzept §2.2), wird anfangs von sehr wenigen
Menschen entwickelt und läuft auf einem eigenen Server mit Docker Compose. Microservices
brächten verteilte Transaktionen, Netzwerkfehler zwischen Diensten und mehrere Deployments,
ohne dass die Last sie verlangt. Ein Monolith ohne innere Grenzen verwächst dagegen mit der
Zeit, und das spätere Herauslösen rechenintensiver Teile (Medien, Planung) würde teuer.

## Entscheidung

- Ein Repository, eine Codebasis, zwei Prozesse: API und Worker.
- Fachliche Module unter `modellbahn.modules.<name>`, jedes mit eigenem PostgreSQL-Schema
  (`identity`, später `catalog`, `sales` …). Der Plattform-Kern `modellbahn.platform` enthält
  keine Fachlogik, besitzt das Schema `platform` (Outbox) und importiert kein Modul.
- Schichten im Modul: `api` und `infrastructure` → `application` → `domain`. Die Domäne ist
  reines Python ohne Framework.
- Andere Module sehen nur das Paket `contracts` eines Moduls: Ereignisklassen, DTOs,
  Abfragefunktionen. Reaktionen auf fremde Vorgänge laufen über Ereignisse (ADR 0002).
  Ereignisse und Typen liegen in `contracts.events` ohne Framework, die Abfragen in
  eigenen Untermodulen. So bleibt eine Domäne rein, die auf fremde Ereignisse reagiert.
- Nur die Schicht `domain` ist Pflicht; ein Modul darf `api`, `infrastructure` und
  `application` weglassen.
- Fremdschlüssel über Modulgrenzen zeigen nur auf Aggregatwurzeln und löschen nie kaskadierend.
- import-linter prüft die Import-Regeln in jedem CI-Lauf. Die Verträge verwenden Platzhalter;
  ein Test schlägt fehl, wenn ein neues Modul von ihnen nicht erfasst wird.

## Folgen

- Ein Deployment, eine Datenbank, Transaktionen ohne verteilte Koordination.
- Ein Modul herauszulösen bleibt ein geplanter Handgriff: Schema in eine eigene Datenbank
  verschieben, Fremdschlüssel über die Grenze durch ID plus Ereignis ersetzen, den
  Outbox-Transport austauschen.
- PostgreSQL erzwingt die Schema-Grenzen nicht, solange alle Module denselben
  Datenbanknutzer verwenden. SQL über fremde Schemas muss im Review abgelehnt werden.
- Mehr Code als ein schlichter CRUD-Monolith: imperatives Mapping, Verträge, DTOs.
- Alle Module skalieren gemeinsam, bis eines herausgelöst wird.
