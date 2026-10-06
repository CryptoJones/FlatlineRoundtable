#!/usr/bin/env bash
# Expose FlatlineRoundtable as a Claude Code skill, and put `roundtable` on PATH.
#
# Symlinks rather than copies, so a `git pull` updates the installed skill.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
SKILL_SRC="${SCRIPT_DIR}/skill"
TARGET="${HOME}/.claude/skills/flatline-roundtable"
BIN_DIR="${HOME}/.local/bin"
BIN_LINK="${BIN_DIR}/roundtable"
STORE="${XDG_DATA_HOME:-${HOME}/.local/share}/flatline-roundtable/roundtable.db"
OLD_YAML="${HOME}/.config/flatline-roundtable/FlatlineRoundtable.yaml"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }

uninstall() {
    for link in "${TARGET}" "${BIN_LINK}"; do
        if [[ -L "${link}" ]]; then
            rm "${link}"; log "Removed ${link}"
        elif [[ -e "${link}" ]]; then
            # Never delete something we did not create.
            die "${link} exists but is not a symlink — refusing to delete it."
        fi
    done
    log "Left ${STORE} alone (your lanes and secrets, your call)."
    exit 0
}

[[ "${1:-}" == "--uninstall" ]] && uninstall
[[ -n "${1:-}" ]] && die "Unknown argument: ${1}. Usage: ./install.sh [--uninstall]"

[[ -f "${SKILL_SRC}/SKILL.md" ]]  || die "Missing ${SKILL_SRC}/SKILL.md — repo is incomplete."
[[ -x "${SCRIPT_DIR}/roundtable" ]] || die "Missing or non-executable ${SCRIPT_DIR}/roundtable."
# The floor is 3.11 (the store code and CI assume it). pluto's default python3
# is 3.9 with 3.11 installed beside it, so name the fix rather than just failing.
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || \
    die "Python 3.11+ required; python3 is $(python3 -V 2>&1). Put python3.11 first on PATH."
python3 -c 'import cryptography' 2>/dev/null || \
    die "\`cryptography\` not installed — python3 -m pip install --user cryptography (the store needs it)"

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

mkdir -p "${HOME}/.claude/skills" "${BIN_DIR}"
ln -sfn "${SKILL_SRC}" "${TARGET}";              log "Skill  -> ${TARGET}"
ln -sfn "${SCRIPT_DIR}/roundtable" "${BIN_LINK}"; log "Binary -> ${BIN_LINK}"

if [[ -f "${STORE}" ]]; then
    log "Store found at ${STORE} — left untouched."
else
    log ""
    log "No store yet. Create it, then add lanes:"
    log "  roundtable db init"
    if [[ -f "${OLD_YAML}" ]]; then
        log "  roundtable import-yaml ${OLD_YAML} --dry-run      # needs PyYAML, once"
        log "  roundtable import-yaml ${OLD_YAML} --pull-secrets"
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
