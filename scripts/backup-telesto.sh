#!/usr/bin/env bash
# One-shot backup of the roundtable store to telesto, with restic (#110).
#
# Runs to completion and exits: a launchd timer starts it (see
# examples/net.thenetwerk.roundtable-backup.plist), which keeps the
# "no long-lived processes" rule in AGENTS.md.
#
# What goes over, and why both halves:
#   * the store's backups dir -- `roundtable db backup` writes an
#     integrity-checked copy there first, so restic never reads a live WAL file;
#   * the gpg-encrypted pass entries under flatline-roundtable/ -- the DB key.
#     Without it a restored store's secrets cannot be decrypted. It is still
#     useless without your gpg private key, which this does not touch.
#
# Override any of these from the environment:
#   RESTIC_REPOSITORY        default sftp:telesto:/NAS/backups/flatline-roundtable/<host>
#   RESTIC_PASSWORD_COMMAND  default pass show flatline-roundtable/restic-telesto
#   KEEP                     local backup copies to keep (default 14)
#   CHECK=1                  run `restic check` now (otherwise Sundays only)
#
# rsync is the fallback if restic is unavailable:
#   rsync -a "$DATA/backups/" telesto:/NAS/backups/flatline-roundtable/<host>/
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
ROUNDTABLE="${SCRIPT_DIR}/../roundtable"
HOST="$(hostname -s)"
DATA="${XDG_DATA_HOME:-${HOME}/.local/share}/flatline-roundtable"
PASS_DIR="${PASSWORD_STORE_DIR:-${HOME}/.password-store}/flatline-roundtable"

export RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-sftp:telesto:/NAS/backups/flatline-roundtable/${HOST}}"
export RESTIC_PASSWORD_COMMAND="${RESTIC_PASSWORD_COMMAND:-pass show flatline-roundtable/restic-telesto}"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }

command -v restic >/dev/null || die "restic is not installed (brew install restic)"
[[ -f "${PASS_DIR}/db-key.gpg" ]] || die "no DB key at ${PASS_DIR}/db-key.gpg — backing up a store without its key is pointless"

log "snapshot the store"
"${ROUNDTABLE}" db backup --keep "${KEEP:-14}"

if ! restic cat config >/dev/null 2>&1; then
    log "initialise ${RESTIC_REPOSITORY}"
    restic init
fi

log "restic backup"
restic backup --quiet --tag flatline-roundtable --host "${HOST}" "${DATA}/backups" "${PASS_DIR}"

log "restic forget"
restic forget --quiet --tag flatline-roundtable --host "${HOST}" \
    --keep-daily 14 --keep-weekly 8 --keep-monthly 6 --prune

if [[ "$(date +%u)" == 7 || "${CHECK:-}" == 1 ]]; then
    log "restic check"
    restic check
fi
log "done"
