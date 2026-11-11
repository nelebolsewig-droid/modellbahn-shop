# Betrieb auf einem Strato-Server

So kommt der Shop mit dem Stellwerk auf einen eigenen Server bei Strato. Zuerst läuft er
unter **`neu.adp-modelle.de`**: Stellwerk, Fertigung, Lager und eBay sind sofort nutzbar,
während der Shopify-Shop unter `www.adp-modelle.de` weiter verkauft. `www` zieht um, sobald
die Zahlung mit SumUp angebunden ist (siehe [Später](#später-wwwadp-modellede-übernehmen)).

Die Einrichtung macht ein geführtes Skript (`scripts/einrichten.sh`). Vorher braucht es nur
einen Server und das Repository darauf.

## 1. Server bestellen

- **Ein Server mit Root-Zugang**, kein Webhosting-Paket: bei Strato „VPS Linux“ oder
  „Dedicated Server“.
- **Mindestens 2 Kerne, 4 GB Arbeitsspeicher und 80 GB SSD.** Der erste Bau des Shops
  braucht den Arbeitsspeicher; Fotos und Sicherungen den Platz.
- **Betriebssystem: Ubuntu 24.04.** Im Strato-Server-Login das Root-Passwort setzen oder
  einen SSH-Schlüssel hinterlegen.
- Die **IPv4-Adresse** des Servers notieren; sie steht im Server-Login.

## 2. Anmelden

Im Terminal (Mac, Linux) oder in der Windows-Eingabeaufforderung:

```bash
ssh -o ServerAliveInterval=30 root@<IPv4-Adresse>
```

`ServerAliveInterval=30` hält die Verbindung offen, während du im Browser etwas
nachschlägst; ohne trennt der Server sie manchmal nach ein paar Minuten Stille.

## 3. Repository holen

Das Repository ist privat. Der Server bekommt dafür einen eigenen Schlüssel, der nur lesen
darf:

```bash
apt-get update && apt-get install -y git
ssh-keygen -t ed25519 -N "" -f ~/.ssh/modellbahn_deploy -C "strato-server"
printf 'Host github.com\n  IdentityFile ~/.ssh/modellbahn_deploy\n' >> ~/.ssh/config
cat ~/.ssh/modellbahn_deploy.pub
```

1. Die ausgegebene Zeile (beginnt mit `ssh-ed25519`) kopieren.
2. Auf GitHub unter
   [Settings → Deploy keys → Add deploy key](https://github.com/nelebolsewig-droid/modellbahn-shop/settings/keys/new)
   einfügen, als Titel „Strato-Server“.
3. „Allow write access“ **nicht** anhaken, dann speichern.

Dann:

```bash
git clone git@github.com:nelebolsewig-droid/modellbahn-shop.git /opt/modellbahn-shop
```

Die Frage nach dem Fingerabdruck von github.com mit `yes` beantworten.

## 4. Einrichten

```bash
cd /opt/modellbahn-shop && ./scripts/einrichten.sh
```

Das Skript führt durch vierzehn Schritte und sagt bei jedem, was zu tun ist:

1. **Grundsystem:** Updates, Firewall (nur SSH, HTTP, HTTPS), automatische Sicherheitsupdates.
2. **Docker** aus der offiziellen Paketquelle.
3. **Domain:** Das Skript zeigt die IP-Adresse des Servers. Im Strato-Kundenlogin bekommt
   die Subdomain `neu` einen A-Record (und AAAA-Record) auf diese Adresse; das Skript wartet,
   bis er wirkt. `www` und `adp-modelle.de` bleiben unberührt.
4. **Mail:** ein Strato-Postfach (z. B. `shop@adp-modelle.de`) verschickt die Mails des
   Shops über `smtp.strato.de`. Das Passwort wird verdeckt eingegeben.
5. **Impressum:** Firma, Inhaber, Anschrift, E-Mail; optional Telefon und USt-IdNr.
6. **Geheimnisse:**
   - Datenbank, Bildspeicher und eBay-Token bekommen eigene, zufällige Werte.
   - Dazu kommen der echte Betrieb (`MB_ENVIRONMENT=production`), das Zertifikat von
     Let's Encrypt und HSTS.
7. **eBay** (überspringbar): Johanns Schlüssel und die zwei Adressen, die im
   eBay-Entwicklerkonto eingetragen werden.
8. **SumUp** (überspringbar): API-Schlüssel (`sup_sk_…`, verdeckt) und Händlercode des
   SumUp-Kontos. Ohne sie nimmt der Shop keine Bestellungen an (`MB_PAYMENT_PROVIDER=off`).
9. **Vorkasse** (überspringbar): die Bankverbindung für Überweisungen.
10. **DHL-Versandlabels** (überspringbar): API-Schlüssel und Systembenutzer.
11. **Shop bauen und starten**: beim ersten Mal 10 bis 20 Minuten.
12. **Konten**: dein Inhaberkonto, auf Wunsch eins für Johann.
13. **Nächtliche Sicherung** um 3:30 Uhr.
14. **Überwachung und Sicherung außer Haus** (überspringbar): Mails von Healthchecks.io, wenn
    der Shop oder die Sicherung ausfällt, und eine verschlüsselte Kopie jeder Sicherung auf
    einer Storage Box bei Hetzner (siehe [Überwachung](#überwachung) und
    [Sicherung](#sicherung)).

Alle Werte stehen danach in `/opt/modellbahn-shop/.env` (nur für root lesbar). Das Skript
lässt sich jederzeit erneut starten: Es bietet die gespeicherten Werte an, und einmal
erzeugte Geheimnisse bleiben, wie sie sind. So lassen sich etwa die eBay-Schlüssel oder
SumUp nachtragen.

Das Stellwerk ist dann unter **`https://neu.adp-modelle.de/admin`** erreichbar.

## Aktualisieren

Nach einem Merge auf `main`:

```bash
cd /opt/modellbahn-shop && git pull && docker compose up --detach --build --wait
```

Neue Migrationen laufen beim Start von selbst. Ein Bau dauert ein paar Minuten; der Shop
läuft währenddessen weiter und wechselt am Ende auf die neue Fassung.

## Im Betrieb

| Wozu | Befehl (in `/opt/modellbahn-shop`) |
| --- | --- |
| Läuft alles? | `docker compose ps` |
| Logs ansehen | `docker compose logs --tail 200 api worker caddy` |
| Weiteres Mitarbeiterkonto | `make staff EMAIL=… NAME="…" ROLE=staff` (oder `owner`, `packer`) |
| Mitarbeiterkonten anzeigen | `make staff-list` |
| Mitarbeiterkonto löschen | `make staff-delete EMAIL=…` (fragt nach; Anmeldungen enden sofort; das letzte Inhaberkonto bleibt) |
| Gesperrtes Konto freigeben | `docker compose run --rm api python -m modellbahn.cli unlock-staff --email …` |
| DHL einrichten oder einschalten | `./scripts/einrichten.sh dhl` |
| Überwachung und Sicherung außer Haus einrichten | `./scripts/einrichten.sh sicherung` |
| Shop prüfen wie die Überwachung | `./scripts/ueberwachung.sh` |
| Jetzt sichern (Bilder kurz nicht erreichbar) | `./scripts/sicherung.sh` |
| Sicherung zur Probe wiederherstellen | `make sicherung-pruefen` (der Shop läuft weiter) |
| Fotos ihrer Farbe zuordnen (alte Uploads) | `make gallery-colors` |
| DHL-Zugang prüfen | `make dhl-check SANDBOX=1` (Sandbox) · `make dhl-check` (Geschäftskundenkonto) |
| Neu starten | `docker compose restart api worker` |

### Zahlungen mit SumUp

- **Ablauf:** Der Kunde bezahlt auf der Seite von SumUp und kommt zur Bezahlseite des Shops
  zurück. Der Shop fragt SumUp dann selbst, wie die Zahlung ausging (ADR 0019).
  - SumUp meldet sich zusätzlich unter `/api/v1/webhooks/sumup`; diese Adresse nennt der Shop
    bei jeder Zahlung selbst, im SumUp-Konto ist nichts einzutragen.
  - Kommt beides nicht an, fragt der Worker nach einer Minute nach.
- **Im Stellwerk** steht eine Zahlung, die noch auf SumUps Seite läuft, als „Offen bei SumUp“.
- **Stornieren** schließt eine offene Bezahlseite bei SumUp. Geld, das danach noch eingeht,
  erstattet der Shop von selbst; das Log zeigt dann `sales.payment.refunded_after_cancel`.
- **Prüfen, ob SumUp antwortet:** `docker compose logs --tail 200 api worker | grep sumup`.
  `sales.sumup.error` mit `status=401` heißt: Der API-Schlüssel stimmt nicht (Skript erneut
  starten und den Schlüssel neu eintragen).
- **Zum Ausprobieren** vor dem Start eine Bestellung über ein paar Euro mit echter Karte
  bezahlen und im Stellwerk stornieren: Das prüft Zahlung und Erstattung in einem.
- **SumUp lehnt eine Erstattung ab:** Das Stellwerk zeigt „SumUp hat die Erstattung
  abgelehnt“ und darunter SumUps eigene Antwort (im Log: `sales.sumup.error` mit `status`
  und `message`). Storno bzw. Erstattung sind dann nicht gespeichert, es ging nichts zurück.
  - Den Betrag im SumUp-Konto selbst erstatten: unter den Transaktionen die Zahlung öffnen
    und dort erstatten.
  - Danach im Stellwerk dieselbe Aktion noch einmal: Beim Stornieren erscheint der Haken
    „im SumUp-Konto selbst erstattet“, bei der Erstattung der Knopf „Im SumUp-Konto
    erstattet, nur vermerken“. Der Shop vermerkt die Erstattung dann, ohne SumUp noch
    einmal zu fragen; der Kunde bekommt seine Mail wie sonst auch.
  - Bei `status=403` darf der API-Schlüssel womöglich keine Erstattungen auslösen; dann im
    SumUp-Konto die Rechte des Schlüssels prüfen.

### Vorkasse per Überweisung

Kunden können statt über SumUp auch per Überweisung bezahlen, sobald die Bankverbindung
eingetragen ist (ADR 0022; Skript erneut starten, Stufe „Vorkasse“).

- **Ablauf:** Der Kunde wählt Vorkasse auf der Bezahlseite und bekommt Bankverbindung,
  Bestellnummer als Verwendungszweck und einen GiroCode, auch per Mail. Er hat zehn Tage
  Zeit; danach storniert der Shop die Bestellung.
- **Geld ist da:** Im Kontoauszug die Überweisung mit dem Verwendungszweck `MB-…` suchen,
  im Stellwerk die Bestellung öffnen und „Überweisung eingegangen“ drücken. Der Kunde bekommt
  die Bestätigung, die Bestellung geht in die Kommissionierung.
  - Stimmt der Betrag nicht, erst mit dem Kunden klären und dann buchen.
- **Geld zurück:** Bei Storno, Teilerstattung oder Widerruf einer Vorkasse-Bestellung kann
  der Shop nicht selbst zurückzahlen.
  - An `MB_IMPRINT_EMAIL` kommt eine Mail „Rücküberweisung: … für MB-…“.
  - Den Betrag auf das Konto zurücküberweisen, von dem die Zahlung kam; IBAN und Name
    stehen im Kontoauszug.
- **Überweisung nach der Frist:** Gehört sie zu einer stornierten Bestellung, das Geld
  zurücküberweisen; der Shop kennt diesen Eingang nicht.
- **Ausschalten:** Skript erneut starten und bei „Vorkasse anbieten?“ mit `N` antworten.
  Bestellungen, die schon auf eine Überweisung warten, behalten ihre Frist und lassen sich
  weiter buchen; die Bankverbindung finden die Kunden dann nur noch in ihrer Mail.

### DHL-Versandlabels

Das Stellwerk bucht das DHL-Label, sobald ein Paket gepackt ist (ADR 0023). Eingerichtet
wird es mit `./scripts/einrichten.sh dhl`: nur diese Stufe, danach der Neustart.

- **Schlüssel einfügen:** Im Feld erscheint beim Einfügen (⌘V) nichts. Nach Enter meldet
  das Skript „✓ übernommen (… Zeichen)“; nur Enter ohne Eingabe lässt DHL aus.

- **Zugang prüfen, ohne etwas Echtes zu buchen:**
  - `make dhl-check SANDBOX=1`: DHLs Sandbox mit DHLs Testkunden. Braucht nur den
    API-Schlüssel, bucht dort ein Testlabel, misst seine Größe und storniert es wieder.
  - `make dhl-check`: das Geschäftskundenkonto (Systembenutzer, Passwort, EKP). DHL prüft
    eine Inlands- und eine EU-Sendung, ein Label entsteht nicht.
  - Beide zeigen DHLs Antwort im Wortlaut. Erst einschalten, wenn `make dhl-check` „DHL
    nimmt beide Sendungen an.“ meldet.
- **Packen:** Ist alles kommissioniert, zeigt das Bestellpult unter „Versand“ das
  Gewichtsfeld. Paket wiegen, Gewicht in Gramm eintragen, „DHL-Label buchen“.
  - „Label drucken“ öffnet das PDF. Im Druckdialog den Etikettendrucker wählen, Papier
    100 × 150 mm, „Tatsächliche Größe“.
  - Druckt die App des Druckers nur Bilder (Brother iPrint&Label), „Als Bild“ nehmen.
  - „Als versendet melden“ übernimmt die Sendungsnummer; der Kunde bekommt sie mit
    Verfolgungslink.
- **Falsches Label:** „Label stornieren“, dann neu buchen. Nach dem Versand geht das nicht
  mehr. Storniert ihr die Bestellung, storniert der Shop ihr Label bei DHL selbst.
- **„wird automatisch GoGreen Plus hinzugebucht“:** `./scripts/einrichten.sh dhl` und bei
  „GoGreen Plus bei jedem Label mitbuchen?“ mit `y` antworten.
- **DHL lehnt ab:** Unter der Meldung steht DHLs Begründung, meist Adresse oder Gewicht.
  Adresse mit dem Kunden klären; zur Not das Label im Geschäftskundenportal buchen und die
  Nummer von Hand eintragen.
- **Einschalten, Ausschalten:** `./scripts/einrichten.sh dhl` und bei „Labels im Stellwerk
  jetzt echt buchen lassen?“ mit `y` bzw. `N` antworten. Ausgeschaltet wird die Nummer
  wieder von Hand eingetragen.

### Fotos und Farben

Bei einem Modell in mehreren Farben zeigt der Shop zur gewählten Farbe das Foto, das dieser
Farbe zugeordnet ist. Ohne Zuordnung zeigt er bei jeder Farbe das erste Foto.

- **Im Stellwerk:** Katalog → Modell → Galerie, unter jedem Foto bei „Farbe“ die Farbe
  wählen und speichern. Fehlt einer Farbe noch ein Foto, sagt die Galerie es oben.
- **Foto-Skript:** ordnet jedes Foto der Farbe aus der Spalte „Farbe“ zu.
- **Fotos, die das Skript früher ohne Zuordnung hochgeladen hat:** einmal
  `make gallery-colors`. Das ordnet jedes Foto der Farbe aus seinem Bildtext („Modell, Rot“)
  zu, sofern es die Farbe beim Modell gibt.

### Etiketten der Modelle

- **Neue Stücke erfassen:** Lager → „Einheiten erfassen“, Artikel suchen, Anzahl „Stück“
  und Platz eintragen, „Erfassen und Etiketten drucken“. Unterwegs geht es mit dem Handy
  unter „Erfassen“ (neues Modell mit „Stück mit Etikett“).
- **Drucken:** A4-Bogen oder Brother-Rolle 62 mm wählen. Für die Brother-App „Als Bilder
  für die Brother-App“: jedes Etikett als Bild, einzeln oder als ZIP.
- Auf jedem Etikett stehen der Preis (oben rechts) sowie Hersteller, Anschrift und E-Mail
  aus dem Impressum.
- **Preis geändert?** Die gedruckten Etiketten zeigen den alten Preis: auf der Seite der
  Einheit (Code scannen oder im Lager öffnen) das Etikett neu drucken.

### Widerrufe

- Ein Widerruf über „Vertrag widerrufen“ kommt als E-Mail an `MB_IMPRINT_EMAIL` und steht
  im Stellwerk über der Bestellliste. Der Kunde hat seine Eingangsbestätigung dann schon
  (ADR 0020).
- **Noch nicht versendet:** Nichts zu tun. Der Shop storniert die Bestellung von selbst und
  erstattet eine eingegangene Zahlung über SumUp.
- **Schon versendet:** Ist die Ware zurück (oder die Rücksendung nachgewiesen), am
  Bestellpult unter „Erstattung“ auf „Rücksendung erhalten – erstatten“. SumUp zahlt sofort
  zurück, der Kunde bekommt eine Mail. Nur einzelne Artikel zurück: „Einzelne Artikel“
  wählen.
- **Frist:** 14 Tage nach Eingang des Widerrufs. Vier Tage vorher kommt täglich eine
  Erinnerung an `MB_IMPRINT_EMAIL`, bis erstattet ist.
- Passt ein Widerruf zu keiner Bestellung des Shops, ist es vielleicht ein eBay-Kauf; den
  erstattet man über eBay.

### Modelle löschen

- **Testmodell weg:** im Stellwerk das Modell öffnen, „Modell löschen …“, dann „Endgültig
  löschen“. Ist es im Shop, zuerst „Archivieren“.
- Mit dem Modell gehen seine nie verkauften Stücke samt Lagerbuchungen und seine
  eBay-Angebote, die nicht mehr online sind. Etiketten dieser Stücke gelten dann nicht
  mehr; am besten abziehen. Die Fotos bleiben in der Medienbibliothek.
- **Lässt sich nicht löschen?** Der Dialog sagt warum:
  - Offene Bestellungen (Nummern stehen dabei, eBay-Bestellungen mit „eBay“): versenden
    oder stornieren, dann noch einmal.
  - Stücke verkauft oder montiert: Das Modell bleibt archiviert, unsichtbar im Shop. Direkt
    nach einem Storno kann die Meldung auch kommen, bis das Lager die Stücke freigibt
    (etwa eine Minute).
  - Noch bei eBay online: Nach dem Archivieren nimmt der Shop das Angebot in ein paar
    Minuten herunter.
- Rückgängig geht nur über die Sicherung (unten, „Wiederherstellen“) (ADR 0024).

### Fotos aus einem Ordner hochladen

`scripts/fotos_hochladen.py` lädt Fotos vom eigenen Rechner in die Galerien der Produkte,
statt sie einzeln im Stellwerk hochzuladen. Es braucht nur Python 3.

- **Die Liste:** `modelle-uebersicht.csv` (Semikolon, Spalten `Datei`, `Modell`,
  `Entwurf im Startbestand`, `Farbe`, `Eignung`, `Hauptbild (ja/nein)` …). Claude Code
  schreibt sie beim Durchsehen eines Fotoordners. `Datei` ist relativ zum Ordner der Liste.
- **Was hochgeht:** je Modell das Hauptbild, dann die Fotos mit „gut“, dann „brauchbar“,
  höchstens 8 (`--max-fotos`). „nein“ bleibt draußen.
- **Wohin:** in die Galerie des Produkts mit dem Namen aus `Entwurf im Startbestand`, bei
  „neu“ aus `Modell`. Das Produkt muss es schon geben. Das Skript legt keine Produkte an und
  veröffentlicht nichts.
- **Ohne `--hochladen` ist es ein Probelauf** und zeigt nur, was passieren würde.
- **Wiederholen ist unschädlich:** Der Server erkennt ein Foto an seiner Prüfsumme, und ein
  Bild kommt nicht doppelt in eine Galerie.
- **Rohfotos (DNG, TIFF)** nimmt der Server nicht an. Auf dem Mac wandelt das Skript sie
  über Quick Look in JPEG um, richtig herum und mit höchstens 4000 Pixeln. Die JPEGs bleiben
  in `~/Library/Caches/adp-fotos-hochladen`. Der Probelauf wandelt ein Foto zur Probe um und
  nennt die Datei.
- **Erst Fotos, dann umbenennen:** Das Skript findet ein Produkt über seinen Namen. Wer ein
  Modell im Stellwerk umbenennt, lädt dessen Fotos vorher hoch.

Im Ordner mit der Liste, auf dem Mac:

```bash
curl -fsSLO https://raw.githubusercontent.com/nelebolsewig-droid/modellbahn-shop/main/scripts/fotos_hochladen.py
python3 fotos_hochladen.py modelle-uebersicht.csv --email du@example.de              # Probelauf
python3 fotos_hochladen.py modelle-uebersicht.csv --email du@example.de --hochladen
```

Das Passwort fürs Stellwerk fragt das Skript verdeckt ab.

`make up` und `make logs` funktionieren auch, denn `.env` wählt mit
`COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml` die Einstellungen für den echten
Betrieb (ohne das Test-Postfach Mailpit).

## Überwachung

Healthchecks.io schickt eine Mail, wenn der Shop nicht antwortet oder die nächtliche
Sicherung fehlschlägt (ADR 0025). Eingerichtet wird es mit `./scripts/einrichten.sh sicherung`.

- **Konto:** kostenlos auf [healthchecks.io](https://healthchecks.io), mit der Mail-Adresse,
  die die Warnungen bekommen soll. Weitere Empfänger: dort unter „Integrations“.
- **Zwei Checks**, ihre Ping-Adressen (`https://hc-ping.com/…`) fragt das Skript ab:

  | Check | Period | Grace Time | Wer meldet sich |
  | --- | --- | --- | --- |
  | Shop | 5 Minuten | 10 Minuten | `scripts/ueberwachung.sh`, alle 5 Minuten |
  | Sicherung | 1 Tag | 2 Stunden | `scripts/sicherung.sh`, jede Nacht um 3:30 Uhr |

- **Was der Server alle 5 Minuten prüft:**
  - `https://neu.adp-modelle.de/readyz` antwortet. Das klappt nur, wenn Caddy, API und
    Datenbank laufen und das HTTPS-Zertifikat gültig ist.
  - Die Festplatte (`/` und der Datenordner von Docker) ist höchstens zu 90 % voll.
- Die Ping-Adressen stehen nur in `.env`. Wer sie kennt, kann für die Checks melden; also
  nicht in Mails oder Chats weitergeben. Die Meldungen selbst enthalten keine Kundendaten.

**Grenzen:** Der Server prüft sich selbst. Fällt der ganze Server oder sein Netz aus, kann er
nichts melden. Dann bleibt die Meldung aus, und Healthchecks.io schickt die Mail nach Period
und Grace Time: beim Shop nach höchstens 15 Minuten, bei der Sicherung gegen 5:30 Uhr am
Morgen danach. Eine Sperre, die nur Besucher von außen trifft (etwa die Firewall im
Strato-Login), sieht der Server nicht.

### Was die Mails bedeuten

Healthchecks.io schreibt „down“, wenn etwas nicht stimmt, und „up“, sobald es wieder geht.
Unter der Meldung steht der Grund, den der Server geschickt hat.

| In der Mail steht | Was tun |
| --- | --- |
| Shop: „Keine Verbindung“, „Keine Antwort“ oder „HTTP 502“ | `docker compose ps`; steht ein Dienst nicht auf „running“ oder „healthy“: `docker compose up --detach --wait`, dann `docker compose logs --tail 200 api caddy` |
| Shop: „die Datenbank antwortet nicht (HTTP 503)“ | `docker compose logs --tail 100 db`; oft ist die Platte voll (`df -h`) |
| Shop: „das Zertifikat ist ungültig oder abgelaufen“ | Caddy bekommt kein neues Zertifikat: `docker compose logs caddy \| grep -i acme`. Zeigt die Adresse noch auf den Server (`dig +short neu.adp-modelle.de`)? Dann `docker compose restart caddy` |
| Shop: „Speicherplatz: / ist zu 9… % voll“ | `df -h` und `docker system df`. Platz schaffen: `docker builder prune --force` und `docker image prune --force` (alte Bauten, die Daten bleiben) |
| Shop: kein Grund, die Meldung blieb aus | Der Server oder sein Netz ist weg. Shop im Browser öffnen; im Strato-Server-Login nachsehen, ob der Server läuft, sonst dort neu starten. Der Shop startet danach von selbst |
| Sicherung: Grund mit den letzten Zeilen des Protokolls | Die Zeilen sagen, was fehlte (Platte voll, Storage Box nicht erreichbar, …). Ursache beheben, dann `./scripts/sicherung.sh` und abwarten, bis „up“ kommt |
| Sicherung: kein Grund, die Meldung blieb aus | Die Sicherung lief nicht an oder hängt: `tail -n 50 /var/log/modellbahn-sicherung.log`, `cat /etc/cron.d/modellbahn-sicherung`. Läuft der Server? |

Für geplante Arbeiten, bei denen der Shop steht, den Check in Healthchecks.io pausieren
(„Pause“). Die nächste Meldung des Servers schaltet ihn wieder ein.

Auf dem Server selbst: Probleme der Überwachung stehen in
`/var/log/modellbahn-ueberwachung.log`; `./scripts/ueberwachung.sh` prüft sofort und zeigt
das Ergebnis.

## Sicherung

`scripts/sicherung.sh` läuft jede Nacht um 3:30 Uhr
(`/etc/cron.d/modellbahn-sicherung`, Protokoll in `/var/log/modellbahn-sicherung.log`):

- **Datenbank:** `datenbank-<Datum>.dump`, im laufenden Betrieb.
- **Bilder:** `bilder-<Datum>.tar.gz` mit Originalen und Bildgrößen. Der Bildspeicher pausiert
  dafür kurz; nachts sind so lange nur die Bilder im Shop nicht erreichbar.
- Beides liegt in `/var/backups/modellbahn` und bleibt **14 Tage**.
- **Außer Haus:** Danach legt restic die beiden Dateien der Nacht und `.env` verschlüsselt auf
  eine Storage Box bei Hetzner in Deutschland. Dort bleibt ebenfalls nur, was jünger als
  **14 Tage** ist, so wie es die Datenschutzerklärung zusagt. Sonntags liest restic zur Probe
  ein Zehntel der Daten zurück.
- Geht etwas davon schief, gilt die ganze Nacht als fehlgeschlagen, und Healthchecks.io
  schickt eine Mail (siehe [Überwachung](#überwachung)). Ohne Storage Box steht im Protokoll
  nur „Sicherung außer Haus ist nicht eingerichtet“.

`.env` gehört in die Kopie, weil die Daten ohne ihre Schlüssel nicht vollständig sind (z. B.
der Schlüssel der eBay-Token und der Zugang zum Bildspeicher).

### Sicherung außer Haus einrichten

1. Bei Hetzner eine **Storage Box** bestellen; die kleinste reicht.
2. In der Hetzner-Konsole bei der Box **SSH-Support** und **Externe Erreichbarkeit**
   einschalten. Benutzername (`u` und Ziffern) und Passwort der Box bereithalten.
3. Mit Hetzner den **Vertrag zur Auftragsverarbeitung (AVV)** abschließen, ebenfalls in der
   Hetzner-Konsole. Die Datenschutzerklärung nennt Hetzner als Speicheranbieter; ohne AVV
   stimmt sie nicht.
4. Auf dem Server:

   ```bash
   cd /opt/modellbahn-shop && ./scripts/einrichten.sh sicherung
   ```

   Das Skript fragt die Ping-Adressen von Healthchecks.io, Benutzername und Adresse der Box
   (`u123456.your-storagebox.de`). Dann:
   - Es erzeugt einen eigenen SSH-Schlüssel (`/root/.ssh/modellbahn-sicherung`) und trägt
     die Box unter dem Namen `modellbahn-sicherung` in `/root/.ssh/config` ein (Port 23).
   - Es bringt den Schlüssel auf die Box. Dafür fragt die Box **einmal** nach ihrem Passwort.
   - Es legt die verschlüsselte Sicherung auf der Box an (Ordner `modellbahn`) und würfelt
     ihr Passwort.
5. **Das Passwort der Sicherung erscheint genau einmal.** Sofort in den Passwort-Manager
   legen, zusammen mit Benutzername und Adresse der Box. Ohne dieses Passwort kann niemand
   die Sicherung öffnen, auch Hetzner nicht. Geht der Server verloren, ist es der einzige Weg
   zurück. Auf dem Server steht es nur in `/root/.config/modellbahn/restic-passwort`.
6. Zum Schluss bietet das Skript eine Sicherung und eine Probe-Wiederherstellung an.

Das Skript lässt sich gefahrlos erneut starten: Enter behält die Werte, Schlüssel, Passwort
und Sicherung auf der Box bleiben, wie sie sind.

### Probe-Wiederherstellung

```bash
cd /opt/modellbahn-shop && make sicherung-pruefen
```

Holt die neueste Datenbank von der Storage Box und spielt sie in eine Wegwerf-Datenbank ein,
die nur im Arbeitsspeicher lebt; der Shop läuft dabei weiter und merkt nichts. Dann zählt sie
Produkte und Bestellungen, liest das Bilder-Archiv bis zum Ende und sagt:

- **„✓ Die Sicherung vom … lässt sich vollständig wiederherstellen.“** Alles gut. Die Zahlen
  darunter sollten zu denen des Shops passen („Shop jetzt“); seit der Nacht können ein paar
  dazugekommen sein.
- **„✗ …“** mit Grund: Die Sicherung taugt so nicht. Den Grund beheben (oft wie bei den Mails
  oben) und danach `./scripts/sicherung.sh` und `make sicherung-pruefen` wiederholen.

Am besten einmal im Monat und nach jeder größeren Änderung am Server.

### Wiederherstellen

Datenbank (der Shop steht dabei still):

```bash
cd /opt/modellbahn-shop
docker compose stop api worker
docker compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  < /var/backups/modellbahn/datenbank-<Datum>.dump
docker compose start api worker
```

Bilder:

```bash
cd /opt/modellbahn-shop
docker compose stop storage
docker run --rm --volumes-from "$(docker compose ps --all --quiet storage)" \
  --volume /var/backups/modellbahn:/backup postgres:17-alpine \
  sh -c 'rm -rf /var/lib/garage/meta/* /var/lib/garage/data/* && tar -xzf /backup/bilder-<Datum>.tar.gz -C /var/lib/garage'
docker compose start storage
```

Fehlt die Nacht in `/var/backups/modellbahn`, liegt sie noch auf der Storage Box (höchstens
14 Tage zurück):

```bash
export RESTIC_REPOSITORY=sftp:modellbahn-sicherung:modellbahn RESTIC_PASSWORD_FILE=/root/.config/modellbahn/restic-passwort
restic snapshots
restic restore <ID> --target /root/wiederherstellung
```

`restic snapshots` zeigt eine Zeile je Nacht; die ID der gewünschten Nacht nehmen (oder
`latest` für die neueste). Die Dateien liegen danach unter
`/root/wiederherstellung/var/backups/modellbahn/`; in den Befehlen oben diesen Ordner statt
`/var/backups/modellbahn` nehmen. Danach `rm -rf /root/wiederherstellung`.

### Auf einem neuen Server

Ist der alte Server verloren, kommt alles von der Storage Box. Dafür braucht es das Passwort
der Sicherung aus dem Passwort-Manager und das Passwort der Storage Box.

1. Die Schritte 1 bis 3 oben: Server bestellen, anmelden, Repository holen.
2. Storage Box anbinden:

   ```bash
   cd /opt/modellbahn-shop && ./scripts/einrichten.sh sicherung
   ```

   - Ping-Adressen: nur Enter, sie kommen gleich mit der alten `.env`.
   - Benutzername und Adresse der Box eingeben; die Box fragt einmal nach ihrem Passwort.
   - Das Skript findet die alte Sicherung und fragt nach **ihrem Passwort** aus dem
     Passwort-Manager.
   - „Jetzt einmal sichern?“ mit `N` beantworten: Es gibt noch nichts zu sichern.
3. Die neueste Nacht holen und die alte `.env` zurücklegen:

   ```bash
   export RESTIC_REPOSITORY=sftp:modellbahn-sicherung:modellbahn RESTIC_PASSWORD_FILE=/root/.config/modellbahn/restic-passwort
   restic restore latest --target /root/wiederherstellung
   cp /root/wiederherstellung/opt/modellbahn-shop/.env /opt/modellbahn-shop/.env
   mkdir -p /var/backups/modellbahn && cp /root/wiederherstellung/var/backups/modellbahn/* /var/backups/modellbahn/
   ```

4. Das ganze Skript wie in Schritt 4 oben: `./scripts/einrichten.sh`. Es bietet die Werte der
   alten `.env` an (Enter behält sie) und erzeugt keine neuen Geheimnisse. Bei „Domain“ den
   A-Record auf die **neue** IP-Adresse setzen. Die Fragen nach einer Probe-Sicherung mit `N`
   beantworten, bis die Daten zurück sind.
5. Datenbank und Bilder wie oben unter „Wiederherstellen“ einspielen, mit den Dateien aus
   `/var/backups/modellbahn`.
6. Prüfen: Shop und Stellwerk im Browser, dann `./scripts/sicherung.sh` und
   `make sicherung-pruefen`. Danach `rm -rf /root/wiederherstellung`.

## Später: www.adp-modelle.de übernehmen

Der Umzug von Shopify ist ein eigener Schritt. Er setzt voraus:

- **Zahlung:** SumUp Online ist angebunden (Schritt 8 des Skripts) und mit einer echten
  Bestellung geprüft.
- **Katalog:** Der Katalog ist vollständig, mit Fotos.
- **Rechtliches:**
  - AGB, Widerrufsbelehrung und Datenschutzerklärung stehen im Shop (ADR 0020); vor dem
    Start sollte sie ein Anwalt durchsehen.
  - Mit Strato ist im Kundenlogin der Vertrag zur Auftragsverarbeitung abgeschlossen,
    mit Hetzner für die Storage Box ebenso (siehe „Sicherung außer Haus einrichten“).
  - Der EU-Gewährleistungshinweis (Pflicht seit 27.09.2026) ist eingebunden (ADR 0020).

Dann:

1. In `.env` `SITE_ADDRESS` und `MB_PUBLIC_BASE_URL` auf `www.adp-modelle.de` umstellen.
2. Im Strato-Kundenlogin den A-Record von `www` auf den Server setzen.
3. Bei Shopify die Domain lösen.
4. Im eBay-Entwicklerkonto die beiden Adressen (Rücksprung nach der Anmeldung und
   Löschmeldungen) auf die neue Domain ändern.

Alte Shopify-Adressen leitet der Shop schon weiter. Die Weiterleitung von `adp-modelle.de`
und `neu.adp-modelle.de` auf `www` kommt mit diesem Schritt.
