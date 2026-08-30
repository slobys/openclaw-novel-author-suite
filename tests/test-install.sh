#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/drama-pipeline-install-test.XXXXXX")"
trap 'rm -rf -- "${TEST_ROOT}"' EXIT

mkdir -p \
  "${TEST_ROOT}/bin" \
  "${TEST_ROOT}/state/workspace-novel-producer/memory" \
  "${TEST_ROOT}/state/workspace-drama-producer/projects/demo"
printf 'private memory\n' > "${TEST_ROOT}/state/workspace-novel-producer/memory/private.md"
printf 'private project\n' > "${TEST_ROOT}/state/workspace-drama-producer/projects/demo/private.txt"
printf 'old agent contract\n' > "${TEST_ROOT}/state/workspace-novel-producer/AGENTS.md"

cat > "${TEST_ROOT}/bin/openclaw" <<'FAKE'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" >> "${FAKE_OPENCLAW_LOG}"
if [[ "$1 $2" == "agents list" ]]; then
  if [[ "${FAKE_AGENTS_EXIST:-0}" == "1" ]]; then
    printf '[{"id":"novel-producer","workspace":"%s"},{"id":"drama-producer","workspace":"%s"}]\n' \
      "${FAKE_NOVEL_WORKSPACE}" "${FAKE_DRAMA_WORKSPACE}"
  else
    printf '[]\n'
  fi
elif [[ "${1:-} ${2:-} ${3:-}" == "gateway restart --help" ]]; then
  printf '%s\n' '--safe'
fi
FAKE
chmod +x "${TEST_ROOT}/bin/openclaw"

export PATH="${TEST_ROOT}/bin:${PATH}"
export HOME="${TEST_ROOT}/home"
export OPENCLAW_STATE_DIR="${TEST_ROOT}/state"
export DRAMA_SUITE_SOURCE_DIR="${REPO_ROOT}"
export FAKE_OPENCLAW_LOG="${TEST_ROOT}/openclaw.log"

bash "${REPO_ROOT}/install.sh"

test -f "${OPENCLAW_STATE_DIR}/workspace-novel-producer/AGENTS.md"
test -f "${OPENCLAW_STATE_DIR}/workspace-drama-producer/AGENTS.md"
test -f "${OPENCLAW_STATE_DIR}/skills/deepwhite-00-novel-series-orchestrator/SKILL.md"
test "$(find "${OPENCLAW_STATE_DIR}/skills" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')" -eq 9
test "$(cat "${OPENCLAW_STATE_DIR}/workspace-novel-producer/memory/private.md")" = 'private memory'
test "$(cat "${OPENCLAW_STATE_DIR}/workspace-drama-producer/projects/demo/private.txt")" = 'private project'
find "${OPENCLAW_STATE_DIR}/backups/drama-pipeline-suite" -path '*/workspace-novel-producer/AGENTS.md' -type f | grep -q .
grep -q 'agents add novel-producer' "${FAKE_OPENCLAW_LOG}"
grep -q 'agents add drama-producer' "${FAKE_OPENCLAW_LOG}"
grep -q 'gateway restart --safe' "${FAKE_OPENCLAW_LOG}"

export FAKE_AGENTS_EXIST=1
export FAKE_NOVEL_WORKSPACE="${OPENCLAW_STATE_DIR}/workspace-novel-producer"
export FAKE_DRAMA_WORKSPACE="${OPENCLAW_STATE_DIR}/workspace-drama-producer"
bash "${REPO_ROOT}/install.sh"

test "$(grep -c 'agents add novel-producer' "${FAKE_OPENCLAW_LOG}")" -eq 1
test "$(grep -c 'agents add drama-producer' "${FAKE_OPENCLAW_LOG}")" -eq 1
if grep -q 'agents.entries' "${FAKE_OPENCLAW_LOG}"; then
  printf 'installer must not write version-specific agent roster paths\n' >&2
  exit 1
fi

printf 'installer test passed\n'

