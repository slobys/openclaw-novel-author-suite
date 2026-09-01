#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

novel_output="$(OPENCLAW_SUITE_SELECTOR_DRY_RUN=1 bash "${ROOT}/setup.sh" 1)"
grep -q 'Selected: 安装/更新：小说创作版' <<<"${novel_output}"
grep -q '/v0.4.8/install.sh' <<<"${novel_output}"

drama_output="$(OPENCLAW_SUITE_SELECTOR_DRY_RUN=1 bash "${ROOT}/setup.sh" 2)"
grep -q 'Selected: 安装/更新：小说转 AI 漫剧版' <<<"${drama_output}"
grep -q '/drama-v1.3.0/install.sh' <<<"${drama_output}"

novel_uninstall_output="$(OPENCLAW_SUITE_SELECTOR_DRY_RUN=1 bash "${ROOT}/setup.sh" 3)"
grep -q 'Selected: 安全卸载：小说创作版' <<<"${novel_uninstall_output}"
grep -q '/v0.4.8/uninstall.sh' <<<"${novel_uninstall_output}"

drama_uninstall_output="$(OPENCLAW_SUITE_SELECTOR_DRY_RUN=1 bash "${ROOT}/setup.sh" 4)"
grep -q 'Selected: 安全卸载：小说转 AI 漫剧版' <<<"${drama_uninstall_output}"
grep -q '/drama-v1.3.0/uninstall.sh' <<<"${drama_uninstall_output}"

if OPENCLAW_SUITE_SELECTOR_DRY_RUN=1 bash "${ROOT}/setup.sh" 5 >/dev/null 2>&1; then
  printf 'selector must reject invalid choices\n' >&2
  exit 1
fi

printf 'selector test passed\n'
