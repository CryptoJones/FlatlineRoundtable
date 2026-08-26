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
CONFIG_DIR="${HOME}/.config/flatline-roundtable"
CONFIG="${CONFIG_DIR}/FlatlineRoundtable.yaml"

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
    log "Left ${CONFIG} alone (your config, your call)."
    exit 0
}

[[ "${1:-}" == "--uninstall" ]] && uninstall
[[ -n "${1:-}" ]] && die "Unknown argument: ${1}. Usage: ./install.sh [--uninstall]"

[[ -f "${SKILL_SRC}/SKILL.md" ]]  || die "Missing ${SKILL_SRC}/SKILL.md — repo is incomplete."
[[ -x "${SCRIPT_DIR}/roundtable" ]] || die "Missing or non-executable ${SCRIPT_DIR}/roundtable."
python3 -c 'import yaml' 2>/dev/null || die "PyYAML not installed — pip install pyyaml"

# `pass` is how every key reaches a lane: config names an entry, never a value.
# This is a warning rather than a hard failure because a roster of only `cli` /
# `acp` lanes rides subscriptions and needs no secret at all. But a config with
# any `key_entry` will abort at run time without it, so say so now rather than
# on the first real run.
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
        log "NOTE: \`pass\` not found. Lanes name a pass entry via key_entry; a key"
        log "      value never appears in config, argv, or a transcript. Without pass,"
        log "      any lane carrying a key_entry aborts at run time."
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

mkdir -p "${HOME}/.claude/skills" "${BIN_DIR}" "${CONFIG_DIR}"
ln -sfn "${SKILL_SRC}" "${TARGET}";              log "Skill  -> ${TARGET}"
ln -sfn "${SCRIPT_DIR}/roundtable" "${BIN_LINK}"; log "Binary -> ${BIN_LINK}"

if [[ ! -f "${CONFIG}" ]]; then
    log ""
    log "No config yet. Start from the example:"
    log "  cp ${SCRIPT_DIR}/FlatlineRoundtable.yaml.example ${CONFIG}"
    log "  \$EDITOR ${CONFIG}"
else
    log "Config found at ${CONFIG} — left untouched."
fi

case ":${PATH}:" in
    *":${BIN_DIR}:"*) ;;
    *) log ""; log "NOTE: ${BIN_DIR} is not on your PATH." ;;
esac
log ""
log "Done. Try: roundtable --list"
