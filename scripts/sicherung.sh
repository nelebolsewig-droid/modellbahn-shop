#!/usr/bin/env bash
#
# Nightly backup of the shop on its server (docs/BETRIEB.md, "Sicherung"):
#
#   - the database as a pg_dump in PostgreSQL's custom format, taken while the shop runs;
#   - the object storage (photo originals and image sizes) as a tar archive of Garage's
#     metadata and data. Garage must not write while its metadata is copied, so the storage
#     pauses for the copy; at night only the images of the shop are briefly unavailable.
#
# Keeps BACKUP_KEEP_DAYS days (default 14) in BACKUP_DIR (default /var/backups/modellbahn).
# Copies on this server do not survive the loss of the server: download them regularly.

set -euo pipefail

cd "$(dirname "$0")/.."
target="${BACKUP_DIR:-/var/backups/modellbahn}"
keep_days="${BACKUP_KEEP_DAYS:-14}"
stamp="$(date +%Y%m%d-%H%M)"

umask 077
mkdir -p "$target"

# Written under a temporary name first, so a failed dump never looks like a backup.
docker compose exec -T db sh -c \
  'pg_dump --format=custom --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  > "$target/datenbank-$stamp.dump.part"
mv "$target/datenbank-$stamp.dump.part" "$target/datenbank-$stamp.dump"

storage="$(docker compose ps --all --quiet storage)"
if [[ -z "$storage" ]]; then
  echo "Kein Container für den Bildspeicher (storage) gefunden." >&2
  exit 1
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

echo "Sicherung $stamp fertig: $(du -sh "$target" | cut -f1) in $target"
