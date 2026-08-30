#!/usr/bin/env python3
"""Deterministically validate one-to-one location prompt coverage.

Compares Scene Asset Planner's location_asset_requirements.json against
Image Prompt Builder V2's location_asset_prompt_manifest.json.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return data


def norm_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def build_gate(requirements: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    generation = requirements.get("generation_requirements")
    reuse = requirements.get("reuse_assets")
    assets = manifest.get("assets")

    if not isinstance(generation, list):
        generation = []
        errors.append("generation_requirements must be an array")
    if not isinstance(reuse, list):
        reuse = []
        errors.append("reuse_assets must be an array")
    if not isinstance(assets, list):
        assets = []
        errors.append("manifest.assets must be an array")

    req_ids = [x.get("asset_id") for x in generation if isinstance(x, dict) and x.get("asset_id")]
    out_ids = [x.get("asset_id") for x in assets if isinstance(x, dict) and x.get("asset_id")]
    reuse_ids = [x.get("asset_id") for x in reuse if isinstance(x, dict) and x.get("asset_id")]

    req_counts = Counter(req_ids)
    out_counts = Counter(out_ids)
    duplicate_requirement_ids = sorted([k for k, v in req_counts.items() if v > 1])
    duplicate_output_ids = sorted([k for k, v in out_counts.items() if v > 1])

    req_set = set(req_ids)
    out_set = set(out_ids)
    reuse_set = set(reuse_ids)

    missing = sorted(req_set - out_set)
    unexpected = sorted(out_set - req_set)
    reuse_overlap = sorted(out_set & reuse_set)

    req_by_id = {x.get("asset_id"): x for x in generation if isinstance(x, dict) and x.get("asset_id")}
    out_by_id = {x.get("asset_id"): x for x in assets if isinstance(x, dict) and x.get("asset_id")}

    mismatches: list[dict[str, Any]] = []
    required_metadata_fields = ["scene_ids", "location_id", "sub_location_id", "identity_fingerprint"]

    for asset_id in sorted(req_set & out_set):
        req = req_by_id[asset_id]
        out = out_by_id[asset_id]
        metadata = out.get("metadata") if isinstance(out.get("metadata"), dict) else {}
        fields: list[str] = []

        if out.get("category") != req.get("category"):
            fields.append("category")
        if out.get("name") != req.get("name"):
            fields.append("name")

        for field in required_metadata_fields:
            expected = req.get(field)
            actual = metadata.get(field)
            if field == "scene_ids":
                if sorted(norm_list(actual)) != sorted(norm_list(expected)):
                    fields.append(field)
            elif actual != expected:
                fields.append(field)

        if metadata.get("source_plan_id") != requirements.get("source_plan_id"):
            fields.append("source_plan_id")

        if not isinstance(out.get("prompt_zh"), str) or not out.get("prompt_zh", "").strip():
            fields.append("prompt_zh")
        if not isinstance(out.get("prompt_en"), str) or not out.get("prompt_en", "").strip():
            fields.append("prompt_en")

        expected_filename = f"{asset_id}.png"
        if out.get("filename") != expected_filename:
            fields.append("filename")

        if fields:
            mismatches.append({"asset_id": asset_id, "fields": sorted(set(fields))})

    requirement_count = len(generation)
    output_count = len(assets)
    covered_unique = len(req_set & out_set)
    coverage_ratio = 1.0 if not req_set else round(covered_unique / len(req_set), 6)

    if duplicate_requirement_ids:
        errors.append("duplicate asset_id in generation_requirements")
    if duplicate_output_ids:
        errors.append("duplicate asset_id in manifest.assets")
    if missing:
        errors.append("required prompt assets are missing")
    if unexpected:
        errors.append("manifest contains unplanned assets")
    if reuse_overlap:
        errors.append("reuse assets were incorrectly included in generation manifest")
    if mismatches:
        errors.append("one or more output assets do not preserve required metadata or prompts")
    if requirement_count != output_count:
        errors.append("requirement count and output asset count differ")

    passed = not errors

    return {
        "schema_version": "1.0",
        "project_id": requirements.get("project_id"),
        "episode_project_id": requirements.get("episode_project_id"),
        "source_plan_id": requirements.get("source_plan_id"),
        "passed": passed,
        "requirement_count": requirement_count,
        "output_asset_count": output_count,
        "coverage_ratio": coverage_ratio,
        "missing_asset_ids": missing,
        "unexpected_asset_ids": unexpected,
        "duplicate_requirement_asset_ids": duplicate_requirement_ids,
        "duplicate_output_asset_ids": duplicate_output_ids,
        "metadata_mismatch_count": len(mismatches),
        "metadata_mismatches": mismatches,
        "reuse_overlap_count": len(reuse_overlap),
        "reuse_overlap_asset_ids": reuse_overlap,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--gate-out")
    args = parser.parse_args()

    try:
        requirements = load_json(args.requirements)
        manifest = load_json(args.manifest)
        gate = build_gate(requirements, manifest)
    except Exception as exc:
        gate = {
            "schema_version": "1.0",
            "passed": False,
            "errors": [f"validator exception: {exc}"],
        }

    text = json.dumps(gate, ensure_ascii=False, indent=2)
    print(text)

    if args.gate_out:
        out = Path(args.gate_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")

    return 0 if gate.get("passed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
