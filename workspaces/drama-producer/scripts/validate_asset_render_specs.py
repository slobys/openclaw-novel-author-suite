#!/usr/bin/env python3
"""Validate per-asset aspect ratio and one-subject/one-view declarations."""

import argparse
import json
import re
import sys
from pathlib import Path


EXPECTED_RATIOS = {
    "character": "9:16",
    "animal": "9:16",
    "creature": "9:16",
    "location": "16:9",
    "environment": "16:9",
    "prop": "9:16",
}

SHA256 = re.compile(r"^[a-f0-9]{64}$")
MAX_REFERENCE_IMAGES = 2


def prompt_section(prompt: str, heading: str) -> str:
    start = prompt.find(heading)
    if start < 0:
        return ""
    remainder = prompt[start + len(heading) :]
    next_heading = re.search(r"\n【[^】]+】", remainder)
    return remainder[: next_heading.start() if next_heading else None].strip()


def semantic_errors(asset_id: str, asset: dict) -> list[str]:
    prompt = str(asset.get("prompt_zh") or asset.get("prompt_en") or "")
    structure = prompt_section(prompt, "【STRUCTURE LOCK｜固定原文】")
    subject = prompt_section(prompt, "【SUBJECT DNA｜固定原文】")
    spatial = prompt_section(prompt, "【SPATIAL LOCK｜固定原文】")
    current = prompt_section(prompt, "【CURRENT ASSET】")
    visible = prompt_section(prompt, "【VISIBLE / OCCLUDED LANDMARKS OR FEATURES】")
    angle = str(asset.get("angle_id") or "").lower()
    name = str(asset.get("name") or "")
    overrides = {str(value).strip().lower() for value in (asset.get("variant_overrides") or [])}
    errors: list[str] = []

    side_or_back = bool(
        re.search(r"side|back|rear|left_90|right_90|135|180|225|270", angle)
        or re.search(r"侧面|侧视|背面|后3/4|后四分之三", name + current)
    )
    if side_or_back and "双耳完整无遮挡" in structure:
        errors.append(f'{asset_id}: PROMPT_CONTRADICTION 侧面/背面视图不得硬锁“双耳完整无遮挡”')

    neutral = bool(re.search(r"neutral|中性", (name + current).lower()))
    dramatic = bool(re.search(r"挑眉|嘴角抽动|大笑|愤怒|惊恐|哭泣", subject + structure))
    excluded = bool(re.search(r"不进入中性|仅属于剧情|中性.*不得", subject + structure))
    if neutral and dramatic and not excluded:
        errors.append(f"{asset_id}: PROMPT_CONTRADICTION 中性基础资产包含剧情表情硬锁")

    forbids_translation = bool(re.search(r"(?:不得|禁止)[^。；\n]{0,60}(?:平移|移动)", spatial))
    requests_translation = bool(re.search(r"平移至|移动至|移到|挪到", current))
    if forbids_translation and requests_translation and "spatial_translation" not in overrides:
        errors.append(
            f'{asset_id}: PROMPT_CONTRADICTION 空间锁禁止平移但当前资产要求平移；'
            '必须删除冲突或声明 variant_overrides=["spatial_translation"]'
        )

    required = re.findall(r"(?:必须|清楚)看见([^；。\n]+)", visible)
    hidden = re.findall(r"([^；。\n]+?)(?:自然不入画|位于摄影机后|完全遮挡)", visible)
    if any(r in h or h in r for r in required for h in hidden):
        errors.append(f"{asset_id}: PROMPT_CONTRADICTION 同一地标同时被要求可见与自然遮挡")
    return errors


