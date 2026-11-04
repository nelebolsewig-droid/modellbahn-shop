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
ssh root@<IPv4-Adresse>
```

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

Das Skript führt durch elf Schritte und sagt bei jedem, was zu tun ist:

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
9. **Shop bauen und starten**: beim ersten Mal 10 bis 20 Minuten.
10. **Konten**: dein Inhaberkonto, auf Wunsch eins für Johann.
11. **Nächtliche Sicherung** um 3:30 Uhr.

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
| Gesperrtes Konto freigeben | `docker compose run --rm api python -m modellbahn.cli unlock-staff --email …` |
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

`make up` und `make logs` funktionieren auch, denn `.env` wählt mit
`COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml` die Einstellungen für den echten
Betrieb (ohne das Test-Postfach Mailpit).

## Sicherung

`scripts/sicherung.sh` läuft jede Nacht um 3:30 Uhr
(`/etc/cron.d/modellbahn-sicherung`, Protokoll in `/var/log/modellbahn-sicherung.log`):

- **Datenbank:** `datenbank-<Datum>.dump`, im laufenden Betrieb.
- **Bilder:** `bilder-<Datum>.tar.gz` mit Originalen und Bildgrößen. Der Bildspeicher pausiert
  dafür kurz; nachts sind so lange nur die Bilder im Shop nicht erreichbar.
- Beides liegt in `/var/backups/modellbahn` und bleibt **14 Tage**.

Eine Sicherung auf demselben Server übersteht dessen Verlust nicht. Darum regelmäßig vom
eigenen Rechner herunterladen:

```bash
scp 'root@<IPv4-Adresse>:/var/backups/modellbahn/*' ./modellbahn-sicherung/
```

Bietet dein Strato-Paket Backups oder Snapshots des Servers an, schalte sie zusätzlich ein.

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

Auf einem neuen Server zuerst die Schritte 1 bis 4 durchgehen, mit der gesicherten `.env`
statt einer neuen (sie enthält die Passwörter, zu denen die Sicherungen passen). Danach
wiederherstellen.

## Später: www.adp-modelle.de übernehmen

Der Umzug von Shopify ist ein eigener Schritt. Er setzt voraus:

- **Zahlung:** SumUp Online ist angebunden (Schritt 8 des Skripts) und mit einer echten
  Bestellung geprüft.
- **Katalog:** Der Katalog ist vollständig, mit Fotos.
- **Rechtliches:** AGB, Widerruf und Datenschutz sind geprüft. Die AGB-Seite sagt bis dahin,
  Bestellungen seien Testbestellungen; das muss vor der ersten echten Zahlung weg.

Dann:

1. In `.env` `SITE_ADDRESS` und `MB_PUBLIC_BASE_URL` auf `www.adp-modelle.de` umstellen.
2. Im Strato-Kundenlogin den A-Record von `www` auf den Server setzen.
3. Bei Shopify die Domain lösen.
4. Im eBay-Entwicklerkonto die beiden Adressen (Rücksprung nach der Anmeldung und
   Löschmeldungen) auf die neue Domain ändern.

Alte Shopify-Adressen leitet der Shop schon weiter. Die Weiterleitung von `adp-modelle.de`
und `neu.adp-modelle.de` auf `www` kommt mit diesem Schritt.
