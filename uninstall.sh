#!/usr/bin/env bash
set -Eeuo pipefail

STATE_DIR="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}"
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-${STATE_DIR}/skills}"
BACKUP_ROOT="${STATE_DIR}/backups/drama-pipeline-suite-uninstall"
SKILL_NAMES=(
  deepwhite-00-novel-series-orchestrator
  deepwhite-continuity-worldstate-zh
  deepwhite-image-prompt-builder
  deepwhite-n8n-asset-dispatcher
  deepwhite-n8n-video-dispatcher
  deepwhite-scene-asset-planner
  deepwhite-scene-pack-builder
  deepwhite-screenwriting-v1
  deepwhite-shot-transition-builder-zh
  deepwhite-shotlist-builder-zh-user
)

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT}/${timestamp}"
mkdir -p "${backup_dir}"

for name in "${SKILL_NAMES[@]}"; do
  source_dir="${SKILLS_DIR}/${name}"
  if [[ -d "${source_dir}" ]]; then
    mv -- "${source_dir}" "${backup_dir}/${name}"
  fi
done

printf '[drama-pipeline-suite] Skills moved to %s\n' "${backup_dir}"
printf '[drama-pipeline-suite] Agent workspaces, projects, memory, output and sessions were preserved.\n'
printf '[drama-pipeline-suite] Remove the two Agent roster entries manually only if you no longer need them.\n'
