#!/usr/bin/env python3
"""Deterministic Scene Asset Plan and route-coverage validator."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_DECISIONS = {
    "reuse_exact", "reuse_compatible", "generate_new_location",
    "generate_new_sublocation", "generate_state_variant",
}
ROUTE_ROLES = {"departure", "path", "turn", "reveal", "arrival"}


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层必须是 JSON object")
    return data


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def safe_id(value: Any, label: str, errors: list[str]) -> str:
    text = str(value or "").strip()
    if not text:
        errors.append(f"{label} 不能为空")
        return ""
    if not SAFE_ID_RE.fullmatch(text):
        errors.append(f"{label} 只能包含字母、数字、下划线和连字符：{text}")
    return text


def duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: set[str] = set()
    for value in values:
        if value in seen:
            result.add(value)
        seen.add(value)
    return sorted(result)


def numeric(value: Any, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def parse_scene_index(scene_index: dict[str, Any] | None, errors: list[str]) -> list[dict[str, Any]]:
    if scene_index is None:
        return []
    rows = scene_index.get("scenes")
    if not isinstance(rows, list) or not rows:
        errors.append("scene_index.scenes 必须为非空数组")
        return []
    result: list[dict[str, Any]] = []
    ids: list[str] = []
    orders: list[int] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"scene_index.scenes[{index}] 必须为 object")
            continue
        sid = safe_id(row.get("scene_id"), f"scene_index.scenes[{index}].scene_id", errors)
        order = row.get("scene_order")
        if not isinstance(order, int) or order < 1:
            errors.append(f"scene_index scene {sid or index}.scene_order 必须为正整数")
        else:
            orders.append(order)
        duration = row.get("expected_duration_seconds")
        if numeric(duration) <= 0:
            errors.append(f"scene_index scene {sid or index}.expected_duration_seconds 必须大于 0")
        if not isinstance(row.get("movement_required"), bool):
            errors.append(f"scene_index scene {sid or index}.movement_required 必须为 boolean")
        ids.append(sid)
        result.append(row)
    for value in duplicates([value for value in ids if value]):
        errors.append(f"scene_index 重复 scene_id：{value}")
    for value in duplicates([str(value) for value in orders]):
        errors.append(f"scene_index 重复 scene_order：{value}")
    if orders and orders != sorted(orders):
        errors.append("scene_index.scenes 必须按 scene_order 升序排列")
    return result


def validate_plan(
    plan: dict[str, Any],
    requirements: dict[str, Any] | None = None,
    scene_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if str(plan.get("schema_version")) not in {"1.0", "1.1"}:
        errors.append("scene_asset_plan.schema_version 必须为 1.0 或 1.1")
    safe_id(plan.get("project_id"), "project_id", errors)
    safe_id(plan.get("episode_project_id"), "episode_project_id", errors)
    safe_id(plan.get("plan_id"), "plan_id", errors)

    scenes = plan.get("scene_bindings")
    assets = plan.get("location_assets")
    locations = plan.get("locations")
    sub_locations = plan.get("sub_locations")
    if not isinstance(scenes, list) or not scenes:
        errors.append("scene_bindings 必须为非空数组"); scenes = []
    if not isinstance(assets, list) or not assets:
        errors.append("location_assets 必须为非空数组"); assets = []
    if not isinstance(locations, list) or not locations:
        errors.append("locations 必须为非空数组"); locations = []
    if not isinstance(sub_locations, list) or not sub_locations:
        errors.append("sub_locations 必须为非空数组"); sub_locations = []

    location_ids: list[str] = []
    for index, row in enumerate(locations):
        if not isinstance(row, dict):
            errors.append(f"locations[{index}] 必须为 object"); continue
        location_ids.append(safe_id(row.get("location_id"), f"locations[{index}].location_id", errors))
        if not str(row.get("canonical_name") or "").strip():
            errors.append(f"locations[{index}].canonical_name 不能为空")
        if not str(row.get("identity_fingerprint") or "").strip():
            errors.append(f"locations[{index}].identity_fingerprint 不能为空")
    for value in duplicates([value for value in location_ids if value]):
        errors.append(f"重复 location_id：{value}")
    location_set = set(location_ids)

    sub_ids: list[str] = []
    sub_to_location: dict[str, str] = {}
    for index, row in enumerate(sub_locations):
        if not isinstance(row, dict):
            errors.append(f"sub_locations[{index}] 必须为 object"); continue
        sid = safe_id(row.get("sub_location_id"), f"sub_locations[{index}].sub_location_id", errors)
        lid = safe_id(row.get("location_id"), f"sub_locations[{index}].location_id", errors)
        sub_ids.append(sid)
        if lid and lid not in location_set:
            errors.append(f"sub_locations[{index}] 引用未知 location_id：{lid}")
        if sid:
            sub_to_location[sid] = lid
        if not str(row.get("identity_fingerprint") or "").strip():
            errors.append(f"sub_locations[{index}].identity_fingerprint 不能为空")
    for value in duplicates([value for value in sub_ids if value]):
        errors.append(f"重复 sub_location_id：{value}")
    sub_set = set(sub_ids)

    asset_ids: list[str] = []
    asset_map: dict[str, dict[str, Any]] = {}
    generation_ids: set[str] = set()
    reuse_ids: set[str] = set()
    for index, row in enumerate(assets):
        if not isinstance(row, dict):
            errors.append(f"location_assets[{index}] 必须为 object"); continue
        aid = safe_id(row.get("asset_id"), f"location_assets[{index}].asset_id", errors)
        lid = safe_id(row.get("location_id"), f"location_assets[{index}].location_id", errors)
        sid = safe_id(row.get("sub_location_id"), f"location_assets[{index}].sub_location_id", errors)
        asset_ids.append(aid)
        if row.get("category") != "location":
            errors.append(f"location_assets[{index}].category 必须为 location")
        if lid and lid not in location_set:
            errors.append(f"location_assets[{index}] 引用未知 location_id：{lid}")
        if sid and sid not in sub_set:
            errors.append(f"location_assets[{index}] 引用未知 sub_location_id：{sid}")
        if sid and sub_to_location.get(sid) and sub_to_location[sid] != lid:
            errors.append(f"location_assets[{index}] 的 location_id 与 sub_location 所属地点不一致")
        decision = str(row.get("decision") or "")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"location_assets[{index}].decision 无效：{decision}")
        generated = row.get("generation_required")
        if not isinstance(generated, bool):
            errors.append(f"location_assets[{index}].generation_required 必须为 boolean")
        elif aid:
            if generated:
                generation_ids.add(aid)
                if decision.startswith("reuse_"):
                    errors.append(f"资产 {aid} 标记需生成但 decision={decision}")
            else:
                reuse_ids.add(aid)
                if not decision.startswith("reuse_"):
                    warnings.append(f"资产 {aid} 不生成但 decision={decision}，请确认来源")
        if not str(row.get("identity_fingerprint") or "").strip():
            errors.append(f"location_assets[{index}].identity_fingerprint 不能为空")
        if aid:
            asset_map[aid] = row
    for value in duplicates([value for value in asset_ids if value]):
        errors.append(f"重复 location asset_id：{value}")

    expected_rows = parse_scene_index(scene_index, errors)
    expected_map = {str(row.get("scene_id")): row for row in expected_rows if row.get("scene_id")}
    expected_ids = list(expected_map)
    if scene_index is None:
        warnings.append("未提供权威 scene_index；仅执行 legacy 输出内一致性校验")

    scene_ids: list[str] = []
    scene_map: dict[str, dict[str, Any]] = {}
    missing_primary = 0
    unknown_primary = 0
    route_anchor_count = 0
    movement_scene_count = 0
    resolved_movement_scene_count = 0
    background_rows: list[tuple[int, str, float, str, bool]] = []
    for index, row in enumerate(scenes):
        if not isinstance(row, dict):
            errors.append(f"scene_bindings[{index}] 必须为 object"); continue
        sid = safe_id(row.get("scene_id"), f"scene_bindings[{index}].scene_id", errors)
        lid = safe_id(row.get("location_id"), f"scene_bindings[{index}].location_id", errors)
        subid = safe_id(row.get("sub_location_id"), f"scene_bindings[{index}].sub_location_id", errors)
        primary = safe_id(row.get("primary_location_asset_id"), f"scene_bindings[{index}].primary_location_asset_id", errors)
        scene_ids.append(sid); scene_map[sid] = row
        if lid and lid not in location_set:
            errors.append(f"scene {sid} 引用未知 location_id：{lid}")
        if subid and subid not in sub_set:
            errors.append(f"scene {sid} 引用未知 sub_location_id：{subid}")
        if subid and sub_to_location.get(subid) and sub_to_location[subid] != lid:
            errors.append(f"scene {sid} 的 location_id 与 sub_location 所属地点不一致")
        if not primary:
            missing_primary += 1
        elif primary not in asset_map:
            unknown_primary += 1; errors.append(f"scene {sid} 的主场景资产不存在：{primary}")
        else:
            asset = asset_map[primary]
            if asset.get("location_id") != lid or asset.get("sub_location_id") != subid:
                errors.append(f"scene {sid} 的主场景资产与 location/sub_location 不一致：{primary}")

        supporting = row.get("supporting_location_asset_ids", [])
        if not isinstance(supporting, list):
            errors.append(f"scene {sid}.supporting_location_asset_ids 必须为数组"); supporting = []
        declared_allowed = row.get("allowed_location_asset_ids")
        if declared_allowed is None:
            declared_allowed = [primary, *supporting]
        if not isinstance(declared_allowed, list) or not declared_allowed:
            errors.append(f"scene {sid}.allowed_location_asset_ids 必须为非空数组"); declared_allowed = []
        allowed = [str(value) for value in declared_allowed if value]
        if primary and primary not in allowed:
            errors.append(f"scene {sid} 的 allowed_location_asset_ids 必须包含 primary")
        if len(allowed) != len(set(allowed)):
            errors.append(f"scene {sid} 的 allowed_location_asset_ids 存在重复")
        for aid in allowed:
            if aid not in asset_map:
                errors.append(f"scene {sid} 引用未知 allowed location asset：{aid}")

        anchors = row.get("route_anchors", [])
        if not isinstance(anchors, list):
            errors.append(f"scene {sid}.route_anchors 必须为数组"); anchors = []
        anchor_ids: list[str] = []
        anchor_orders: list[int] = []
        anchor_roles: list[str] = []
        anchor_assets: list[str] = []
        previous_asset = ""
        for anchor_index, anchor in enumerate(anchors):
            if not isinstance(anchor, dict):
                errors.append(f"scene {sid}.route_anchors[{anchor_index}] 必须为 object"); continue
            anchor_id = safe_id(anchor.get("route_anchor_id"), f"scene {sid}.route_anchor_id", errors)
            role = str(anchor.get("role") or "")
            order = anchor.get("order")
            aid = safe_id(anchor.get("location_asset_id"), f"scene {sid}.route_anchors[{anchor_index}].location_asset_id", errors)
            if role not in ROUTE_ROLES:
                errors.append(f"scene {sid} route anchor {anchor_id} role 无效：{role}")
            if not isinstance(order, int) or order < 1:
                errors.append(f"scene {sid} route anchor {anchor_id}.order 必须为正整数")
            else:
                anchor_orders.append(order)
            if aid and aid not in allowed:
                errors.append(f"scene {sid} route anchor {anchor_id} 使用未授权资产：{aid}")
            predecessor = anchor.get("predecessor_environment_asset_id")
            expected_predecessor = previous_asset or None
            if predecessor != expected_predecessor:
                errors.append(f"scene {sid} route anchor {anchor_id} predecessor 错误：got {predecessor!r}, expected {expected_predecessor!r}")
            previous_asset = aid
            anchor_ids.append(anchor_id); anchor_roles.append(role); anchor_assets.append(aid)
        route_anchor_count += len(anchors)
        for value in duplicates([value for value in anchor_ids if value]):
            errors.append(f"scene {sid} 重复 route_anchor_id：{value}")
        if anchor_orders and anchor_orders != sorted(anchor_orders):
            errors.append(f"scene {sid}.route_anchors 必须按 order 升序")
        if len(anchor_orders) != len(set(anchor_orders)):
            errors.append(f"scene {sid}.route_anchors 存在重复 order")

        expected = expected_map.get(sid, {})
        movement_required = expected.get("movement_required", row.get("movement_required", False))
        duration = numeric(expected.get("expected_duration_seconds"), numeric(row.get("expected_duration_seconds")))
        if expected:
            if row.get("scene_order") != expected.get("scene_order"):
                errors.append(f"scene {sid}.scene_order 与 scene_index 不一致")
            if abs(numeric(row.get("expected_duration_seconds")) - duration) > 1e-9:
                errors.append(f"scene {sid}.expected_duration_seconds 与 scene_index 不一致")
        if movement_required is True:
            movement_scene_count += 1
            minimum = 3 if duration > 12 else 2
            route_rule = expected.get("route_requirements") if isinstance(expected.get("route_requirements"), dict) else {}
            minimum = max(minimum, int(route_rule.get("minimum_anchor_count", minimum)))
            required_roles = set(route_rule.get("required_roles") or ["departure", "arrival"])
            if len(anchors) < minimum:
                errors.append(f"scene {sid} 是移动场次，至少需要 {minimum} 个 route anchors")
            if not required_roles.issubset(set(anchor_roles)):
                errors.append(f"scene {sid} 缺少移动路线角色：{', '.join(sorted(required_roles - set(anchor_roles)))}")
            if len(set(anchor_assets)) < 2:
                errors.append(f"scene {sid} 的移动路线至少需要两个不同环境资产")
            if len(anchors) >= minimum and required_roles.issubset(set(anchor_roles)) and len(set(anchor_assets)) >= 2:
                resolved_movement_scene_count += 1
        order = row.get("scene_order") if isinstance(row.get("scene_order"), int) else index + 1
        background_rows.append((order, primary, duration, sid, len(set(anchor_assets)) > 1))

    duplicate_scenes = duplicates([value for value in scene_ids if value])
    for value in duplicate_scenes:
        errors.append(f"重复 scene binding：{value}")
    planned_ids = [value for value in scene_ids if value]
    if expected_ids:
        missing_scenes = [value for value in expected_ids if value not in scene_map]
        unexpected_scenes = [value for value in planned_ids if value not in expected_map]
        for value in missing_scenes:
            errors.append(f"scene_asset_plan 缺少权威场次：{value}")
        for value in unexpected_scenes:
            errors.append(f"scene_asset_plan 包含 scene_index 未声明场次：{value}")
        denominator = len(expected_ids)
        covered = len(set(expected_ids) & set(planned_ids))
    else:
        missing_scenes = []; unexpected_scenes = []
        denominator = len(planned_ids); covered = len(set(planned_ids))
    coverage_ratio = covered / denominator if denominator else 0.0
    primary_ratio = max(0.0, min(1.0, (denominator - missing_primary - unknown_primary) / denominator)) if denominator else 0.0

    policy = plan.get("policy") if isinstance(plan.get("policy"), dict) else {}
    soft_limit = numeric(policy.get("same_background_soft_limit_seconds"), 24.0)
    hard_limit = numeric(policy.get("same_background_hard_limit_seconds"), 35.0)
    longest_run = 0.0
    current_key = ""; current_duration = 0.0; current_scenes: list[str] = []
    for _, primary, duration, sid, has_route_variety in sorted(background_rows):
        key = f"route:{sid}" if has_route_variety else primary
        if key and key == current_key:
            current_duration += duration; current_scenes.append(sid)
        else:
            longest_run = max(longest_run, current_duration)
            if current_duration > soft_limit:
                label = "、".join(current_scenes)
                if current_duration > hard_limit:
                    errors.append(f"同一背景连续 {current_duration:g}s 超过硬上限 {hard_limit:g}s：{label}")
                elif not all(str((scene_map.get(value) or {}).get("single_location_justification") or "").strip() for value in current_scenes):
                    warnings.append(f"同一背景连续 {current_duration:g}s 超过软上限 {soft_limit:g}s，需记录说明：{label}")
            current_key = key; current_duration = duration; current_scenes = [sid]
    longest_run = max(longest_run, current_duration)
    if current_duration > soft_limit:
        label = "、".join(current_scenes)
        if current_duration > hard_limit:
            errors.append(f"同一背景连续 {current_duration:g}s 超过硬上限 {hard_limit:g}s：{label}")
        elif not all(str((scene_map.get(value) or {}).get("single_location_justification") or "").strip() for value in current_scenes):
            warnings.append(f"同一背景连续 {current_duration:g}s 超过软上限 {soft_limit:g}s，需记录说明：{label}")

    overlap: set[str] = set()
    duplicate_req_ids: list[str] = []
    if requirements is not None:
        reqs = requirements.get("generation_requirements")
        reuses = requirements.get("reuse_assets")
        if not isinstance(reqs, list):
            errors.append("location_asset_requirements.generation_requirements 必须为数组"); reqs = []
        if not isinstance(reuses, list):
            errors.append("location_asset_requirements.reuse_assets 必须为数组"); reuses = []
        req_ids = [safe_id(row.get("asset_id"), f"generation_requirements[{index}].asset_id", errors) for index, row in enumerate(reqs) if isinstance(row, dict)]
        duplicate_req_ids = duplicates([value for value in req_ids if value])
        for value in duplicate_req_ids:
            errors.append(f"重复 generation requirement asset_id：{value}")
        req_set = set(value for value in req_ids if value)
        reuse_req_set = {str(row.get("asset_id")) for row in reuses if isinstance(row, dict) and row.get("asset_id")}
        overlap = req_set & reuse_req_set
        for value in sorted(overlap):
            errors.append(f"资产同时出现在 generation_requirements 和 reuse_assets：{value}")
        for value in sorted(generation_ids - req_set):
            errors.append(f"plan 标记需生成但 requirements 缺失：{value}")
        for value in sorted(req_set - generation_ids):
            errors.append(f"requirements 存在 plan 未标记需生成的资产：{value}")

    planned_scene_count = len(planned_ids)
    summary = plan.get("summary")
    if isinstance(summary, dict):
        if summary.get("scene_count") is not None and summary.get("scene_count") != planned_scene_count:
            errors.append("summary.scene_count 与 scene_bindings 数量不一致")
        if summary.get("scene_coverage_ratio") is not None and numeric(summary.get("scene_coverage_ratio")) != 1.0:
            errors.append("summary.scene_coverage_ratio 必须为 1.0")
        if summary.get("primary_binding_ratio") is not None and numeric(summary.get("primary_binding_ratio")) != 1.0:
            errors.append("summary.primary_binding_ratio 必须为 1.0")

    checks = {
        "authoritative_scene_index_used": scene_index is not None,
        "expected_scene_count": denominator,
        "scene_count_planned": planned_scene_count,
        "unique_scene_count": len(set(planned_ids)),
        "scene_coverage_ratio": round(coverage_ratio, 6),
        "primary_binding_ratio": round(primary_ratio, 6),
        "missing_scene_ids": missing_scenes,
        "unexpected_scene_ids": unexpected_scenes,
        "duplicate_scene_binding_count": len(duplicate_scenes),
        "missing_primary_asset_count": missing_primary,
        "unknown_primary_asset_count": unknown_primary,
        "route_anchor_count": route_anchor_count,
        "movement_scene_count": movement_scene_count,
        "resolved_movement_scene_count": resolved_movement_scene_count,
        "longest_same_background_seconds": round(longest_run, 3),
        "same_background_soft_limit_seconds": soft_limit,
        "same_background_hard_limit_seconds": hard_limit,
        "reuse_generation_overlap_count": len(overlap),
        "duplicate_generation_asset_count": len(duplicate_req_ids),
        "generation_asset_count": len(generation_ids),
        "reuse_asset_count": len(reuse_ids),
    }
    passed = not errors
    return {"schema_version": "1.1", "passed": passed, "ok": passed, "deterministic_checks": checks, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 DeepWhite 场景资产与路线规划")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--requirements")
    parser.add_argument("--scene-index", help="script/scene_index.json；AUTO 模式必须提供")
    parser.add_argument("--gate-out")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        plan = read_json(Path(args.plan).expanduser().resolve())
        requirements = read_json(Path(args.requirements).expanduser().resolve()) if args.requirements else None
        scene_index = read_json(Path(args.scene_index).expanduser().resolve()) if args.scene_index else None
        result = validate_plan(plan, requirements, scene_index)
    except Exception as exc:
        result = {"schema_version": "1.1", "passed": False, "ok": False, "deterministic_checks": {}, "errors": [str(exc)], "warnings": []}
    if args.gate_out:
        atomic_write_json(Path(args.gate_out).expanduser().resolve(), result)
    if args.json or args.gate_out:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["passed"]:
        checks = result["deterministic_checks"]
        print(f"验证通过：{checks['scene_count_planned']} 个场次，{checks['route_anchor_count']} 个路线锚点")
    else:
        print("验证失败：", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
