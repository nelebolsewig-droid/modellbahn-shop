#!/usr/bin/env bash
#
# Restore drill for the offsite backup, run by hand with `make sicherung-pruefen`
# (docs/BETRIEB.md, "Sicherung"; ADR 0025):
#
#   - restores the database dump of the latest snapshot on the Storage Box into a throwaway
#     PostgreSQL container without network, its data in memory only; the running shop is
#     not touched, apart from reading its two counts for comparison;
#   - counts products and orders in the restored database and reads the image archive
#     through to its end;
#   - prints a verdict in German. Exit status 0 only if all of that worked.
#
# Nothing of the backup lands on disk: restic streams the files into the container and tar.

set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="$PWD/.env"
# shellcheck source=scripts/gemeinsam.sh
source scripts/gemeinsam.sh

# A snapshot older than this means the nightly backup has stopped.
MAX_AGE_HOURS=36
container="modellbahn-probe-$$"

fail() {
  printf '\n✗ %s\n' "$1" >&2
  exit 1
}

if [[ -z "$(env_value MB_RESTIC_REPOSITORY)" ]]; then
  fail "Die Sicherung außer Haus ist nicht eingerichtet: ./scripts/einrichten.sh sicherung"
fi
if [[ ! -r "$OFFSITE_PASSWORD_FILE" ]]; then
  fail "Das restic-Passwort ist nicht lesbar. Als root starten (sudo make sicherung-pruefen)."
fi

echo "Suche die neueste Sicherung auf der Storage Box …"
listing="$(offsite_restic ls latest 2>/dev/null)" \
  || fail "Die Storage Box ist nicht erreichbar, oder es liegt noch keine Sicherung dort."
dump_path="$(grep -E '/datenbank-[0-9]{8}-[0-9]{4}\.dump$' <<<"$listing" | head -n 1 || true)"
images_path="$(grep -E '/bilder-[0-9]{8}-[0-9]{4}\.tar\.gz$' <<<"$listing" | head -n 1 || true)"
[[ -n "$dump_path" ]] || fail "Die neueste Sicherung enthält keine Datenbank."

# The time is in the file name: datenbank-20261111-0330.dump.
stamp="${dump_path##*/datenbank-}"
stamp="${stamp%.dump}"
taken_at="$(date -d "${stamp:0:8} ${stamp:9:2}:${stamp:11:2}" +%s)"
taken_label="$(date -d "@$taken_at" '+%d.%m.%Y, %H:%M Uhr')"
age_hours=$(( ($(date +%s) - taken_at) / 3600 ))
echo "Neueste Sicherung: $taken_label."

cleanup() {
  docker rm --force "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

db_user="$(env_value POSTGRES_USER)"
db_user="${db_user:-modellbahn}"
echo "Starte eine Wegwerf-Datenbank (ohne Netz, nur im Arbeitsspeicher) …"
docker run --detach --name "$container" --network none --tmpfs /var/lib/postgresql/data \
  --env POSTGRES_USER="$db_user" --env POSTGRES_DB=probe --env POSTGRES_HOST_AUTH_METHOD=trust \
  postgres:17-alpine >/dev/null
# The image first initialises the database with a server on the socket only, then restarts
# it; the server is ready for good once it answers on TCP.
ready=""
for _ in $(seq 1 60); do
  if docker exec "$container" pg_isready --quiet --host 127.0.0.1 --username "$db_user"; then
    ready=1
    break
  fi
  sleep 1
done
[[ -n "$ready" ]] || fail "Die Wegwerf-Datenbank startet nicht (docker logs $container)."

echo "Spiele die Datenbank ein …"
offsite_restic dump latest "$dump_path" \
  | docker exec -i "$container" pg_restore --exit-on-error --no-owner \
    --username "$db_user" --dbname probe \
  || fail "Die Datenbank der Sicherung vom $taken_label lässt sich nicht einspielen."

query() {
  docker exec "$container" psql --quiet --tuples-only --no-align --username "$db_user" \
    --dbname probe --command "$1"
}
products="$(query 'SELECT count(*) FROM catalog.products')" \
  || fail "In der eingespielten Datenbank fehlen die Produkte."
orders="$(query 'SELECT count(*) FROM sales.orders')" \
  || fail "In der eingespielten Datenbank fehlen die Bestellungen."
last_order="$(query "SELECT coalesce(to_char(max(placed_at) AT TIME ZONE 'Europe/Berlin', 'DD.MM.YYYY, HH24:MI'), 'keine') FROM sales.orders")"

# The running shop for comparison, read only: it may have a few more since the night.
live_count() {
  docker compose exec -T db sh -c 'psql --quiet --tuples-only --no-align \
    --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --command="$1"' sh "$1" 2>/dev/null
}
live_products="$(live_count 'SELECT count(*) FROM catalog.products' || true)"
live_orders="$(live_count 'SELECT count(*) FROM sales.orders' || true)"

images="fehlt in der Sicherung"
images_ok=""
if [[ -n "$images_path" ]]; then
  echo "Lese das Bilder-Archiv bis zum Ende …"
  if count="$(offsite_restic dump latest "$images_path" | tar -tzf - | wc -l)"; then
    images="vollständig lesbar, $count Einträge"
    images_ok=1
  else
    images="beschädigt oder unvollständig"
  fi
fi
if grep -qE '/\.env$' <<<"$listing"; then env_state="dabei"; else env_state="fehlt"; fi

printf '\n'
echo "  Datenbank:  $products Produkte, $orders Bestellungen, letzte Bestellung: $last_order"
if [[ -n "$live_products" && -n "$live_orders" ]]; then
  echo "  Shop jetzt: $live_products Produkte, $live_orders Bestellungen"
fi
echo "  Bilder:     $images"
echo "  .env:       $env_state"
if [[ -z "$images_ok" || "$env_state" != "dabei" ]]; then
  fail "Die Datenbank vom $taken_label lässt sich wiederherstellen, aber die Sicherung ist unvollständig (siehe oben)."
fi
if (( age_hours > MAX_AGE_HOURS )); then
  fail "Die Sicherung lässt sich wiederherstellen, ist aber $age_hours Stunden alt. Läuft die nächtliche Sicherung? Protokoll: /var/log/modellbahn-sicherung.log"
fi
printf '\n✓ Die Sicherung vom %s lässt sich vollständig wiederherstellen.\n' "$taken_label"
