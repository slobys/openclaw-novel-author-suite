#!/usr/bin/env python3
"""Validate ordered route-anchor environment continuity before video prompts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

BAD_STATUS = {"rejected", "failed", "blocked", "missing", "invalid"}
REQUIRED_NODE_FIELDS = (
    "route_anchor_id", "role", "location_asset_id", "inherited_location_id",
    "character_position", "camera_position", "camera_view_direction", "route_direction",
    "landmark_ids", "landmark_world_relationships", "expected_screen_position_and_scale",
    "distance_change", "landmark_parallax", "justified_occlusion",
)


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层必须为 object")
    return data


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验路线锚点与环境衔接")
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--spatial", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        handoff = load(args.handoff)
        assets = load(args.assets)
        spatial = load(args.spatial)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    asset_map = {
        str(row.get("asset_id")): row
        for row in assets.get("assets", [])
        if isinstance(row, dict) and row.get("asset_id")
    }
    bindings = handoff.get("scene_bindings")
    if handoff.get("gate_passed") is not True:
        errors.append("scene_asset_handoff.gate_passed must be true")
    if not isinstance(bindings, dict) or not bindings:
        errors.append("scene_asset_handoff.scene_bindings must be non-empty"); bindings = {}
    continuity_map = spatial.get("environment_continuity_map")
    routes = continuity_map.get("routes") if isinstance(continuity_map, dict) else None
    if not isinstance(routes, list):
        errors.append("spatial_blocking.environment_continuity_map.routes must be an array"); routes = []
    route_by_scene: dict[str, dict[str, Any]] = {}
    for route in routes:
        if not isinstance(route, dict) or not route.get("scene_id"):
            errors.append("environment route missing scene_id"); continue
        scene_id = str(route["scene_id"])
        if scene_id in route_by_scene:
            errors.append(f"duplicate environment route for scene {scene_id}")
        route_by_scene[scene_id] = route

    expected_anchor_count = 0
    validated_anchor_count = 0
    for scene_id, binding in bindings.items():
        if not isinstance(binding, dict):
            errors.append(f"scene binding {scene_id} must be object"); continue
        expected = binding.get("route_anchors") or []
        if not expected:
            continue
        expected_anchor_count += len(expected)
        route = route_by_scene.get(str(scene_id))
        if not route:
            errors.append(f"scene {scene_id} missing environment continuity route"); continue
        nodes = route.get("nodes")
        if not isinstance(nodes, list):
            errors.append(f"scene {scene_id} route.nodes must be an array"); continue
        expected_by_id = {str(row.get("route_anchor_id")): row for row in expected if isinstance(row, dict)}
        actual_ids = [str(row.get("route_anchor_id")) for row in nodes if isinstance(row, dict)]
        if actual_ids != list(expected_by_id):
            errors.append(f"scene {scene_id} route anchor order/set does not match handoff")
        previous: dict[str, Any] | None = None
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                errors.append(f"scene {scene_id} nodes[{index}] must be object"); continue
            anchor_id = str(node.get("route_anchor_id") or "")
            source = expected_by_id.get(anchor_id)
            if not source:
                errors.append(f"scene {scene_id} unknown route_anchor_id {anchor_id!r}"); continue
            node_ok = True
            for field in REQUIRED_NODE_FIELDS:
                value = node.get(field)
                if value is None or value == "" or (field == "landmark_ids" and not isinstance(value, list)) or (field == "landmark_world_relationships" and not isinstance(value, dict)):
                    errors.append(f"scene {scene_id} anchor {anchor_id} missing/invalid {field}"); node_ok = False
            for field in ("role", "location_asset_id", "predecessor_environment_asset_id"):
                if node.get(field) != source.get(field):
                    errors.append(f"scene {scene_id} anchor {anchor_id} {field} does not match handoff"); node_ok = False
            if node.get("inherited_location_id") != binding.get("location_id"):
                errors.append(f"scene {scene_id} anchor {anchor_id} inherited_location_id mismatch"); node_ok = False
            asset_id = str(node.get("location_asset_id") or "")
            asset = asset_map.get(asset_id)
            if not asset:
                errors.append(f"scene {scene_id} anchor {anchor_id} asset {asset_id!r} missing"); node_ok = False
            elif str(asset.get("status", "approved")).lower() in BAD_STATUS:
                errors.append(f"scene {scene_id} anchor {anchor_id} asset {asset_id!r} not approved"); node_ok = False
            if previous is not None:
                evidence = node.get("reference_evidence")
                if not isinstance(evidence, dict) or evidence.get("provider_reference_verified") is not True:
                    errors.append(f"scene {scene_id} anchor {anchor_id} lacks verified predecessor reference evidence"); node_ok = False
                elif previous.get("location_asset_id") not in (evidence.get("reference_asset_ids") or []):
                    errors.append(f"scene {scene_id} anchor {anchor_id} reference evidence omits predecessor asset"); node_ok = False
                previous_landmarks = set(previous.get("landmark_ids") or [])
                landmarks = set(node.get("landmark_ids") or [])
                previous_rel = previous.get("landmark_world_relationships") or {}
                relationships = node.get("landmark_world_relationships") or {}
                for landmark in sorted(previous_landmarks & landmarks):
                    if relationships.get(landmark) != previous_rel.get(landmark):
                        errors.append(f"scene {scene_id} anchor {anchor_id} mutates landmark relationship: {landmark}"); node_ok = False
                if previous_landmarks - landmarks and not node.get("justified_occlusion"):
                    errors.append(f"scene {scene_id} anchor {anchor_id} drops landmarks without occlusion/framing reason"); node_ok = False
            if node_ok:
                validated_anchor_count += 1
            previous = node

    unexpected_routes = sorted(set(route_by_scene) - {str(key) for key, value in bindings.items() if isinstance(value, dict) and value.get("route_anchors")})
    if unexpected_routes:
        errors.append("unexpected environment routes: " + ", ".join(unexpected_routes))
    coverage = validated_anchor_count / expected_anchor_count if expected_anchor_count else 1.0
    passed = not errors and coverage == 1.0
    report = {
        "schema_version": "1.0", "passed": passed,
        "expected_route_anchor_count": expected_anchor_count,
        "validated_route_anchor_count": validated_anchor_count,
        "route_anchor_coverage_ratio": round(coverage, 6),
        "unexpected_route_scene_ids": unexpected_routes,
        "errors": errors, "warnings": warnings,
    }
    if args.out:
        atomic_write(args.out.expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
