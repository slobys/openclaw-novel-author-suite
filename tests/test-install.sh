#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/novel-author-install-test.XXXXXX")"
trap 'rm -rf -- "${TEST_ROOT}"' EXIT

mkdir -p "${TEST_ROOT}/bin" "${TEST_ROOT}/state/workspace-novel-author/memory"
printf 'private memory\n' > "${TEST_ROOT}/state/workspace-novel-author/memory/private.md"
printf 'old contract\n' > "${TEST_ROOT}/state/workspace-novel-author/AGENTS.md"

cat > "${TEST_ROOT}/bin/openclaw" <<'FAKE'
#!/usr/bin/env bash
set -Eeuo pipefail
printf '%s\n' "$*" >> "${FAKE_OPENCLAW_LOG}"
if [[ "$1 $2" == "agents list" ]]; then
  if [[ "${FAKE_AGENT_EXISTS:-0}" == "1" ]]; then
    printf '[{"id":"novel-author","workspace":"%s"}]\n' "${FAKE_AGENT_WORKSPACE}"
  else
    printf '[]\n'
  fi
elif [[ "${1:-} ${2:-} ${3:-}" == "gateway restart --help" ]]; then
  printf '%s\n' '--safe'
elif [[ "$1 $2" == "plugins inspect" ]]; then
  printf '{"id":"novel-engine","runtime":true}\n'
fi
FAKE
chmod +x "${TEST_ROOT}/bin/openclaw"

export PATH="${TEST_ROOT}/bin:${PATH}"
export HOME="${TEST_ROOT}/home"
export OPENCLAW_STATE_DIR="${TEST_ROOT}/state"
export NOVEL_SUITE_SOURCE_DIR="${REPO_ROOT}"
export FAKE_OPENCLAW_LOG="${TEST_ROOT}/openclaw.log"

bash "${REPO_ROOT}/install.sh"

test -f "${OPENCLAW_STATE_DIR}/workspace-novel-author/AGENTS.md"
grep -q 'V5.3.2' "${OPENCLAW_STATE_DIR}/workspace-novel-author/AGENTS.md"
test "$(cat "${OPENCLAW_STATE_DIR}/workspace-novel-author/memory/private.md")" = 'private memory'
find "${OPENCLAW_STATE_DIR}/backups/novel-author-suite" -name AGENTS.md -type f | grep -q .
grep -q 'plugins install git:github.com/slobys/openclaw-novel-author-suite@v0.4.5 --force' "${FAKE_OPENCLAW_LOG}"
grep -q 'minChapterHanChars 2000 --strict-json' "${FAKE_OPENCLAW_LOG}"
grep -q 'targetChapterHanChars 2600 --strict-json' "${FAKE_OPENCLAW_LOG}"
grep -q 'targetChapterHanCharsMax 3200 --strict-json' "${FAKE_OPENCLAW_LOG}"
grep -q 'gateway restart --safe' "${FAKE_OPENCLAW_LOG}"

export FAKE_AGENT_EXISTS=1
export FAKE_AGENT_WORKSPACE="${OPENCLAW_STATE_DIR}/workspace-novel-author"
bash "${REPO_ROOT}/install.sh"

test "$(grep -c 'agents add novel-author' "${FAKE_OPENCLAW_LOG}")" -eq 1
if grep -q 'agents.entries' "${FAKE_OPENCLAW_LOG}"; then
  printf 'installer must not write version-specific agent roster paths\n' >&2
  exit 1
fi

printf 'installer test passed\n'
