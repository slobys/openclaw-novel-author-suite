#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_ROOT="${ROOT}/skills/deepwhite-scene-pack-builder"
TEST_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/scene-pack-test.XXXXXX")"
trap 'rm -rf -- "${TEST_ROOT}"' EXIT

python3 "${SKILL_ROOT}/scripts/scene_state.py" init \
  --root "${TEST_ROOT}" \
  --scene-id SC777 \
  --name test-yard >/dev/null

manifest="${TEST_ROOT}/SC777/scene.json"
python3 "${SKILL_ROOT}/scripts/scene_state.py" validate "${manifest}" >/dev/null
python3 - "${manifest}" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert data["schema_version"] == "3.2.0"
assert data["scene_id"] == "SC777"
assert data["assets"][0]["asset_id"] == "SC777-ST01-F01-v001"
PY

next_asset="$(python3 "${SKILL_ROOT}/scripts/queue_manager.py" "${manifest}" next)"
test "${next_asset}" = "SC777-ST01-F01-v001"

production_manifest="${TEST_ROOT}/production-scene.json"
cp "${SKILL_ROOT}/assets/indoor-multizone-manifest.example.json" "${production_manifest}"
python3 "${SKILL_ROOT}/scripts/scene_state.py" validate "${production_manifest}" --strict >/dev/null
python3 "${SKILL_ROOT}/scripts/scene_state.py" seal "${production_manifest}" >/dev/null
python3 "${SKILL_ROOT}/scripts/scene_state.py" validate "${production_manifest}" --strict >/dev/null

printf 'scene-pack CLI test passed\n'
