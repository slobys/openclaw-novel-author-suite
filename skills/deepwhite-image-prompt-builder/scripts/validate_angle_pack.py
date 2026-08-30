#!/usr/bin/env python3
"""Validate independent 9:16 character/creature angle packs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

EIGHT_DIRECTIONS = (
    "front", "front_left_three_quarter", "left_profile", "rear_left_three_quarter",
    "back", "rear_right_three_quarter", "right_profile", "front_right_three_quarter",
)
FULL_PACK_TIERS = {
    "series_core", "recurring", "episode_important", "pet", "companion_creature", "recurring_creature",
}


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


def validate(manifest: dict[str, Any], job: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    packs = manifest.get("packs")
    if not isinstance(packs, list):
        errors.append("angle_pack_manifest.packs 必须为数组"); packs = []
    pack_ids: set[str] = set()
    manifest_assets: dict[str, dict[str, Any]] = {}
    validated = 0
    for pack_index, pack in enumerate(packs):
        if not isinstance(pack, dict):
            errors.append(f"packs[{pack_index}] 必须为 object"); continue
        pack_id = str(pack.get("angle_pack_id") or "")
        subject_id = str(pack.get("subject_id") or "")
        tier = str(pack.get("tier") or "")
        if not pack_id or not subject_id:
            errors.append(f"packs[{pack_index}] 缺少 angle_pack_id/subject_id"); continue
        if pack_id in pack_ids:
            errors.append(f"重复 angle_pack_id：{pack_id}")
        pack_ids.add(pack_id)
        if pack.get("subject_kind") not in {"character", "creature"}:
            errors.append(f"{pack_id}: subject_kind 必须为 character 或 creature")
        required = pack.get("required_angles")
        if not isinstance(required, list) or not required:
            errors.append(f"{pack_id}: required_angles 必须为非空数组"); required = []
        if tier in FULL_PACK_TIERS and tuple(required) != EIGHT_DIRECTIONS:
            errors.append(f"{pack_id}: {tier} 必须按标准顺序提供 8 个方向")
        if len(required) != len(set(required)):
            errors.append(f"{pack_id}: required_angles 存在重复")
        for field in ("identity_fingerprint", "identity_reference_sha256", "style_contract_sha256"):
            if not str(pack.get(field) or "").strip():
                errors.append(f"{pack_id}: 缺少 {field}")
        state_id = str(pack.get("state_id") or "")
        if not state_id:
            errors.append(f"{pack_id}: 缺少 state_id")
        rows = pack.get("assets")
        if not isinstance(rows, list):
            errors.append(f"{pack_id}.assets 必须为数组"); rows = []
        angles: list[str] = []
        local_ids: set[str] = set()
        pack_ok = True
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"{pack_id}.assets[{row_index}] 必须为 object"); pack_ok = False; continue
            asset_id = str(row.get("asset_id") or "")
            angle_id = str(row.get("angle_id") or "")
            if not asset_id or asset_id in local_ids or asset_id in manifest_assets:
                errors.append(f"{pack_id}: asset_id 缺失或重复：{asset_id!r}"); pack_ok = False
            local_ids.add(asset_id); manifest_assets[asset_id] = row
            angles.append(angle_id)
            expected = {
                "angle_pack_id": pack_id,
                "subject_id": subject_id,
                "subject_kind": pack.get("subject_kind"),
                "state_id": state_id,
                "identity_fingerprint": pack.get("identity_fingerprint"),
                "identity_reference_sha256": pack.get("identity_reference_sha256"),
                "style_contract_sha256": pack.get("style_contract_sha256"),
                "aspect_ratio": "9:16",
                "asset_role": "video_reference",
                "layout_type": "single_view_clean",
                "contains_multiple_independent_assets": False,
            }
            for field, value in expected.items():
                if row.get(field) != value:
                    errors.append(f"{asset_id or pack_id}: {field} 必须为 {value!r}"); pack_ok = False
            if not str(row.get("filename") or "").strip():
                errors.append(f"{asset_id or pack_id}: 缺少独立 filename"); pack_ok = False
        if angles != required:
            errors.append(f"{pack_id}: assets 的 angle_id 集合/顺序与 required_angles 不一致"); pack_ok = False
        if pack_ok:
            validated += 1

    job_pack_ids: set[str] = set()
    if job is not None:
        job_assets = job.get("assets")
        if not isinstance(job_assets, list) or not job_assets:
            errors.append("asset job.assets 必须为非空数组"); job_assets = []
        job_asset_map = {str(row.get("asset_id")): row for row in job_assets if isinstance(row, dict) and row.get("asset_id")}
        for row in job_assets:
            if not isinstance(row, dict) or not row.get("angle_pack_id"):
                continue
            job_pack_ids.add(str(row["angle_pack_id"]))
            asset_id = str(row.get("asset_id") or "")
            declared = manifest_assets.get(asset_id)
            if not declared:
                errors.append(f"asset job 的 angle-pack 资产未在 manifest 声明：{asset_id}")
                continue
            for field in (
                "angle_pack_id", "subject_id", "angle_id", "aspect_ratio", "asset_role",
                "layout_type", "contains_multiple_independent_assets", "identity_fingerprint",
                "identity_reference_sha256", "style_contract_sha256", "state_id",
            ):
                if row.get(field) != declared.get(field):
                    errors.append(f"{asset_id}: job.{field} 与 angle-pack manifest 不一致")
        required_job_assets = {
            asset_id for asset_id, row in manifest_assets.items()
            if str(row.get("angle_pack_id")) in job_pack_ids
        }
        missing = sorted(required_job_assets - set(job_asset_map))
        if missing:
            errors.append("asset job 缺少同包角度资产：" + ", ".join(missing))

    passed = not errors
    return {
        "schema_version": "1.0", "passed": passed,
        "pack_count": len(packs), "validated_pack_count": validated,
        "job_angle_pack_ids": sorted(job_pack_ids),
        "errors": errors, "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 DeepWhite 独立多视角资产包")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--job", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        report = validate(load(args.manifest), load(args.job) if args.job else None)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"schema_version": "1.0", "passed": False, "errors": [str(exc)], "warnings": []}
    if args.out:
        atomic_write(args.out.expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
