#!/usr/bin/env bash
set -Eeuo pipefail

SUITE_VERSION="0.4.4"
REPOSITORY="slobys/openclaw-novel-author-suite"
REF="${NOVEL_SUITE_REF:-v${SUITE_VERSION}}"
STATE_DIR="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}"
WORKSPACE_DIR="${NOVEL_AUTHOR_WORKSPACE:-${STATE_DIR}/workspace-novel-author}"
BACKUP_ROOT="${STATE_DIR}/backups/novel-author-suite"
SOURCE_DIR="${NOVEL_SUITE_SOURCE_DIR:-}"
TEMP_DIR=""

log() { printf '[novel-author-suite] %s\n' "$*"; }
die() { printf '[novel-author-suite] ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

cleanup() {
  if [[ -n "${TEMP_DIR}" && -d "${TEMP_DIR}" ]]; then
    case "${TEMP_DIR}" in
      "${TMPDIR:-/tmp}"/novel-author-suite.*) rm -rf -- "${TEMP_DIR}" ;;
    esac
  fi
}
trap cleanup EXIT

need openclaw
need curl
need tar
need git

case "${WORKSPACE_DIR}" in
  /|"${HOME}"|"${STATE_DIR}") die "Unsafe workspace target: ${WORKSPACE_DIR}" ;;
esac

if [[ -z "${SOURCE_DIR}" ]]; then
  TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/novel-author-suite.XXXXXX")"
  log "Downloading ${REPOSITORY}@${REF}"
  curl -fsSL "https://github.com/${REPOSITORY}/archive/${REF}.tar.gz" \
    | tar -xz -C "${TEMP_DIR}" --strip-components=1
  SOURCE_DIR="${TEMP_DIR}"
fi

[[ -f "${SOURCE_DIR}/openclaw.plugin.json" ]] || die "Plugin manifest not found in ${SOURCE_DIR}"
[[ -d "${SOURCE_DIR}/workspace-novel-author" ]] || die "Workspace template not found in ${SOURCE_DIR}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT}/${timestamp}"
mkdir -p "${WORKSPACE_DIR}" "${backup_dir}"

log "Installing workspace into ${WORKSPACE_DIR}"
while IFS= read -r -d '' source_file; do
  relative="${source_file#${SOURCE_DIR}/workspace-novel-author/}"
  case "/${relative}/" in
    */memory/*|*/exports/*|*/.novel-runtime/*|*/__pycache__/*) continue ;;
  esac
  target_file="${WORKSPACE_DIR}/${relative}"
  if [[ -f "${target_file}" ]]; then
    mkdir -p "${backup_dir}/$(dirname "${relative}")"
    cp -p -- "${target_file}" "${backup_dir}/${relative}"
  fi
  mkdir -p "$(dirname "${target_file}")"
  cp -p -- "${source_file}" "${target_file}"
done < <(find "${SOURCE_DIR}/workspace-novel-author" -type f -print0)

plugin_source="${NOVEL_PLUGIN_SOURCE:-git:github.com/${REPOSITORY}@${REF}}"
log "Installing plugin from ${plugin_source}"
openclaw plugins install "${plugin_source}" --force
openclaw plugins enable novel-engine

if openclaw agents list --json 2>/dev/null | grep -Eq '"(id|agentId)"[[:space:]]*:[[:space:]]*"novel-author"'; then
  openclaw config set agents.entries.novel-author.workspace "${WORKSPACE_DIR}"
else
  log "Creating novel-author agent"
  openclaw agents add novel-author --workspace "${WORKSPACE_DIR}" --non-interactive
fi

openclaw agents set-identity --agent novel-author --from-identity >/dev/null 2>&1 || true

log "Applying safe public defaults"
openclaw config set plugins.entries.novel-engine.config.minChapterHanChars 2000 --strict-json
openclaw config set plugins.entries.novel-engine.config.targetChapterHanChars 2600 --strict-json
openclaw config set plugins.entries.novel-engine.config.targetChapterHanCharsMax 3200 --strict-json
openclaw config set plugins.entries.novel-engine.config.requireChapterAudit true --strict-json
openclaw config set plugins.entries.novel-engine.config.requireCompleteAuditChecks true --strict-json
openclaw config set plugins.entries.novel-engine.config.requireQualityGate true --strict-json
openclaw config set plugins.entries.novel-engine.config.requireRevisionAudit true --strict-json
openclaw config set plugins.entries.novel-engine.config.requireRevisionCas true --strict-json
openclaw config set plugins.entries.novel-engine.config.requireClosureReceipt true --strict-json
openclaw config set plugins.entries.novel-engine.config.rejectEmbeddedChapterHeading true --strict-json
openclaw config validate

if [[ "${NOVEL_SKIP_GATEWAY_RESTART:-0}" != "1" ]]; then
  log "Restarting Gateway"
  if openclaw gateway restart --help 2>&1 | grep -q -- '--safe'; then
    openclaw gateway restart --safe
  else
    openclaw gateway restart
  fi
fi

if ! openclaw plugins inspect novel-engine --runtime --json >/dev/null 2>&1; then
  log "Runtime inspection is not ready yet. If restart was deferred, run: openclaw plugins inspect novel-engine --runtime --json"
fi

log "Installed Novel Engine ${SUITE_VERSION} and Novel Author V5.3.2"
log "Workspace backup: ${backup_dir}"
log "Novel data was not modified. Open the novel-author agent to begin."
