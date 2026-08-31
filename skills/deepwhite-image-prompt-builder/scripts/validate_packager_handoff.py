#!/usr/bin/env python3
"""Verify PACKAGER_ONLY copied every child asset and hard-lock field verbatim."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HEADINGS = (
    ("style_lock_text", "【STYLE LOCK｜固定原文】"),
    ("scene_or_subject_lock_text", "【SCENE DNA / SUBJECT DNA｜固定原文】"),
    ("spatial_or_structure_lock_text", "【SPATIAL LOCK / STRUCTURE LOCK｜固定原文】"),
    ("continuity_lock_text", "【CONTINUITY LOCK｜固定原文】"),
)
EXACT_FIELDS = (
    "prompt_zh", "lock_id", "lock_hash", "scene_id", "scene_ids", "location_id",
    "sub_location_id", "location_asset_id", "depends_on", "reference_inputs",
    "aspect_ratio", "generation_stage", "filename",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def extract_assets(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    for key in ("assets", "expanded_assets", "children"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def lock_hash(prompt: str) -> str:
    payload: dict[str, str] = {}
    for key, heading in HEADINGS:
        start_at = prompt.find(heading)
        if start_at < 0:
            raise ValueError(f"missing heading: {heading}")
        content_start = start_at + len(heading)
        content_end = len(prompt)
        for _, next_heading in HEADINGS:
            candidate = prompt.find(next_heading, content_start)
            if candidate >= 0:
                content_end = min(content_end, candidate)
        next_any = prompt.find("\n【", content_start)
        if next_any >= 0:
            content_end = min(content_end, next_any)
        value = prompt[content_start:content_end].strip()
        if not value:
            raise ValueError(f"empty lock block: {heading}")
        payload[key] = value
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def validate(expanded: Any, job: Any) -> dict[str, Any]:
    errors: list[str] = []
    upstream_rows = extract_assets(expanded)
    output_rows = extract_assets(job)
    upstream = {str(item.get("asset_id")): item for item in upstream_rows if item.get("asset_id")}
    output = {str(item.get("asset_id")): item for item in output_rows if item.get("asset_id")}
    if len(upstream) != len(upstream_rows):
        errors.append("upstream contains missing or duplicate asset_id")
    if len(output) != len(output_rows):
        errors.append("job contains missing or duplicate asset_id")
    missing = sorted(set(upstream) - set(output))
    unexpected = sorted(set(output) - set(upstream))
    if missing:
        errors.append(f"missing asset_ids: {missing}")
    if unexpected:
        errors.append(f"unexpected asset_ids: {unexpected}")
    for asset_id in sorted(set(upstream) & set(output)):
        source = upstream[asset_id]
        packed = output[asset_id]
        for field in EXACT_FIELDS:
            if packed.get(field) != source.get(field):
                errors.append(f"{asset_id}.{field} changed during PACKAGER_ONLY")
        try:
            expected_hash = lock_hash(str(source.get("prompt_zh", "")))
        except ValueError as exc:
            errors.append(f"{asset_id}: {exc}")
            continue
        if source.get("lock_hash") != expected_hash:
            errors.append(f"{asset_id}.lock_hash does not match upstream prompt; expected {expected_hash}")
        if packed.get("lock_hash") != expected_hash:
            errors.append(f"{asset_id}.lock_hash does not match packed prompt; expected {expected_hash}")
    return {
        "passed": not errors,
        "upstream_asset_count": len(upstream_rows),
        "job_asset_count": len(output_rows),
        "coverage_ratio": round(len(set(upstream) & set(output)) / len(upstream), 6) if upstream else 0.0,
        "missing_asset_ids": missing,
        "unexpected_asset_ids": unexpected,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expanded", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    result = validate(read_json(Path(args.expanded)), read_json(Path(args.job)))
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
