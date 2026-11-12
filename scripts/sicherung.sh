#!/usr/bin/env bash
#
# Nightly backup of the shop on its server (docs/BETRIEB.md, "Sicherung"; ADR 0025):
#
#   - the database as a pg_dump in PostgreSQL's custom format, taken while the shop runs;
#   - the object storage (photo originals and image sizes) as a tar archive of Garage's
#     metadata and data. Garage must not write while its metadata is copied, so the storage
#     pauses for the copy; at night only the images of the shop are briefly unavailable.
#
# Keeps BACKUP_KEEP_DAYS days (default 14) in BACKUP_DIR (default /var/backups/modellbahn).
# Copies on this server do not survive the loss of the server. With MB_RESTIC_REPOSITORY in
# .env, restic therefore also stores the night's two files and .env encrypted on the Hetzner
# Storage Box, deletes what is older than 14 days there too, and on Sundays reads back a
# sample. If that offsite copy fails, the whole run counts as failed.
#
# With MB_HEALTHCHECK_BACKUP_URL in .env the run reports to Healthchecks.io: /start, then
# success, or /fail with the last lines of its output.

set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="$PWD/.env"
# shellcheck source=scripts/gemeinsam.sh
source scripts/gemeinsam.sh
target="${BACKUP_DIR:-/var/backups/modellbahn}"
keep_days="${BACKUP_KEEP_DAYS:-14}"
stamp="$(date +%Y%m%d-%H%M)"
ping_url="$(env_value MB_HEALTHCHECK_BACKUP_URL)"

umask 077

local_backup() {
  mkdir -p "$target"

  # Written under a temporary name first, so a failed dump never looks like a backup.
  docker compose exec -T db sh -c \
    'pg_dump --format=custom --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
    > "$target/datenbank-$stamp.dump.part"
  mv "$target/datenbank-$stamp.dump.part" "$target/datenbank-$stamp.dump"

  local storage
  storage="$(docker compose ps --all --quiet storage)"
  if [[ -z "$storage" ]]; then
    echo "Kein Container für den Bildspeicher (storage) gefunden." >&2
    return 1
  fi
  docker compose stop storage >/dev/null
  trap 'docker compose start storage >/dev/null' EXIT
  # Any image with tar will do; the database's is on the server anyway.
  docker run --rm --volumes-from "$storage" --volume "$target:/backup" postgres:17-alpine \
    tar -czf "/backup/bilder-$stamp.tar.gz.part" -C /var/lib/garage meta data
  docker compose start storage >/dev/null
  trap - EXIT
  # Garage's metadata holds the storage's access keys: readable for root only.
  chmod 600 "$target/bilder-$stamp.tar.gz.part"
  mv "$target/bilder-$stamp.tar.gz.part" "$target/bilder-$stamp.tar.gz"

  find "$target" -maxdepth 1 \( -name 'datenbank-*.dump' -o -name 'bilder-*.tar.gz' \) \
    -mtime +"$keep_days" -delete
  find "$target" -maxdepth 1 -name '*.part' -mtime +1 -delete

  echo "Auf diesem Server gesichert: $(du -sh "$target" | cut -f1) in $target"
}

# One snapshot per night with only that night's files, so that forgetting snapshots older
# than 14 days also forgets their files. .env goes along: its keys (eBay tokens, the storage's
# access key) belong to the database and images, and a new server needs them to restore.
offsite_backup() {
  if [[ -z "$(env_value MB_RESTIC_REPOSITORY)" ]]; then
    echo "Sicherung außer Haus ist nicht eingerichtet und entfällt (./scripts/einrichten.sh sicherung)."
    return 0
  fi
  if [[ ! -r "$OFFSITE_PASSWORD_FILE" ]]; then
    echo "Sicherung außer Haus: $OFFSITE_PASSWORD_FILE fehlt (./scripts/einrichten.sh sicherung)." >&2
    return 1
  fi
  # Removes only locks of runs that died, never those of a running restic.
  offsite_restic unlock --quiet
  offsite_restic backup --host "$OFFSITE_HOST" --tag nacht \
    "$target/datenbank-$stamp.dump" "$target/bilder-$stamp.tar.gz" "$ENV_FILE"
  # Every snapshot holds other file names, so they must not be grouped by path: each would
  # be the latest of its group and stay forever. --max-unused 0 really deletes their data.
  offsite_restic forget --quiet --group-by '' --keep-within "$OFFSITE_KEEP_WITHIN" \
    --prune --max-unused 0
  echo "Außer Haus gesichert; dort bleiben die Sicherungen der letzten 14 Tage."
  if [[ "$(date +%u)" == 7 ]]; then
    offsite_restic check --quiet --read-data-subset 10%
    echo "Sonntagsprobe außer Haus bestanden: 10 % der Daten gelesen und geprüft."
  fi
}

main() {
  echo "Sicherung $stamp beginnt."
  local_backup
  offsite_backup
}

run_log="$(mktemp)"
report() {
  local status=$?
  if (( status == 0 )); then
    tail -n 3 "$run_log" | hc_ping "$ping_url"
  else
    echo "Sicherung $stamp fehlgeschlagen." >&2
    tail -n 20 "$run_log" | hc_ping "$ping_url" /fail
  fi
  rm -f "$run_log"
  exit "$status"
}
trap report EXIT
hc_ping "$ping_url" /start </dev/null
# main runs in its own subshell here; set -e stops it at the first error, and pipefail hands
# its status to this shell, which then stops as well and reports from the EXIT trap.
main 2>&1 | tee "$run_log"
