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
if [[ "${FAKE_OPENCLAW_LEGACY:-0}" == "1" && " $* " == *" --accept-capabilities "* ]]; then
  printf '%s\n' 'OpenClaw does not recognize option "--accept-capabilities".' >&2
  exit 1
fi
if [[ "$1 $2" == "agents list" ]]; then
  if [[ "${FAKE_AGENT_EXISTS:-0}" == "1" ]]; then
    printf '[{"id":"novel-author","workspace":"%s"}]\n' "${FAKE_AGENT_WORKSPACE}"
  else
    printf '[]\n'
  fi
elif [[ "${1:-} ${2:-} ${3:-} ${4:-}" == "config get agents --json" ]]; then
  if [[ -n "${FAKE_AGENT_CONFIG_JSON:-}" ]]; then
    printf '%s\n' "${FAKE_AGENT_CONFIG_JSON}"
  else
    printf '%s\n' '{"entries":{"novel-author":{"tools":{}}}}'
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
export FAKE_AGENT_CONFIG_JSON='{"entries":{"novel-author":{"tools":{}}}}'

bash "${REPO_ROOT}/install.sh"

test -f "${OPENCLAW_STATE_DIR}/workspace-novel-author/AGENTS.md"
grep -q 'V6.1 Balanced-Fast' "${OPENCLAW_STATE_DIR}/workspace-novel-author/AGENTS.md"
test -f "${OPENCLAW_STATE_DIR}/workspace-novel-author/skills/novel-author/scripts/materialize_session_handoff.py"
test "$(cat "${OPENCLAW_STATE_DIR}/workspace-novel-author/memory/private.md")" = 'private memory'
find "${OPENCLAW_STATE_DIR}/backups/novel-author-suite" -name AGENTS.md -type f | grep -q .
grep -q 'plugins install git:github.com/slobys/openclaw-novel-author-suite@v0.6.0 --force --accept-capabilities' "${FAKE_OPENCLAW_LOG}"
grep -q 'plugins enable novel-engine --accept-capabilities' "${FAKE_OPENCLAW_LOG}"
grep -q 'config set agents.entries.novel-author.tools.profile "coding" --strict-json' "${FAKE_OPENCLAW_LOG}"
grep -q 'config set agents.entries.novel-author.tools.alsoAllow .*group:fs.*group:runtime.*read.*write.*edit.*apply_patch.*exec.*process.*novel-engine.*sessions_spawn.*--strict-json' "${FAKE_OPENCLAW_LOG}"
grep -q 'minChapterHanChars 2000 --strict-json' "${FAKE_OPENCLAW_LOG}"
grep -q 'targetChapterHanChars 2600 --strict-json' "${FAKE_OPENCLAW_LOG}"
grep -q 'targetChapterHanCharsMax 3200 --strict-json' "${FAKE_OPENCLAW_LOG}"
grep -q 'gateway restart --safe' "${FAKE_OPENCLAW_LOG}"

export FAKE_AGENT_EXISTS=1
export FAKE_AGENT_WORKSPACE="${OPENCLAW_STATE_DIR}/workspace-novel-author"
export FAKE_OPENCLAW_LEGACY=1
export FAKE_AGENT_CONFIG_JSON='{"entries":{"novel-author":{"tools":{"profile":"full","allow":["novel-engine","sessions_spawn"]}}}}'
bash "${REPO_ROOT}/install.sh"

test "$(grep -c 'agents add novel-author' "${FAKE_OPENCLAW_LOG}")" -eq 1
grep -q '^plugins install git:github.com/slobys/openclaw-novel-author-suite@v0.6.0 --force$' "${FAKE_OPENCLAW_LOG}"
grep -q '^plugins enable novel-engine$' "${FAKE_OPENCLAW_LOG}"
grep -q 'config set agents.entries.novel-author.tools.profile "full" --strict-json' "${FAKE_OPENCLAW_LOG}"
allow_line="$(grep 'config set agents.entries.novel-author.tools.allow ' "${FAKE_OPENCLAW_LOG}" | tail -n 1)"
for required_tool in novel-engine sessions_spawn group:fs group:runtime read write edit apply_patch exec process; do
  grep -Fq "\"${required_tool}\"" <<<"${allow_line}"
done

export FAKE_AGENT_CONFIG_JSON='{"entries":{"novel-author":{"tools":{"profile":"full","allow":["novel-engine"],"deny":["group:runtime"]}}}}'
if bash "${REPO_ROOT}/install.sh" >"${TEST_ROOT}/deny.log" 2>&1; then
  printf 'installer must reject explicit deny conflicts\n' >&2
  exit 1
fi
grep -q 'tools.deny blocks required workspace/runtime tools' "${TEST_ROOT}/deny.log"

printf 'installer test passed\n'
