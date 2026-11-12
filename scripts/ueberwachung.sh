#!/usr/bin/env bash
#
# Checks the shop from its own server, every 5 minutes by cron
# (/etc/cron.d/modellbahn-ueberwachung; docs/BETRIEB.md, "Überwachung"; ADR 0025):
#
#   - the public https://<site>/readyz answers 200: Caddy, API and database are up, and the
#     TLS certificate is valid (curl verifies it, so an expired one fails as well);
#   - neither / nor Docker's data directory is more than DISK_LIMIT_PERCENT full.
#
# The result goes to the check MB_HEALTHCHECK_SHOP_URL at Healthchecks.io: a plain ping when
# all is well, /fail with the reasons in German otherwise. Healthchecks.io mails on /fail and
# when no ping arrives at all, which covers a server that is down altogether.
# Without MB_HEALTHCHECK_SHOP_URL in .env it does nothing.

set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE="$PWD/.env"
# shellcheck source=scripts/gemeinsam.sh
source scripts/gemeinsam.sh

DISK_LIMIT_PERCENT=90
# For the whole request to /readyz, TLS handshake included.
TIMEOUT_SECONDS=20

ping_url="$(env_value MB_HEALTHCHECK_SHOP_URL)"
if [[ -z "$ping_url" ]]; then
  echo "MB_HEALTHCHECK_SHOP_URL ist nicht gesetzt: keine Überwachung (./scripts/einrichten.sh sicherung)."
  exit 0
fi

problems=()
facts=()

# The address customers use, as in the links of the shop's e-mails.
base_url="$(env_value MB_PUBLIC_BASE_URL)"
[[ -n "$base_url" ]] || base_url="https://$(env_value SITE_ADDRESS)"
base_url="${base_url%/}"

check_shop() {
  local code rc=0
  code=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --max-time "$TIMEOUT_SECONDS" "$base_url/readyz") || rc=$?
  case "$rc" in
    0)
      case "$code" in
        200) facts+=("Shop bereit") ;;
        502) problems+=("$base_url: Caddy läuft, erreicht die API aber nicht (HTTP 502).") ;;
        503) problems+=("$base_url: Die API läuft, die Datenbank antwortet nicht (HTTP 503).") ;;
        *) problems+=("$base_url/readyz antwortet mit HTTP $code statt 200.") ;;
      esac
      ;;
    6) problems+=("$base_url: Der Name lässt sich nicht auflösen (DNS).") ;;
    7) problems+=("$base_url: Keine Verbindung, Caddy nimmt nichts an.") ;;
    28) problems+=("$base_url: Keine Antwort innerhalb von $TIMEOUT_SECONDS Sekunden.") ;;
    35 | 51 | 58 | 59 | 60 | 77 | 83 | 90 | 91)
      problems+=("$base_url: HTTPS geht nicht, das Zertifikat ist ungültig oder abgelaufen (curl-Fehler $rc).") ;;
    *) problems+=("$base_url: nicht erreichbar (curl-Fehler $rc).") ;;
  esac
}

declare -A seen_mounts=()

# check_disk PATH: the file system PATH lives on, once per file system.
check_disk() {
  local path="$1" used="" mount=""
  [[ -d "$path" ]] || return 0
  read -r used mount < <(df --output=pcent,target "$path" 2>/dev/null | tail -n 1) || true
  if [[ ! "$used" =~ ^[0-9]+%$ ]]; then
    problems+=("Speicherplatz von $path lässt sich nicht lesen.")
    return 0
  fi
  [[ -n "${seen_mounts[$mount]:-}" ]] && return 0
  seen_mounts[$mount]=1
  used="${used%\%}"
  if (( used > DISK_LIMIT_PERCENT )); then
    problems+=("Speicherplatz: $mount ist zu $used % voll (Grenze $DISK_LIMIT_PERCENT %).")
  else
    facts+=("$mount zu $used % voll")
  fi
}

check_shop
check_disk /
docker_dir="$(timeout 10 docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
check_disk "${docker_dir:-/var/lib/docker}"

if (( ${#problems[@]} )); then
  for problem in "${problems[@]}"; do
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$problem" >&2
  done
  printf '%s\n' "${problems[@]}" | hc_ping "$ping_url" /fail
  exit 1
fi

summary="$(printf '%s; ' "${facts[@]}")"
summary="${summary%; }"
echo "In Ordnung: $summary."
printf '%s\n' "$summary" | hc_ping "$ping_url"
