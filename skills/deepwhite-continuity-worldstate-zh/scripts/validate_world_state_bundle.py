#!/usr/bin/env python3
"""Validate the AUTO_MACHINE_MODE world-state bundle against scene_index.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def add_unique(items: list[str], message: str) -> None:
    if message not in items:
        items.append(message)


def entity_ids(
    data: Any,
    collection: str,
    id_field: str,
    label: str,
    errors: list[str],
) -> set[str]:
    if not isinstance(data, dict) or not isinstance(data.get(collection), list):
        add_unique(errors, f"{label} 顶层必须包含 {collection}[]")
        return set()
    result: set[str] = set()
    for index, row in enumerate(data[collection]):
        if not isinstance(row, dict):
            add_unique(errors, f"{label}.{collection}[{index}] 必须是对象")
            continue
        item_id = row.get(id_field)
        if not isinstance(item_id, str) or not ID_RE.fullmatch(item_id):
            add_unique(errors, f"{label}.{collection}[{index}].{id_field} 必须是稳定 ASCII ID")
            continue
        if item_id in result:
            add_unique(errors, f"{label} 存在重复 ID：{item_id}")
        result.add(item_id)
        if not isinstance(row.get("name"), str) or not row["name"].strip():
            add_unique(errors, f"{label}.{item_id} 缺少 name")
        if not isinstance(row.get("current_state"), dict):
            add_unique(errors, f"{label}.{item_id}.current_state 必须是对象")
        if collection == "characters" and not isinstance(row.get("identity_fingerprint"), dict):
            add_unique(errors, f"{label}.{item_id}.identity_fingerprint 必须是对象")
    return result


def validate(project_root: Path, scene_index_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    paths = {
        "characters": project_root / "world" / "characters.json",
        "locations": project_root / "world" / "locations.json",
        "props": project_root / "world" / "props.json",
        "handoff": project_root / "continuity" / "continuity_handoff.json",
        "scene_index": scene_index_path,
    }
    loaded: dict[str, Any] = {}
    for key, path in paths.items():
        if not path.is_file():
            add_unique(errors, f"缺少文件：{path}")
            continue
        try:
            loaded[key] = read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            add_unique(errors, f"无法读取 {path}：{exc}")
    if errors:
        return {
            "passed": False,
            "scene_coverage_ratio": 0.0,
            "zero_unknown_references": False,
            "errors": errors,
            "warnings": warnings,
        }

    characters = entity_ids(loaded["characters"], "characters", "character_id", "characters.json", errors)
    locations = entity_ids(loaded["locations"], "locations", "location_id", "locations.json", errors)
    props = entity_ids(loaded["props"], "props", "prop_id", "props.json", errors)

    project_ids = {
        str(loaded[key].get("project_id"))
        for key in ("characters", "locations", "props", "handoff", "scene_index")
        if isinstance(loaded[key], dict) and loaded[key].get("project_id")
    }
    if len(project_ids) > 1:
        add_unique(errors, f"project_id 不一致：{sorted(project_ids)}")

    scene_rows = loaded["scene_index"].get("scenes") if isinstance(loaded["scene_index"], dict) else None
    if not isinstance(scene_rows, list) or not scene_rows:
        add_unique(errors, "scene_index.json 缺少 scenes[]")
        expected_scene_ids: list[str] = []
    else:
        expected_scene_ids = []
        for index, row in enumerate(scene_rows):
            scene_id = row.get("scene_id") if isinstance(row, dict) else None
            if not isinstance(scene_id, str) or not ID_RE.fullmatch(scene_id):
                add_unique(errors, f"scene_index.scenes[{index}].scene_id 无效")
                continue
            if scene_id in expected_scene_ids:
                add_unique(errors, f"scene_index 存在重复 Scene：{scene_id}")
            expected_scene_ids.append(scene_id)

    handoff = loaded["handoff"]
    handoff_rows = handoff.get("scenes") if isinstance(handoff, dict) else None
    if not isinstance(handoff_rows, list):
        add_unique(errors, "continuity_handoff.json 缺少 scenes[]")
        handoff_rows = []

    actual_scene_ids: list[str] = []
    unknown_reference_count = 0
    for index, row in enumerate(handoff_rows):
        if not isinstance(row, dict):
            add_unique(errors, f"continuity_handoff.scenes[{index}] 必须是对象")
            continue
        scene_id = row.get("scene_id")
        if not isinstance(scene_id, str) or not ID_RE.fullmatch(scene_id):
            add_unique(errors, f"continuity_handoff.scenes[{index}].scene_id 无效")
            continue
        if scene_id in actual_scene_ids:
            add_unique(errors, f"continuity_handoff 存在重复 Scene：{scene_id}")
        actual_scene_ids.append(scene_id)
        for field in ("state_before", "state_changes", "state_after"):
            if not isinstance(row.get(field), dict):
                add_unique(errors, f"{scene_id}.{field} 必须是对象")
        if not isinstance(row.get("evidence"), list):
            add_unique(errors, f"{scene_id}.evidence 必须是数组")
        character_refs = row.get("character_ids", [])
        prop_refs = row.get("prop_ids", [])
        location_ref = row.get("location_id")
        if not isinstance(character_refs, list) or not isinstance(prop_refs, list):
            add_unique(errors, f"{scene_id} 的 character_ids/prop_ids 必须是数组")
            continue
        for ref in character_refs:
            if ref not in characters:
                unknown_reference_count += 1
                add_unique(errors, f"{scene_id} 引用未知角色：{ref}")
        for ref in prop_refs:
            if ref not in props:
                unknown_reference_count += 1
                add_unique(errors, f"{scene_id} 引用未知道具：{ref}")
        if location_ref not in locations:
            unknown_reference_count += 1
            add_unique(errors, f"{scene_id} 引用未知地点：{location_ref}")

    missing = [item for item in expected_scene_ids if item not in actual_scene_ids]
    unexpected = [item for item in actual_scene_ids if item not in expected_scene_ids]
    if missing:
        add_unique(errors, f"连续性未覆盖 Scene：{missing}")
    if unexpected:
        add_unique(errors, f"连续性包含额外 Scene：{unexpected}")
    if not missing and not unexpected and actual_scene_ids != expected_scene_ids:
        add_unique(errors, "continuity_handoff Scene 顺序必须与 scene_index 一致")

    denominator = len(expected_scene_ids)
    covered = len([item for item in expected_scene_ids if item in actual_scene_ids])
    coverage = round(covered / denominator, 6) if denominator else 0.0
    return {
        "passed": not errors,
        "project_id": next(iter(project_ids), None),
        "scene_count": denominator,
        "covered_scene_count": covered,
        "scene_coverage_ratio": coverage,
        "missing_scene_ids": missing,
        "unexpected_scene_ids": unexpected,
        "zero_unknown_references": unknown_reference_count == 0,
        "unknown_reference_count": unknown_reference_count,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--scene-index", default="script/scene_index.json")
    parser.add_argument("--out")
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    scene_index = Path(args.scene_index)
    if not scene_index.is_absolute():
        scene_index = root / scene_index
    result = validate(root, scene_index)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        output = Path(args.out)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
