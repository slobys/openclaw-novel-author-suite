#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/drama-pipeline-uninstall-test.XXXXXX")"
trap 'rm -rf -- "${TEST_ROOT}"' EXIT

export HOME="${TEST_ROOT}/home"
export OPENCLAW_STATE_DIR="${TEST_ROOT}/state"
mkdir -p \
  "${OPENCLAW_STATE_DIR}/workspace-novel-producer/projects/demo" \
  "${OPENCLAW_STATE_DIR}/workspace-drama-producer/memory" \
  "${OPENCLAW_STATE_DIR}/skills/deepwhite-scene-pack-builder" \
  "${OPENCLAW_STATE_DIR}/skills/deepwhite-n8n-asset-dispatcher"

printf 'project data\n' > "${OPENCLAW_STATE_DIR}/workspace-novel-producer/projects/demo/private.txt"
printf 'memory data\n' > "${OPENCLAW_STATE_DIR}/workspace-drama-producer/memory/private.txt"
printf 'scene skill\n' > "${OPENCLAW_STATE_DIR}/skills/deepwhite-scene-pack-builder/SKILL.md"
printf 'dispatcher skill\n' > "${OPENCLAW_STATE_DIR}/skills/deepwhite-n8n-asset-dispatcher/SKILL.md"

bash "${REPO_ROOT}/uninstall.sh"

test ! -d "${OPENCLAW_STATE_DIR}/skills/deepwhite-scene-pack-builder"
test ! -d "${OPENCLAW_STATE_DIR}/skills/deepwhite-n8n-asset-dispatcher"
test "$(cat "${OPENCLAW_STATE_DIR}/workspace-novel-producer/projects/demo/private.txt")" = 'project data'
test "$(cat "${OPENCLAW_STATE_DIR}/workspace-drama-producer/memory/private.txt")" = 'memory data'
find "${OPENCLAW_STATE_DIR}/backups/drama-pipeline-suite-uninstall" -path '*/deepwhite-scene-pack-builder/SKILL.md' -type f | grep -q .
find "${OPENCLAW_STATE_DIR}/backups/drama-pipeline-suite-uninstall" -path '*/deepwhite-n8n-asset-dispatcher/SKILL.md' -type f | grep -q .

printf 'uninstaller test passed\n'
