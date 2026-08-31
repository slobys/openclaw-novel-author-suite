#!/usr/bin/env bash
set -Eeuo pipefail

SUITE_VERSION="1.2.0"
REPOSITORY="slobys/openclaw-novel-author-suite"
REF="${DRAMA_SUITE_REF:-drama-v${SUITE_VERSION}}"
STATE_DIR="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}"
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-${STATE_DIR}/skills}"
NOVEL_WORKSPACE_OVERRIDE="${NOVEL_PRODUCER_WORKSPACE:-}"
DRAMA_WORKSPACE_OVERRIDE="${DRAMA_PRODUCER_WORKSPACE:-}"
NOVEL_WORKSPACE="${NOVEL_WORKSPACE_OVERRIDE:-${STATE_DIR}/workspace-novel-producer}"
DRAMA_WORKSPACE="${DRAMA_WORKSPACE_OVERRIDE:-${STATE_DIR}/workspace-drama-producer}"
BACKUP_ROOT="${STATE_DIR}/backups/drama-pipeline-suite"
SOURCE_DIR="${DRAMA_SUITE_SOURCE_DIR:-}"
TEMP_DIR=""

log() { printf '[drama-pipeline-suite] %s\n' "$*"; }
die() { printf '[drama-pipeline-suite] ERROR: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"; }

cleanup() {
  if [[ -n "${TEMP_DIR}" && -d "${TEMP_DIR}" ]]; then
    case "${TEMP_DIR}" in
      "${TMPDIR:-/tmp}"/drama-pipeline-suite.*) rm -rf -- "${TEMP_DIR}" ;;
    esac
  fi
}
trap cleanup EXIT

need openclaw
need curl
need tar
need node

agents_json="$(openclaw agents list --json)" || die "Cannot read the OpenClaw agent roster. Run: openclaw config validate"

find_agent_workspace() {
  local agent_id="$1"
  printf '%s' "${agents_json}" | node -e '
    let input = "";
    const wanted = process.argv[1];
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
      const found = agents.find((item) => item && (item.id === wanted || item.agentId === wanted));
      if (found && typeof found.workspace === "string") process.stdout.write(found.workspace);
    });
  ' "${agent_id}"
}

novel_existing="$(find_agent_workspace novel-producer)" || die "Cannot parse novel-producer from the agent roster."
drama_existing="$(find_agent_workspace drama-producer)" || die "Cannot parse drama-producer from the agent roster."
novel_exists=0
drama_exists=0

if [[ -n "${novel_existing}" ]]; then
  novel_exists=1
  if [[ -n "${NOVEL_WORKSPACE_OVERRIDE}" && "${NOVEL_WORKSPACE_OVERRIDE}" != "${novel_existing}" ]]; then
    die "novel-producer already uses ${novel_existing}; NOVEL_PRODUCER_WORKSPACE points to ${NOVEL_WORKSPACE_OVERRIDE}."
  fi
  NOVEL_WORKSPACE="${novel_existing}"
  log "Using existing novel-producer workspace: ${NOVEL_WORKSPACE}"
fi

if [[ -n "${drama_existing}" ]]; then
  drama_exists=1
  if [[ -n "${DRAMA_WORKSPACE_OVERRIDE}" && "${DRAMA_WORKSPACE_OVERRIDE}" != "${drama_existing}" ]]; then
    die "drama-producer already uses ${drama_existing}; DRAMA_PRODUCER_WORKSPACE points to ${DRAMA_WORKSPACE_OVERRIDE}."
  fi
  DRAMA_WORKSPACE="${drama_existing}"
  log "Using existing drama-producer workspace: ${DRAMA_WORKSPACE}"
fi

for target in "${NOVEL_WORKSPACE}" "${DRAMA_WORKSPACE}" "${SKILLS_DIR}"; do
  case "${target}" in
    /|"${HOME}"|"${STATE_DIR}") die "Unsafe install target: ${target}" ;;
  esac
done

