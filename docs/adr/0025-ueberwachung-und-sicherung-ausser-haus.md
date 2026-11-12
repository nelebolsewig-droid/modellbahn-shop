# ADR 0025: Überwachung und Sicherung außer Haus

Status: angenommen · 11.11.2026

## Kontext

Der Shop läuft auf einem einzigen Server bei Strato (KONZEPT, Entscheidung 1). Ging er bisher
aus, merkte das niemand, bis ein Kunde schrieb. Die nächtliche Sicherung schrieb ihre Fehler
in ein Protokoll, das niemand liest.

Die Sicherungen lagen 14 Tage in `/var/backups/modellbahn`, auf demselben Server. Gehen Server
oder Platte verloren, sind sie mit weg. Die Betriebsanleitung empfahl, sie regelmäßig von Hand
herunterzuladen; darauf ist kein Verlass.

Den Server betreut die Werkstatt selbst, ohne Fachleute: Befehle werden einzeln in eine
SSH-Sitzung kopiert. Was hier entsteht, muss sich mit dem Einrichtungsskript aufsetzen lassen
und danach von selbst laufen.

Die Datenschutzerklärung sagt zu: Was ein Kunde löschen lässt, verschwindet spätestens nach
14 Tagen auch aus den Sicherungen (ADR 0020).

## Entscheidung

### Überwachung mit Healthchecks.io

- **Prinzip Totmannschalter:** Der Server meldet sich regelmäßig bei Healthchecks.io
  (kostenloser Tarif). Meldet er einen Fehler oder bleibt die Meldung aus, schickt
  Healthchecks.io eine Mail. Auf dem Server braucht es dafür nur bash, curl und df.
- **Zwei Checks**, ihre Ping-Adressen stehen in `.env`:
  - `MB_HEALTHCHECK_SHOP_URL`: Period 5 Minuten, Grace Time 10 Minuten.
  - `MB_HEALTHCHECK_BACKUP_URL`: Period 1 Tag, Grace Time 2 Stunden.
  - Ohne Adresse meldet das jeweilige Skript nichts. Ein halb eingerichteter Server bleibt
    so still, statt Fehlalarme zu schicken.
- **`scripts/ueberwachung.sh`**, per cron alle 5 Minuten
  (`/etc/cron.d/modellbahn-ueberwachung`):
  - Ruft `MB_PUBLIC_BASE_URL` + `/readyz` von außen auf, mit 20 Sekunden Zeitlimit. Das
    prüft DNS, Caddy, API und Datenbank in einem. curl prüft dabei das Zertifikat, also
    schlägt auch ein abgelaufenes fehl.
  - Prüft die Belegung von `/` und dem Datenordner von Docker; über 90 % ist ein Fehler.
  - Erfolg: Ping mit einer Zusammenfassung. Fehler: `/fail` mit dem Grund auf Deutsch
    („Die API läuft, die Datenbank antwortet nicht (HTTP 503).“), den Healthchecks.io in die
    Mail übernimmt. Kundendaten enthalten die Meldungen nie.
- **`scripts/sicherung.sh`** meldet `/start`, am Ende Erfolg oder `/fail` mit den letzten
  20 Zeilen seiner Ausgabe. Die eigentliche Arbeit läuft in einer Unterschale mit `set -e`;
  ihr Status entscheidet über die Meldung.
- **Grenze:** Der Server prüft sich selbst. Fällt er ganz aus oder ist sein Netz weg, bleibt
  die Meldung aus, und die Mail kommt nach Period und Grace Time. Eine Sperre, die nur
  Besucher von außen trifft, sieht er nicht.
- **Erwogen:** Ein reiner Prüfdienst von außen (etwa UptimeRobot) bemerkt keine
  fehlgeschlagene Sicherung und keine volle Platte. Eine eigene Überwachung (Uptime Kuma)
  bräuchte einen zweiten Server. Healthchecks.io deckt Shop und Sicherung mit einem
  Mechanismus ab und ist quelloffen, ließe sich also später selbst betreiben.

### Sicherung außer Haus mit restic auf einer Hetzner Storage Box

- **Werkzeug:** restic aus der Paketquelle von Ubuntu. Es verschlüsselt auf dem Server,
  bevor etwas ihn verlässt, dedupliziert, prüft das Repository (`restic check`) und stellt
  einzelne Dateien wieder her. Ein SFTP-Server genügt als Gegenstelle.
- **Ziel:** eine Storage Box bei Hetzner in Deutschland, per SFTP über Port 23.
  - Root bekommt einen eigenen Schlüssel (`/root/.ssh/modellbahn-sicherung`, ed25519) und
    den Host-Alias `modellbahn-sicherung` in `/root/.ssh/config` mit Port, Benutzer und
    `BatchMode yes`; cron kann keine Passwortfrage beantworten.
  - Den Host-Schlüssel der Box merkt sich SSH beim ersten Kontakt (`accept-new`).
  - Das Repository heißt damit schlicht `sftp:modellbahn-sicherung:modellbahn`
    (`MB_RESTIC_REPOSITORY`).
- **Ein Snapshot je Nacht** mit nur den Dateien dieser Nacht: Datenbank-Dump, Bilder-Archiv
  und `.env`.
  - `.env` gehört dazu, weil die Daten ohne ihre Schlüssel nicht vollständig sind: der
    Schlüssel der eBay-Token und der Zugang, den die Metadaten des Bildspeichers erwarten.
    Ein neuer Server braucht sie zum Wiederherstellen.
  - Sie liegt dort verschlüsselt; das Passwort hat nur die Werkstatt.
