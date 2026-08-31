#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 -m compileall -q \
  "${ROOT}/skills" \
  "${ROOT}/workspaces/novel-producer/scripts" \
  "${ROOT}/workspaces/drama-producer/scripts"

python3 -m unittest discover -s "${ROOT}/workspaces/novel-producer/tests" -p 'test_*.py'
python3 -m unittest discover -s "${ROOT}/workspaces/drama-producer/tests" -p 'test_*.py'
python3 "${ROOT}/skills/deepwhite-scene-pack-builder/scripts/hardlock_selftest.py"
bash "${ROOT}/tests/test-scene-pack.sh"
python3 "${ROOT}/scripts/check-public-release.py"
bash "${ROOT}/tests/test-uninstall.sh"