if [[ -z "${SOURCE_DIR}" ]]; then
  TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/drama-pipeline-suite.XXXXXX")"
  log "Downloading ${REPOSITORY}@${REF}"
  curl -fsSL "https://github.com/${REPOSITORY}/archive/${REF}.tar.gz" \
    | tar -xz -C "${TEMP_DIR}" --strip-components=1
  SOURCE_DIR="${TEMP_DIR}"
fi

[[ -d "${SOURCE_DIR}/workspaces/novel-producer" ]] || die "novel-producer template not found in ${SOURCE_DIR}"
[[ -d "${SOURCE_DIR}/workspaces/drama-producer" ]] || die "drama-producer template not found in ${SOURCE_DIR}"
[[ -d "${SOURCE_DIR}/skills/deepwhite-00-novel-series-orchestrator" ]] || die "DeepWhite skill chain not found in ${SOURCE_DIR}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT}/${timestamp}"
mkdir -p "${NOVEL_WORKSPACE}" "${DRAMA_WORKSPACE}" "${SKILLS_DIR}" "${backup_dir}"

install_tree() {
  local source_root="$1"
  local target_root="$2"
  local backup_group="$3"
  while IFS= read -r -d '' source_file; do
    local relative="${source_file#${source_root}/}"
    case "/${relative}/" in
      */memory/*|*/projects/*|*/output/*|*/.learnings/*|*/.novel-runtime/*|*/sessions/*|*/__pycache__/*) continue ;;
    esac
    case "${relative}" in
      *.pyc|*.pyo|*.bak*) continue ;;
    esac
    local target_file="${target_root}/${relative}"
    if [[ -f "${target_file}" && ( "${relative}" == "USER.md" || "${relative}" == "HEARTBEAT.md" ) ]]; then
      continue
    fi
    if [[ -f "${target_file}" ]]; then
      mkdir -p "${backup_dir}/${backup_group}/$(dirname "${relative}")"
      cp -p -- "${target_file}" "${backup_dir}/${backup_group}/${relative}"
    fi
    mkdir -p "$(dirname "${target_file}")"
    cp -p -- "${source_file}" "${target_file}"
  done < <(find "${source_root}" -type f -print0)
}

log "Installing novel-producer workspace into ${NOVEL_WORKSPACE}"
install_tree "${SOURCE_DIR}/workspaces/novel-producer" "${NOVEL_WORKSPACE}" "workspace-novel-producer"

log "Installing drama-producer workspace into ${DRAMA_WORKSPACE}"
install_tree "${SOURCE_DIR}/workspaces/drama-producer" "${DRAMA_WORKSPACE}" "workspace-drama-producer"

log "Installing DeepWhite skills into ${SKILLS_DIR}"
while IFS= read -r -d '' skill_root; do
  skill_name="$(basename "${skill_root}")"
  install_tree "${skill_root}" "${SKILLS_DIR}/${skill_name}" "skills/${skill_name}"
done < <(find "${SOURCE_DIR}/skills" -mindepth 1 -maxdepth 1 -type d -print0)

if [[ "${novel_exists}" != "1" ]]; then
  log "Creating novel-producer agent"
  openclaw agents add novel-producer --workspace "${NOVEL_WORKSPACE}" --non-interactive
fi
if [[ "${drama_exists}" != "1" ]]; then
  log "Creating drama-producer agent"
  openclaw agents add drama-producer --workspace "${DRAMA_WORKSPACE}" --non-interactive
fi

openclaw agents set-identity --agent novel-producer --from-identity >/dev/null 2>&1 || true
openclaw agents set-identity --agent drama-producer --from-identity >/dev/null 2>&1 || true
openclaw config validate

if [[ "${DRAMA_SUITE_SKIP_GATEWAY_RESTART:-0}" != "1" ]]; then
  log "Restarting Gateway"
  if openclaw gateway restart --help 2>&1 | grep -q -- '--safe'; then
    openclaw gateway restart --safe
  else
    openclaw gateway restart
  fi
fi

log "Installed Drama Pipeline Suite ${SUITE_VERSION}"
log "Workspace backup: ${backup_dir}"
log "Projects, memory, output and sessions were not modified."
log "Next: configure OPENCLAW_ASSET_SHARED_ROOT and your n8n webhook URLs, then open novel-producer."