- **Aufbewahrung wie auf dem Server, 14 Tage:**
  `restic forget --group-by '' --keep-within 14d --prune --max-unused 0`.
  - `--group-by ''`: restic gruppiert sonst nach Host und Pfaden. Jede Nacht hat andere
    Dateinamen, jeder Snapshot wäre der neueste seiner Gruppe und bliebe für immer.
  - `--max-unused 0`: `prune` lässt sonst bis zu 5 % ungenutzte Daten liegen, darunter Teile
    vergessener Snapshots. Erst so gilt die Löschzusage der Datenschutzerklärung auch hier.
- **Sonntags** liest `restic check --read-data-subset 10%` ein Zehntel der Daten zurück.
- **Fehler außer Haus sind Fehler der Nacht:** Die Mail kommt wie bei einem fehlgeschlagenen
  Dump. Ist nichts eingerichtet, steht nur eine Zeile im Protokoll.
- **Passwort:** Das Einrichtungsskript würfelt es (`openssl rand -hex 24`) und zeigt es
  genau einmal, mit der Bitte, es sofort in den Passwort-Manager zu legen. Auf dem Server
  steht es nur in `/root/.config/modellbahn/restic-passwort` (0600), nicht in `.env`:
  - `.env` geht in den Snapshot und wird am häufigsten gelesen und kopiert. Der Schlüssel zur
    Kopie außer Haus soll nicht mit ihr reisen.
  - restic liest die Datei selbst (`RESTIC_PASSWORD_FILE`); das Passwort steht nie in einer
    Umgebungsvariable oder Befehlszeile.
- **Probe-Wiederherstellung** `make sicherung-pruefen` (`scripts/sicherung_pruefen.sh`):
  - Spielt den neuesten Dump in einen Wegwerf-Container `postgres:17-alpine` ein, ohne Netz
    und mit den Daten nur im Arbeitsspeicher. restic streamt ihn hinein, nichts landet auf
    der Platte.
  - Zählt Produkte und Bestellungen, nennt die letzte Bestellung, liest das Bilder-Archiv bis
    zum Ende und prüft, dass `.env` dabei ist.
  - Urteil auf Deutsch; älter als 36 Stunden gilt als Hinweis, dass die Nacht ausfiel.
- **Einrichtungsskript:** Stufe 14 „Überwachung und Sicherung außer Haus“, allein mit
  `./scripts/einrichten.sh sicherung`.
  - Fragt Ping-Adressen und die Storage Box ab, installiert restic, erzeugt den Schlüssel
    und bringt ihn mit Hetzners `install-ssh-key` auf die Box (deren Passwort fragt sie
    einmal selbst ab), legt das Repository an und schreibt den cron-Eintrag.
  - Ein zweiter Lauf behält alles: Enter behält die Werte, Schlüssel und Passwort werden
    nicht neu erzeugt, ein bestehendes Repository nicht neu angelegt.
  - Liegt auf der Box schon ein Repository und fehlt das Passwort (neuer Server), fragt es
    nach dem Passwort aus dem Passwort-Manager.
- **Datenschutz:** Die Datenschutzerklärung nennt die Hetzner Online GmbH in Gunzenhausen als
  Speicheranbieter mit Vertrag zur Auftragsverarbeitung, die Verschlüsselung und die 14 Tage.
  Den AVV schließt die Werkstatt in der Hetzner-Konsole ab.
- **Erwogen:**
  - Snapshots des Servers bei Strato: hängen am selben Anbieter und Vertrag wie der Server.
  - Borg: bräuchte Borg auch auf der Gegenseite und passende Versionen.
  - scp oder rsync: ohne Verschlüsselung, Deduplizierung und Prüfung.

## Folgen

- Fällt der Shop aus, kommt nach höchstens 15 Minuten eine Mail; fällt eine Sicherung aus, am
  Morgen danach. Die Betriebsanleitung sagt zu jeder Meldung, was zu tun ist.
- Geht der Server verloren, lässt sich der Shop auf einem neuen Server aus der Storage Box
  wiederherstellen (BETRIEB, „Auf einem neuen Server“). Verloren ist, was seit der letzten
  Nacht geschah; Bestellmails haben Kunde und Werkstatt noch.
- Ohne das Passwort der Sicherung ist die Kopie außer Haus wertlos. Es liegt bei der
  Werkstatt im Passwort-Manager; kein Skript zeigt es ein zweites Mal.
- Das Herunterladen der Sicherungen von Hand entfällt.
- Das Bilder-Archiv ist mit gzip gepackt, restic kann es darum nicht deduplizieren: Jede
  Nacht geht es ganz hinaus und liegt bis zu 15-mal auf der Box. Bei der heutigen Menge Fotos
  ist das unkritisch. Wächst sie stark, die Bilder ungepackt sichern.
- Offen: eine Prüfung von außerhalb des Servers und eine Warnung vor dem Ablauf des
  Zertifikats (Caddy erneuert es lange vor dem Ablauf selbst).

## Nachtrag 12.11.2026

Hetzner hat den Ausweis-Abgleich für das Kundenkonto abgelehnt. Die Sicherung außer Haus ist
deshalb zurückgestellt; die Überwachung mit Healthchecks.io läuft ohne sie
(`./scripts/einrichten.sh sicherung`, bei „Storage Box jetzt anbinden?“ Enter). Die
Datenschutzerklärung nennt einen Speicheranbieter erst wieder, wenn eine Kopie außer Haus
eingerichtet ist.
