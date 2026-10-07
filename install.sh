#!/usr/bin/env bash
# Expose FlatlineRoundtable as a Claude Code skill, and put `roundtable` on PATH.
#
# Symlinks rather than copies, so a `git pull` updates the installed skill.
#
#   ./install.sh               install; print the steps if there is no store yet
#   ./install.sh --init        install, and run `roundtable db init` if there is
#                              no store (may prompt for your gpg passphrase)
#   ./install.sh --uninstall   remove the links; the store is left alone
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
SKILL_SRC="${SCRIPT_DIR}/skill"
TARGET="${HOME}/.claude/skills/flatline-roundtable"
BIN_DIR="${HOME}/.local/bin"
BIN_LINK="${BIN_DIR}/roundtable"
STORE="${XDG_DATA_HOME:-${HOME}/.local/share}/flatline-roundtable/roundtable.db"
# PYTHON=python3.11 ./install.sh  for a host whose default python3 is too old
# (pluto: 3.9 by default, 3.11 beside it). roundtable is then installed as a
# two-line wrapper that execs that interpreter, rather than a symlink that
# would run under the old default.
PYTHON="${PYTHON:-python3}"
WRAPPER_MARK="# flatline-roundtable install.sh wrapper"
OLD_YAML="${HOME}/.config/flatline-roundtable/FlatlineRoundtable.yaml"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }

uninstall() {
    for link in "${TARGET}" "${BIN_LINK}"; do
        if [[ -L "${link}" ]] || { [[ -f "${link}" ]] && grep -qF "${WRAPPER_MARK}" "${link}"; }; then
            rm "${link}"; log "Removed ${link}"
        elif [[ -e "${link}" ]]; then
            # Never delete something we did not create.
            die "${link} exists but is not a symlink — refusing to delete it."
        fi
    done
    log "Left ${STORE} alone (your lanes and secrets, your call)."
    exit 0
}

# --init is opt-in: `db init` may create or unlock the DB key in pass, which can
# mean a pinentry prompt, and a plain install must never block on one.
[[ $# -le 1 ]] || die "One argument at most. Usage: ./install.sh [--init | --uninstall]"
INIT=0
case "${1:-}" in
    "")          ;;
    --uninstall) uninstall ;;
    --init)      INIT=1 ;;
    *)           die "Unknown argument: ${1}. Usage: ./install.sh [--init | --uninstall]" ;;
esac

[[ -f "${SKILL_SRC}/SKILL.md" ]]  || die "Missing ${SKILL_SRC}/SKILL.md — repo is incomplete."
[[ -x "${SCRIPT_DIR}/roundtable" ]] || die "Missing or non-executable ${SCRIPT_DIR}/roundtable."
# The floor is 3.11 (the store code and CI assume it). pluto's default python3
# is 3.9 with 3.11 installed beside it, so name the fix rather than just failing.
command -v "${PYTHON}" >/dev/null || die "${PYTHON} not found"
"${PYTHON}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || \
    die "Python 3.11+ required; ${PYTHON} is $("${PYTHON}" -V 2>&1). Rerun with PYTHON=python3.11 ./install.sh"
"${PYTHON}" -c 'import cryptography' 2>/dev/null || \
    die "\`cryptography\` not installed — ${PYTHON} -m pip install --user cryptography (the store needs it)"

# The store (~/.local/share/flatline-roundtable/roundtable.db) is the only
# configuration: lanes, and lane secrets encrypted under a DB key kept in pass.
# It is read before any lane runs, so a broken store stops a run before it
# spends -- a store failure never fails a paid run.
#
# `pass` holds the store's DB key, which unlocks every lane secret. This is a
# warning rather than a hard failure because a roster of only `cli` / `acp`
# lanes rides subscriptions and needs no secret at all. But a lane with any
# `key_entry` will abort at run time without it, so say so now rather than on
# the first real run.
check_pass() {
    local hint_pass hint_gpg
    case "$(uname -s)" in
        Darwin) hint_pass="brew install pass"; hint_gpg="brew install gnupg" ;;
        Linux)  hint_pass="sudo apt install pass   # or dnf/pacman"
                hint_gpg="sudo apt install gnupg  # or dnf/pacman" ;;
        *)      hint_pass="install pass from https://www.passwordstore.org"
                hint_gpg="install GnuPG from https://gnupg.org" ;;
    esac

    if ! command -v gpg >/dev/null 2>&1; then
        log ""
        log "NOTE: gnupg not found. \`pass\` is built on it and cannot work without it."
        log "  ${hint_gpg}"
    fi

    if ! command -v pass >/dev/null 2>&1; then
        log ""
        log "NOTE: \`pass\` not found. It holds the DB key that decrypts the store's"
        log "      secrets; a key value never appears in plaintext, argv, or a"
        log "      transcript. Without pass, any lane carrying a key_entry aborts."
        log "  ${hint_pass}"
        log "  then:  pass init <your-gpg-key-id>"
        log ""
        log "      Subscription-backed cli/acp lanes need no secret and work without it."
        return
    fi

    # Installed but never initialised is the subtler failure: `pass show` exits
    # non-zero for every entry, which reads as "wrong entry name" rather than
    # "no store".
    if ! pass ls >/dev/null 2>&1; then
        log ""
        log "NOTE: \`pass\` is installed but its store is not initialised."
        log "      Every lookup will fail as though the entry name were wrong."
        log "  pass init <your-gpg-key-id>"
    fi
}
check_pass