def validate_payload(payload: dict) -> list[str]:
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        return ["assets 必须是非空数组"]
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    strict = str(payload.get("schema_version") or "").startswith("2.") or any(
        isinstance(asset, dict) and asset.get("reference_inputs") is not None for asset in assets
    )
    errors: list[str] = []
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            errors.append(f"assets[{index}] 必须是对象")
            continue
        asset_id = asset.get("asset_id") or f"assets[{index}]"
        kind = asset.get("asset_kind")
        role = asset.get("asset_role")
        if kind in EXPECTED_RATIOS:
            expected = EXPECTED_RATIOS[kind]
            if asset.get("aspect_ratio") != expected:
                errors.append(f"{asset_id}: {kind} 必须使用 {expected}")
            if role != "video_reference":
                errors.append(f"{asset_id}: 生产资产 asset_role 必须为 video_reference")
            if asset.get("layout_type") != "single_view_clean":
                errors.append(f"{asset_id}: layout_type 必须为 single_view_clean")
            if not asset.get("angle_id"):
                errors.append(f"{asset_id}: 缺少 angle_id")
            if asset.get("contains_multiple_independent_assets") is not False:
                errors.append(f"{asset_id}: 必须明确不含多个独立资产")
            if kind == "location":
                if not isinstance(asset.get("scene_ids"), list) or not asset.get("scene_ids"):
                    errors.append(f"{asset_id}: location 缺少 scene_ids[]")
                for field in ("location_id", "sub_location_id", "location_asset_id"):
                    if not str(asset.get(field) or "").strip():
                        errors.append(f"{asset_id}: location 缺少 {field}")
        elif role == "video_reference":
            errors.append(f"{asset_id}: video_reference 使用了未知 asset_kind={kind!r}")

        if strict:
            if not str(asset.get("asset_lineage_id") or "").strip():
                errors.append(f"{asset_id}: 缺少 asset_lineage_id")
            if not SHA256.fullmatch(str(asset.get("requirement_sha256") or "")):
                errors.append(f"{asset_id}: requirement_sha256 必须为64位小写SHA256")
            if not str(asset.get("revision_reason_code") or "").strip():
                errors.append(f"{asset_id}: 缺少 revision_reason_code")
            if str(asset.get("acceptance_policy") or "strict_only").lower() != "strict_only":
                errors.append(f"{asset_id}: 连续资产 acceptance_policy 必须为 strict_only")
            if not str(asset.get("lock_id") or "").strip() or not str(asset.get("lock_hash") or "").strip():
                errors.append(f"{asset_id}: 缺少 lock_id/lock_hash")

        direct_refs = asset.get("reference_images") or []
        reference_inputs = asset.get("reference_inputs") or []
        if not isinstance(direct_refs, list):
            errors.append(f"{asset_id}: reference_images 必须是数组")
            direct_refs = []
        if not isinstance(reference_inputs, list):
            errors.append(f"{asset_id}: reference_inputs 必须是数组")
            reference_inputs = []
        required_refs = len(set(map(str, direct_refs)))
        required_refs += len(
            {
                str(row.get("asset_id") or row.get("path"))
                for row in reference_inputs
                if isinstance(row, dict) and row.get("required") is not False
            }
        )
        if required_refs > MAX_REFERENCE_IMAGES:
            errors.append(
                f"{asset_id}: 必需参考图 {required_refs} 张，超过执行分支上限 {MAX_REFERENCE_IMAGES} 张"
            )

        review_retries = asset.get("review_max_retries", defaults.get("review_max_retries", 2))
        try:
            review_retries = int(review_retries)
        except (TypeError, ValueError):
            errors.append(f"{asset_id}: review_max_retries 必须是整数")
        else:
            if not 0 <= review_retries <= 2:
                errors.append(f"{asset_id}: review_max_retries 必须在 0..2，最多对应三次实际生图")
            max_generations = asset.get("max_image_generations", defaults.get("max_image_generations", review_retries + 1))
            try:
                max_generations = int(max_generations)
            except (TypeError, ValueError):
                errors.append(f"{asset_id}: max_image_generations 必须是整数")
            else:
                if max_generations != review_retries + 1 or not 1 <= max_generations <= 3:
                    errors.append(
                        f"{asset_id}: max_image_generations 必须等于 review_max_retries + 1，且不得超过 3"
                    )

        errors.extend(semantic_errors(str(asset_id), asset))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="校验资产单图规格")
    parser.add_argument("--job", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.job.read_text(encoding="utf-8"))
        assets = payload.get("assets")
        errors = validate_payload(payload)
        if errors:
            raise ValueError("资产单图规格 Gate 失败:\n- " + "\n- ".join(errors))
        print(json.dumps({"ok": True, "gate": "asset_render_specs", "asset_count": len(assets)}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
