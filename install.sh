#!/usr/bin/env bash
set -Eeuo pipefail

SUITE_VERSION="0.4.7"
REPOSITORY="slobys/openclaw-novel-author-suite"
REF="${NOVEL_SUITE_REF:-v${SUITE_VERSION}}"
STATE_DIR="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}"
WORKSPACE_OVERRIDE="${NOVEL_AUTHOR_WORKSPACE:-}"
WORKSPACE_DIR="${WORKSPACE_OVERRIDE:-${STATE_DIR}/workspace-novel-author}"
BACKUP_ROOT="${STATE_DIR}/backups/novel-author-suite"
SOURCE_DIR="${NOVEL_SUITE_SOURCE_DIR:-}"
TEMP_DIR=""

log() { printf '[novel-author-suite] %s\n' "$*"; }
die() { printf '[novel-author-suite] ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

run_with_capability_consent() {
  local command_log status
  command_log="$(mktemp "${TMPDIR:-/tmp}/novel-author-capabilities.XXXXXX")"
  set +e
  "$@" --accept-capabilities 2>&1 | tee "${command_log}"
  status="${PIPESTATUS[0]}"
  set -e
  if [[ "${status}" == "0" ]]; then
    rm -f -- "${command_log}"
    return 0
  fi
  if grep -Eiq '(does not recognize|unrecognized|unknown).*(--accept-capabilities|accept-capabilities)' "${command_log}"; then
    rm -f -- "${command_log}"
    log "This OpenClaw version does not support --accept-capabilities; retrying once with the legacy command."
    "$@"
    return
  fi
  rm -f -- "${command_log}"
  return "${status}"
}

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
need node

if [[ -z "${SOURCE_DIR}" ]]; then
  TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/novel-author-suite.XXXXXX")"
  log "Downloading ${REPOSITORY}@${REF}"
  curl -fsSL "https://github.com/${REPOSITORY}/archive/${REF}.tar.gz" \
    | tar -xz -C "${TEMP_DIR}" --strip-components=1
  SOURCE_DIR="${TEMP_DIR}"
fi

[[ -f "${SOURCE_DIR}/openclaw.plugin.json" ]] || die "Plugin manifest not found in ${SOURCE_DIR}"
[[ -d "${SOURCE_DIR}/workspace-novel-author" ]] || die "Workspace template not found in ${SOURCE_DIR}"

plugin_source="${NOVEL_PLUGIN_SOURCE:-git:github.com/${REPOSITORY}@${REF}}"
log "Installing plugin from ${plugin_source}"
run_with_capability_consent openclaw plugins install "${plugin_source}" --force
run_with_capability_consent openclaw plugins enable novel-engine

# Resolve the Agent roster only after capability consent. OpenClaw 2026.8.1+
# may refuse every other CLI command while an updated plugin is awaiting consent.
agents_json="$(openclaw agents list --json)" || die "Cannot read the OpenClaw agent roster. Run: openclaw config validate"
existing_workspace="$(
  printf '%s' "${agents_json}" | node -e '
    let input = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { input += chunk; });
    process.stdin.on("end", () => {
      const parsed = JSON.parse(input);
      const agents = Array.isArray(parsed)
        ? parsed
        : Array.isArray(parsed.agents)
          ? parsed.agents
          : Array.isArray(parsed.list)
            ? parsed.list
            : [];
      const found = agents.find((item) => item && (item.id === "novel-author" || item.agentId === "novel-author"));
      if (found && typeof found.workspace === "string") process.stdout.write(found.workspace);
    });
  '
)" || die "Cannot parse the OpenClaw agent roster."

agent_exists=0
if [[ -n "${existing_workspace}" ]]; then
  agent_exists=1
  if [[ -n "${WORKSPACE_OVERRIDE}" && "${WORKSPACE_OVERRIDE}" != "${existing_workspace}" ]]; then
    die "novel-author already uses ${existing_workspace}; NOVEL_AUTHOR_WORKSPACE points to ${WORKSPACE_OVERRIDE}."
  fi
  WORKSPACE_DIR="${existing_workspace}"
  log "Using existing novel-author workspace: ${WORKSPACE_DIR}"
fi

case "${WORKSPACE_DIR}" in
  /|"${HOME}"|"${STATE_DIR}") die "Unsafe workspace target: ${WORKSPACE_DIR}" ;;
esac

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

if [[ "${agent_exists}" != "1" ]]; then
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

log "Installed Novel Engine ${SUITE_VERSION} and Novel Author V5.4.0 Balanced-Lite"
log "Workspace backup: ${backup_dir}"
log "Novel data was not modified. Open the novel-author agent to begin."
