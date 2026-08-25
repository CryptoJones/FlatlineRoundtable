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
