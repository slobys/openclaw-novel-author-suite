#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

novel_output="$(OPENCLAW_SUITE_SELECTOR_DRY_RUN=1 bash "${ROOT}/setup.sh" 1)"
grep -q 'Selected: 小说创作版' <<<"${novel_output}"
grep -q '/v0.4.5/install.sh' <<<"${novel_output}"

drama_output="$(OPENCLAW_SUITE_SELECTOR_DRY_RUN=1 bash "${ROOT}/setup.sh" 2)"
grep -q 'Selected: 小说转 AI 漫剧版' <<<"${drama_output}"
grep -q '/drama-v1.0.1/install.sh' <<<"${drama_output}"

if OPENCLAW_SUITE_SELECTOR_DRY_RUN=1 bash "${ROOT}/setup.sh" 3 >/dev/null 2>&1; then
  printf 'selector must reject invalid choices\n' >&2
  exit 1
fi

printf 'selector test passed\n'
