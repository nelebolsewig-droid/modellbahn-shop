# Shared by the server scripts sicherung.sh, sicherung_pruefen.sh, ueberwachung.sh and
# einrichten.sh (ADR 0025): reading .env without running it, pinging Healthchecks.io and
# reaching the offsite backup on the Hetzner Storage Box. Sourced, not run.
# The constants are used by the scripts that source this file.
# shellcheck shell=bash disable=SC2034

# The offsite backup's access lives with root only, never in the repository or in .env:
# an SSH host alias for the Storage Box (port 23, its own key) and restic's password.
OFFSITE_SSH_ALIAS="modellbahn-sicherung"
OFFSITE_SSH_KEY="/root/.ssh/modellbahn-sicherung"
OFFSITE_PASSWORD_FILE="/root/.config/modellbahn/restic-passwort"
# Snapshots carry this host name, so a new server continues the same history.
OFFSITE_HOST="modellbahn-shop"
# The privacy policy promises that backups are deleted after 14 days; offsite as well.
OFFSITE_KEEP_WITHIN="14d"

# env_value KEY prints KEY's value from ENV_FILE (default .env), or nothing. The file is
# read, not sourced: .env.example has unquoted values with spaces (the IBAN). Undoes the
# single quotes of einrichten.sh's write_env and plain double quotes.
env_value() {
  local file="${ENV_FILE:-.env}" line value sq="'\\''"
  [[ -r "$file" ]] || return 0
  line=$(grep -E "^${1}=" "$file" | tail -n 1) || return 0
  value="${line#*=}"
  if [[ "$value" == \'*\' ]]; then
    value="${value:1:${#value}-2}"
    value="${value//"$sq"/\'}"
  elif [[ "$value" == \"*\" ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

# hc_ping URL [SUFFIX] sends stdin as the body of a ping to Healthchecks.io: no suffix for
# success, /start or /fail. Does nothing without URL; a failed ping is reported, not fatal.
# The URL itself is never printed, since anyone who has it can report for the check.
hc_ping() {
  local url="${1%/}" suffix="${2:-}"
  if [[ -z "$url" ]]; then
    cat >/dev/null
    return 0
  fi
  if ! curl --fail --silent --show-error --max-time 10 --retry 3 --output /dev/null \
    --data-binary @- "$url$suffix"; then
    echo "Meldung an Healthchecks.io ging nicht durch (${suffix:-ok})." >&2
  fi
  return 0
}

# offsite_restic ARGS... runs restic against the repository MB_RESTIC_REPOSITORY in .env.
offsite_restic() {
  RESTIC_REPOSITORY="$(env_value MB_RESTIC_REPOSITORY)" \
    RESTIC_PASSWORD_FILE="$OFFSITE_PASSWORD_FILE" \
    restic "$@"
}