# --init: run `roundtable db init`, and on failure say exactly what was tried and
# what usually causes it. roundtable's own error is printed above ours as-is.
init_store() {
    local key_src cmd rc
    if [[ -n "${ROUNDTABLE_DB_KEY_FILE:-}" ]]; then
        key_src="key file \$ROUNDTABLE_DB_KEY_FILE=${ROUNDTABLE_DB_KEY_FILE}"
    else
        key_src="pass entry (created, or reused if it already exists)"
        # Fail before db init rather than inside it: without pass there is
        # nowhere to keep the DB key, and the store would be unreadable.
        if ! command -v pass >/dev/null 2>&1; then
            printf 'ERROR: ./install.sh --init cannot create the store.\n' >&2
            printf '  Store path : %s\n' "${STORE}" >&2
            printf '  Problem    : `pass` is not installed, and ROUNDTABLE_DB_KEY_FILE is not set,\n' >&2
            printf '               so there is nowhere to keep the DB key that encrypts lane secrets.\n' >&2
            printf '  Fix        : install pass and gnupg, run `pass init <gpg-key-id>`, then rerun\n' >&2
            printf '               ./install.sh --init  (or set ROUNDTABLE_DB_KEY_FILE for a file key).\n' >&2
            exit 1
        fi
        if ! pass ls >/dev/null 2>&1; then
            printf 'ERROR: ./install.sh --init cannot create the store.\n' >&2
            printf '  Store path : %s\n' "${STORE}" >&2
            printf '  Problem    : `pass` is installed but `pass ls` failed — its store is not\n' >&2
            printf '               initialised, or gpg cannot reach it.\n' >&2
            printf '  Fix        : pass init <gpg-key-id>, then rerun ./install.sh --init\n' >&2
            exit 1
        fi
    fi
    cmd=("${PYTHON}" "${SCRIPT_DIR}/roundtable" db init)
    log "No store yet — creating it."
    log "  Store path : ${STORE}"
    log "  DB key     : ${key_src}"
    log "  Running    : ${cmd[*]}"
    rc=0
    "${cmd[@]}" || rc=$?
    if (( rc != 0 )); then
        printf '\nERROR: roundtable db init failed (exit %s). Its own message is above.\n' "${rc}" >&2
        printf '  Command    : %s\n' "${cmd[*]}" >&2
        printf '  Python     : %s (%s)\n' "$(command -v "${PYTHON}")" "$("${PYTHON}" -V 2>&1)" >&2
        printf '  Store path : %s\n' "${STORE}" >&2
        printf '  DB key     : %s\n' "${key_src}" >&2
        printf '  Common causes:\n' >&2
        printf '    - gpg-agent is locked or pinentry could not prompt (no tty): run\n' >&2
        printf '      `pass show <any entry>` once in this terminal to unlock it, then retry.\n' >&2
        printf '    - the store directory is not writable: check %s\n' "$(dirname -- "${STORE}")" >&2
        printf '    - a half-created store was left behind: inspect it with `roundtable db doctor`\n' >&2
        printf '      before deleting anything; never delete the pass entry holding the DB key.\n' >&2
        printf '  Rerun ./install.sh --init once fixed; it never touches a store that exists.\n' >&2
        exit "${rc}"
    fi
}

mkdir -p "${HOME}/.claude/skills" "${BIN_DIR}"
ln -sfn "${SKILL_SRC}" "${TARGET}";              log "Skill  -> ${TARGET}"
if [[ "${PYTHON}" == python3 ]]; then
    ln -sfn "${SCRIPT_DIR}/roundtable" "${BIN_LINK}"; log "Binary -> ${BIN_LINK}"
else
    [[ -e "${BIN_LINK}" && ! -L "${BIN_LINK}" ]] && ! grep -qF "${WRAPPER_MARK}" "${BIN_LINK}" && \
        die "${BIN_LINK} exists and is not ours — refusing to overwrite it."
    rm -f "${BIN_LINK}"
    printf '#!/bin/sh\n%s\nexec '"'"'%s'"'"' '"'"'%s'"'"' "$@"\n' "${WRAPPER_MARK}" \
        "$(command -v "${PYTHON}")" "${SCRIPT_DIR}/roundtable" > "${BIN_LINK}"
    chmod 755 "${BIN_LINK}"; log "Binary -> ${BIN_LINK} (wrapper: $(command -v "${PYTHON}"))"
fi

if [[ -f "${STORE}" ]]; then
    log "Store found at ${STORE} — left untouched."
else
    log ""
    if (( INIT )); then
        # Only reached with no store; db init also refuses an existing one.
        init_store
        log ""
        log "Store created. It holds no lanes yet; add them:"
    else
        log "No store yet. Create it (or rerun with ./install.sh --init), then add lanes:"
        log "  roundtable db init"
    fi
    if [[ -f "${OLD_YAML}" ]]; then
        log "  roundtable import-yaml ${OLD_YAML} --dry-run      # needs PyYAML, once"
        log "  roundtable import-yaml ${OLD_YAML} --pull-secrets"
        log "  (or, on a host other than makemake: db import makemake's export —"
        log "   see the README's Fleet section)"
    else
        log "  roundtable db import ${SCRIPT_DIR}/examples/roster.example.json"
    fi
fi

case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *) log ""; log "NOTE: ${BIN_DIR} is not on your PATH." ;;
esac
log ""
log "Done. Try: roundtable --list"
