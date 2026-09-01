#!/usr/bin/env python3
"""Select the smallest reusable image set that covers declared shot demands."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any


ALLOWED_CATEGORIES = {"location", "scene", "character", "animal", "creature", "prop", "shot"}
ALLOWED_PACK_MODES = {"on_demand", "full"}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} 顶层必须为 JSON object")
    return payload


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def registry_assets(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = registry.get("assets") or {}
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items() if isinstance(value, dict)}
    if isinstance(raw, list):
        return {
            str(row.get("asset_id")): row
            for row in raw
            if isinstance(row, dict) and row.get("asset_id")
        }
    raise ValueError("reference_registry.assets 必须为 object 或 array")


def resolve_asset_demand(intent: dict[str, Any], registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    project_id = str(intent.get("project_id") or "")
    if not project_id:
        raise ValueError("shot_intent_manifest 缺少 project_id")
    demands_raw = intent.get("demands")
    candidates_raw = intent.get("candidates")
    if not isinstance(demands_raw, list) or not isinstance(candidates_raw, list):
        raise ValueError("demands 和 candidates 必须为数组")

    policy = intent.get("policy") or {}
    if not isinstance(policy, dict):
        raise ValueError("policy 必须为 object")
    text_only_risks = {str(value) for value in policy.get("allow_text_only_risk_levels") or ["low"]}
    full_pack_tiers = {str(value) for value in policy.get("full_pack_tiers") or ["series_core"]}

    demands: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, row in enumerate(demands_raw):
        if not isinstance(row, dict):
            errors.append(f"demands[{index}] 必须为 object")
            continue
        demand_id = str(row.get("demand_id") or "")
        shot_ids = row.get("shot_ids")
        category = str(row.get("category") or "")
        if not demand_id or demand_id in demands:
            errors.append(f"demands[{index}] demand_id 缺失或重复：{demand_id!r}")
            continue
        if not isinstance(shot_ids, list) or not shot_ids or any(not str(value) for value in shot_ids):
            errors.append(f"{demand_id}: shot_ids 必须为非空数组")
        if category not in ALLOWED_CATEGORIES:
            errors.append(f"{demand_id}: category 不受支持：{category}")
        demands[demand_id] = row

    candidates: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    for index, row in enumerate(candidates_raw):
        if not isinstance(row, dict):
            errors.append(f"candidates[{index}] 必须为 object")
            continue
        asset_id = str(row.get("asset_id") or "")
        covers = row.get("covers")
        category = str(row.get("category") or "")
        pack_mode = str(row.get("angle_pack_mode") or "on_demand")
        if not asset_id or asset_id in candidate_ids:
            errors.append(f"candidates[{index}] asset_id 缺失或重复：{asset_id!r}")
            continue
        candidate_ids.add(asset_id)
        if not isinstance(covers, list):
            errors.append(f"{asset_id}: covers 必须为数组")
            covers = []
        unknown = sorted({str(value) for value in covers} - set(demands))
        if unknown:
            errors.append(f"{asset_id}: covers 包含未知 demand：{', '.join(unknown)}")
        if category not in ALLOWED_CATEGORIES:
            errors.append(f"{asset_id}: category 不受支持：{category}")
        if pack_mode not in ALLOWED_PACK_MODES:
            errors.append(f"{asset_id}: angle_pack_mode 不受支持：{pack_mode}")
        if pack_mode == "full" and str(row.get("tier") or "") not in full_pack_tiers:
            errors.append(f"{asset_id}: 非完整包等级不得声明 angle_pack_mode=full")
        if pack_mode == "full" and (not row.get("angle_pack_id") or row.get("series_library") is not True):
            errors.append(f"{asset_id}: 完整包资产必须声明 angle_pack_id 和 series_library=true")
        try:
            cost = float(row.get("cost", 1))
            if cost <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{asset_id}: cost 必须为正数")
            cost = 1.0
        candidates.append({**row, "_index": index, "_covers": {str(value) for value in covers}, "_cost": cost})

    if errors:
        return failed_result(project_id, demands, candidates, errors)

    approved = {
        asset_id
        for asset_id, row in registry_assets(registry).items()
        if row.get("status") == "approved"
    }
    decisions: dict[str, dict[str, Any]] = {}
    uncovered: set[str] = set()
    for demand_id, row in demands.items():
        required = row.get("required") is not False
        risk = str(row.get("risk_level") or "high")
        if row.get("allow_text_only") is True and risk in text_only_risks:
            decisions[demand_id] = decision(row, "text_only", [])
        elif required:
            uncovered.add(demand_id)
        else:
            decisions[demand_id] = decision(row, "not_required", [])

    selected: list[dict[str, Any]] = []
    available = list(candidates)
    while uncovered:
        best: dict[str, Any] | None = None
        best_key: tuple[float, int, int] | None = None
        for row in available:
            newly_covered = row["_covers"] & uncovered
            if not newly_covered:
                continue
            asset_id = str(row["asset_id"])
            if row.get("source") == "reuse_only" and asset_id not in approved:
                continue
            reuse = asset_id in approved
            score = math.inf if reuse else len(newly_covered) / row["_cost"]
            key = (score, len(newly_covered), -row["_index"])
            if best_key is None or key > best_key:
                best = row
                best_key = key
        if best is None:
            break
        group = [best]
        if best.get("angle_pack_mode") == "full":
            pack_id = str(best.get("angle_pack_id"))
            group = [
                row for row in available
                if row.get("angle_pack_mode") == "full" and str(row.get("angle_pack_id")) == pack_id
            ]
        selected.extend(group)
        for row in group:
            uncovered -= row["_covers"]
            available.remove(row)

    generation: list[dict[str, Any]] = []
    reuse_assets: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for row in selected:
        asset_id = str(row["asset_id"])
        selected_ids.add(asset_id)
        covered_ids = [demand_id for demand_id in demands if demand_id in row["_covers"]]
        consumer_shots = sorted({
            str(shot_id)
            for demand_id in covered_ids
            for shot_id in demands[demand_id].get("shot_ids") or []
        })
        clean = {key: value for key, value in row.items() if not key.startswith("_") and key != "covers"}
        clean.update({"demand_ids": covered_ids, "consumer_shot_ids": consumer_shots})
        if asset_id in approved:
            clean["selection_reason"] = "approved_registry_reuse"
            reuse_assets.append(clean)
            mode = "reuse"
        else:
            clean["selection_reason"] = "minimum_demand_cover"
            generation.append(clean)
            mode = "generate"
        for demand_id in covered_ids:
            current = decisions.get(demand_id)
            ids = list(current.get("selected_asset_ids") or []) if current else []
            ids.append(asset_id)
            decisions[demand_id] = decision(demands[demand_id], mode, ids)

    missing = sorted(uncovered)
    for demand_id in missing:
        decisions[demand_id] = decision(demands[demand_id], "uncovered", [])
    orphan_generation = sorted(
        row["asset_id"] for row in generation
        if not row.get("consumer_shot_ids") and row.get("series_library") is not True
    )
    required_ids = [key for key, row in demands.items() if row.get("required") is not False]
    covered_required = [key for key in required_ids if decisions.get(key, {}).get("coverage_mode") != "uncovered"]
    ratio = len(covered_required) / len(required_ids) if required_ids else 1.0
    ordered_decisions = [decisions[key] for key in demands]
    gate = {
        "schema_version": "1.0",
        "project_id": project_id,
        "passed": not missing and not orphan_generation,
        "required_demand_count": len(required_ids),
        "covered_required_demand_count": len(covered_required),
        "coverage_ratio": ratio,
        "missing_demand_ids": missing,
        "orphan_generation_asset_ids": orphan_generation,
        "selected_generation_count": len(generation),
        "selected_reuse_count": len(reuse_assets),
        "text_only_count": sum(row["coverage_mode"] == "text_only" for row in ordered_decisions),
        "skipped_candidate_count": len(candidates) - len(selected),
        "errors": [],
    }
    manifest = {
        "schema_version": "1.0",
        "project_id": project_id,
        "source_intent_id": intent.get("intent_id"),
        "policy": policy,
        "generation_requirements": generation,
        "reuse_assets": reuse_assets,
        "text_only_demand_ids": [row["demand_id"] for row in ordered_decisions if row["coverage_mode"] == "text_only"],
        "selected_asset_ids": [row["asset_id"] for row in selected],
        "skipped_candidate_asset_ids": [row["asset_id"] for row in candidates if row["asset_id"] not in selected_ids],
        "metrics": {key: gate[key] for key in (
            "required_demand_count", "coverage_ratio", "selected_generation_count",
            "selected_reuse_count", "text_only_count", "skipped_candidate_count",
        )},
    }
    coverage = {
        "schema_version": "1.0",
        "project_id": project_id,
        "decisions": ordered_decisions,
    }
    return {
        "asset_demand_manifest": manifest,
        "reference_coverage_plan": coverage,
        "asset_demand_gate": gate,
    }


def decision(demand: dict[str, Any], mode: str, asset_ids: list[str]) -> dict[str, Any]:
    return {
        "demand_id": demand.get("demand_id"),
        "shot_ids": list(demand.get("shot_ids") or []),
        "category": demand.get("category"),
        "risk_level": demand.get("risk_level", "high"),
        "coverage_mode": mode,
        "selected_asset_ids": asset_ids,
    }


def failed_result(
    project_id: str,
    demands: dict[str, dict[str, Any]],
    candidates: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    return {
        "asset_demand_manifest": {
            "schema_version": "1.0", "project_id": project_id,
            "generation_requirements": [], "reuse_assets": [],
        },
        "reference_coverage_plan": {"schema_version": "1.0", "project_id": project_id, "decisions": []},
        "asset_demand_gate": {
            "schema_version": "1.0", "project_id": project_id, "passed": False,
            "required_demand_count": sum(row.get("required") is not False for row in demands.values()),
            "covered_required_demand_count": 0, "coverage_ratio": 0.0,
            "missing_demand_ids": sorted(demands), "orphan_generation_asset_ids": [],
            "selected_generation_count": 0, "selected_reuse_count": 0,
            "text_only_count": 0, "skipped_candidate_count": len(candidates), "errors": errors,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="按镜头需求选择最小图片资产集合")
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--manifest-out", required=True, type=Path)
    parser.add_argument("--coverage-out", required=True, type=Path)
    parser.add_argument("--gate-out", required=True, type=Path)
    args = parser.parse_args()
    try:
        intent = load_json(args.intent.expanduser().resolve())
        registry = load_json(args.registry.expanduser().resolve()) if args.registry and args.registry.is_file() else {}
        result = resolve_asset_demand(intent, registry)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    atomic_json(args.manifest_out.expanduser().resolve(), result["asset_demand_manifest"])
    atomic_json(args.coverage_out.expanduser().resolve(), result["reference_coverage_plan"])
    atomic_json(args.gate_out.expanduser().resolve(), result["asset_demand_gate"])
    print(json.dumps(result["asset_demand_gate"], ensure_ascii=False, indent=2))
    return 0 if result["asset_demand_gate"].get("passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
