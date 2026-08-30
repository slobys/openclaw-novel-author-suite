#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
PROMPT_PREFIX = "不要出现BGM，不要出现字幕"
BAD_REVIEW_STATES = {"rejected", "failed", "blocked", "invalid", "fail"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_assets(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = None
        for key in ("assets", "actual_assets", "items"):
            if isinstance(payload.get(key), list):
                items = payload[key]
                break
        if items is None:
            raise ValueError("actual_asset_manifest 必须包含 assets 数组")
    else:
        raise ValueError("actual_asset_manifest 必须是 JSON object 或 array")
    result = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"assets[{i}] 必须是 object")
        result.append(item)
    return result


def asset_id_of(asset: Dict[str, Any]) -> str:
    return str(asset.get("asset_id") or "").strip()


def asset_lineage_location_id(asset: Dict[str, Any]) -> str:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    for key in ("source_location_asset_id", "base_location_asset_id", "location_asset_id"):
        value = metadata.get(key)
        if value:
            return str(value)
    for key in ("source_location_asset_id", "base_location_asset_id", "location_asset_id"):
        value = asset.get(key)
        if value:
            return str(value)
    return ""


def review_state_of(asset: Dict[str, Any]) -> str:
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    for key in ("review_status", "qa_status", "status"):
        value = metadata.get(key)
        if value is not None:
            return str(value).strip().lower()
    for key in ("review_status", "qa_status", "status"):
        value = asset.get(key)
        if value is not None:
            return str(value).strip().lower()
    return ""


def validate_job(job: Dict[str, Any], handoff: Dict[str, Any], asset_payload: Any) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    clip_results: List[Dict[str, Any]] = []

    project_id = str(job.get("project_id") or "")
    video_job_id = str(job.get("video_job_id") or "")
    clips = job.get("clips")
    scene_bindings = handoff.get("scene_bindings") if isinstance(handoff, dict) else None

    if not isinstance(scene_bindings, dict):
        errors.append("scene_asset_handoff.scene_bindings 必须是 object")
        scene_bindings = {}
    if handoff.get("gate_passed") is not True:
        errors.append("scene_asset_handoff.gate_passed 不是 true")

    assets = extract_assets(asset_payload)
    asset_index: Dict[str, Dict[str, Any]] = {}
    duplicate_asset_ids: List[str] = []
    for asset in assets:
        aid = asset_id_of(asset)
        if not aid:
            errors.append("actual_asset_manifest 中存在缺少 asset_id 的资产")
            continue
        if aid in asset_index:
            duplicate_asset_ids.append(aid)
        else:
            asset_index[aid] = asset
    if duplicate_asset_ids:
        errors.append("actual_asset_manifest 存在重复 asset_id: " + ", ".join(sorted(set(duplicate_asset_ids))))

    if not isinstance(clips, list) or not clips:
        errors.append("clips 必须是非空数组")
        clips = []
    if len(clips) > 100:
        errors.append("clips 数量不得超过 100")

    clip_ids_seen = set()
    filenames_seen = set()

    counters = {
        "unknown_scene_count": 0,
        "location_id_mismatch_count": 0,
        "sub_location_id_mismatch_count": 0,
        "location_asset_mismatch_count": 0,
        "missing_location_asset_count": 0,
        "missing_reference_asset_count": 0,
        "background_reference_error_count": 0,
        "scene_keyframe_lineage_error_count": 0,
        "basic_schema_error_count": 0,
    }

    for index, clip in enumerate(clips):
        cid = str(clip.get("clip_id") or f"clips[{index}]")
        clip_errors: List[str] = []
        clip_warnings: List[str] = []

        required = (
            "clip_id", "scene_id", "location_id", "sub_location_id",
            "location_asset_id", "background_reference_mode",
            "prompt", "duration", "reference_asset_ids", "filename"
        )
        for key in required:
            if clip.get(key) in (None, ""):
                clip_errors.append(f"缺少必填字段 {key}")

        for key in ("clip_id", "scene_id", "location_id", "sub_location_id", "location_asset_id"):
            value = str(clip.get(key) or "")
            if value and not ID_RE.match(value):
                clip_errors.append(f"{key} 含非法字符: {value}")

        clip_id = str(clip.get("clip_id") or "")
        filename = str(clip.get("filename") or "")
        if clip_id:
            if clip_id in clip_ids_seen:
                clip_errors.append(f"重复 clip_id: {clip_id}")
            clip_ids_seen.add(clip_id)
        if filename:
            if filename in filenames_seen:
                clip_errors.append(f"重复 filename: {filename}")
            filenames_seen.add(filename)

        prompt = str(clip.get("prompt") or "")
        if prompt:
            if len(prompt) > 2200:
                clip_errors.append("prompt 超过 2200 字符")
            if not prompt.startswith(PROMPT_PREFIX):
                clip_errors.append(f"prompt 必须以“{PROMPT_PREFIX}”开头")

        try:
            duration = int(clip.get("duration"))
            if duration < 4 or duration > 15:
                clip_errors.append("duration 必须在 4-15 秒")
        except (TypeError, ValueError):
            clip_errors.append("duration 必须是整数")

        refs = clip.get("reference_asset_ids")
        if not isinstance(refs, list) or not refs:
            clip_errors.append("reference_asset_ids 必须是 1-9 个资产 ID")
            refs = []
        else:
            refs = [str(x) for x in refs]
            if len(refs) > 9:
                clip_errors.append("reference_asset_ids 不得超过 9 个")
            if len(set(refs)) != len(refs):
                clip_errors.append("reference_asset_ids 内存在重复资产")

        missing_refs = [aid for aid in refs if aid not in asset_index]
        if missing_refs:
            counters["missing_reference_asset_count"] += len(missing_refs)
            clip_errors.append("引用资产不存在: " + ", ".join(missing_refs))

        scene_id = str(clip.get("scene_id") or "")
        expected = scene_bindings.get(scene_id)
        if not isinstance(expected, dict):
            counters["unknown_scene_count"] += 1
            clip_errors.append(f"scene_id 不存在于 scene_asset_handoff: {scene_id}")
            expected = None

        if expected:
            expected_location = str(expected.get("location_id") or "")
            expected_sub = str(expected.get("sub_location_id") or "")
            expected_asset = str(expected.get("primary_location_asset_id") or "")
            actual_location = str(clip.get("location_id") or "")
            actual_sub = str(clip.get("sub_location_id") or "")
            actual_asset = str(clip.get("location_asset_id") or "")

            if actual_location != expected_location:
                counters["location_id_mismatch_count"] += 1
                clip_errors.append(f"location_id 不匹配: expected={expected_location}, actual={actual_location}")
            if actual_sub != expected_sub:
                counters["sub_location_id_mismatch_count"] += 1
                clip_errors.append(f"sub_location_id 不匹配: expected={expected_sub}, actual={actual_sub}")
            if actual_asset != expected_asset:
                counters["location_asset_mismatch_count"] += 1
                clip_errors.append(f"location_asset_id 不匹配: expected={expected_asset}, actual={actual_asset}")

            if expected_asset and expected_asset not in asset_index:
                counters["missing_location_asset_count"] += 1
                clip_errors.append(f"权威场景资产不在 actual_asset_manifest: {expected_asset}")

        location_asset_id = str(clip.get("location_asset_id") or "")
        mode = str(clip.get("background_reference_mode") or "")
        if mode == "location_asset":
            if location_asset_id and location_asset_id not in refs:
                counters["background_reference_error_count"] += 1
                clip_errors.append("location_asset 模式下 reference_asset_ids 必须包含 location_asset_id")
            if clip.get("scene_keyframe_asset_id"):
                clip_warnings.append("location_asset 模式存在 scene_keyframe_asset_id；该字段不会作为背景证明")
        elif mode == "scene_keyframe":
            keyframe_id = str(clip.get("scene_keyframe_asset_id") or "")
            if not keyframe_id:
                counters["background_reference_error_count"] += 1
                clip_errors.append("scene_keyframe 模式缺少 scene_keyframe_asset_id")
            elif keyframe_id not in refs:
                counters["background_reference_error_count"] += 1
                clip_errors.append("scene_keyframe_asset_id 必须包含在 reference_asset_ids")
            elif keyframe_id not in asset_index:
                counters["background_reference_error_count"] += 1
                clip_errors.append(f"scene keyframe 不存在于 actual_asset_manifest: {keyframe_id}")
            else:
                keyframe_asset = asset_index[keyframe_id]
                lineage = asset_lineage_location_id(keyframe_asset)
                if lineage != location_asset_id:
                    counters["scene_keyframe_lineage_error_count"] += 1
                    clip_errors.append(
                        f"scene keyframe 场景血缘错误: keyframe={keyframe_id}, lineage={lineage or '<missing>'}, expected={location_asset_id}"
                    )
                state = review_state_of(keyframe_asset)
                if state in BAD_REVIEW_STATES:
                    counters["scene_keyframe_lineage_error_count"] += 1
                    clip_errors.append(f"scene keyframe 审核状态不可用: {keyframe_id} status={state}")
        else:
            counters["background_reference_error_count"] += 1
            clip_errors.append("background_reference_mode 只允许 location_asset 或 scene_keyframe")

        if clip_errors:
            counters["basic_schema_error_count"] += sum(
                1 for e in clip_errors
                if not any(token in e for token in (
                    "scene_id 不存在于", "location_id 不匹配", "sub_location_id 不匹配",
                    "location_asset_id 不匹配", "权威场景资产不在", "引用资产不存在",
                    "模式下", "scene keyframe", "background_reference_mode"
                ))
            )

        clip_results.append({
            "clip_id": cid,
            "scene_id": scene_id,
            "passed": not clip_errors,
            "errors": clip_errors,
            "warnings": clip_warnings,
        })

    valid_clip_count = sum(1 for item in clip_results if item["passed"])
    clip_count = len(clips)
    binding_coverage_ratio = round(valid_clip_count / clip_count, 6) if clip_count else 0.0

    flat_clip_errors = []
    for item in clip_results:
        for err in item["errors"]:
            flat_clip_errors.append(f"{item['clip_id']}: {err}")
    errors.extend(flat_clip_errors)

    gate = {
        "schema_version": "1.0",
        "passed": len(errors) == 0 and clip_count > 0,
        "project_id": project_id,
        "video_job_id": video_job_id,
        "clip_count": clip_count,
        "valid_clip_count": valid_clip_count,
        "binding_coverage_ratio": binding_coverage_ratio,
        "checks": counters,
        "clip_results": clip_results,
        "errors": errors,
        "warnings": warnings,
    }
    return gate


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 DeepWhite 视频片段与场景资产的确定性绑定")
    parser.add_argument("--job", required=True, help="video_job.json")
    parser.add_argument("--scene-handoff", required=True, help="scene_asset_handoff.json")
    parser.add_argument("--assets", required=True, help="actual_asset_manifest.json")
    parser.add_argument("--out", help="输出 video_scene_binding_gate.json")
    args = parser.parse_args()

    try:
        job = load_json(Path(args.job))
        handoff = load_json(Path(args.scene_handoff))
        assets = load_json(Path(args.assets))
        gate = validate_job(job, handoff, assets)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"passed": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2

    rendered = json.dumps(gate, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if gate["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
