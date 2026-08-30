#!/usr/bin/env python3
"""Validate the mandatory scene-bound episode pipeline and emit hashed evidence.

This validator is intentionally independent from the LLM.  It reads the
actual artifacts/gates in one drama-producer episode project and only emits a
passed evidence document when the mandatory scene binding chain is complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PIPELINE_PROFILE = "scene_bound_auto_v1.2"
BAD_STATES = {"rejected", "failed", "blocked", "invalid", "error"}

FIXED_ARTIFACTS = {
    "series_episode_context": "input/series_episode_context.json",
    "pipeline_contract": "input/production_pipeline_contract.json",
    "scene_index": "script/scene_index.json",
    "scene_asset_plan": "assets/scene_asset_plan.json",
    "location_asset_requirements": "assets/location_asset_requirements.json",
    "scene_asset_handoff": "handoffs/scene_asset_handoff.json",
    "location_asset_prompt_manifest": "assets/location_asset_prompt_manifest.json",
    "angle_pack_manifest": "assets/angle_pack_manifest.json",
    "actual_asset_manifest": "assets/actual_asset_manifest.json",
    "spatial_blocking": "shots/spatial_blocking.json",
    "video_prompt_manifest": "video_prompts/video_prompt_manifest.json",
}

FIXED_GATES = {
    "scene_asset_coverage": "gates/scene_asset_coverage_gate.json",
    "location_prompt_manifest": "gates/location_prompt_manifest_gate.json",
    "angle_pack": "gates/angle_pack_gate.json",
    "asset_retry_budget": "gates/asset_retry_budget_gate.json",
    "environment_continuity": "gates/environment_continuity_gate.json",
    "shot_scene_binding": "gates/shot_scene_binding_gate.json",
    "video_prompt_review": "review/video_prompt_gate_review.json",
    "video_scene_binding": "gates/video_scene_binding_gate.json",
}

REQUIRED_GATE_NAMES = tuple(FIXED_GATES)
LEGACY_V12_ARTIFACTS = {
    key: value for key, value in FIXED_ARTIFACTS.items()
    if key not in {"scene_index", "angle_pack_manifest", "spatial_blocking"}
}
LEGACY_V12_GATES = {
    key: value for key, value in FIXED_GATES.items()
    if key not in {"angle_pack", "asset_retry_budget", "environment_continuity"}
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 顶层必须是对象：{path}")
    return data


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"不安全相对路径：{relative}")
    target = (root / rel).resolve()
    target.relative_to(root)
    return target


def ratio_is_one(value: Any) -> bool:
    return isinstance(value, (int, float)) and abs(float(value) - 1.0) < 1e-9


def artifact_record(root: Path, relative: str) -> dict[str, Any]:
    path = safe_path(root, relative)
    if not path.is_file() or path.stat().st_size <= 0:
        raise FileNotFoundError(f"缺少或为空：{relative}")
    return {
        "relative_path": relative,
        "file_size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def gate_passed(name: str, data: dict[str, Any], errors: list[str]) -> bool:
    ok = True
    if name == "scene_asset_coverage":
        checks = data.get("deterministic_checks") if isinstance(data.get("deterministic_checks"), dict) else data
        if data.get("passed") is not True:
            errors.append("scene_asset_coverage.passed != true"); ok = False
        if checks.get("authoritative_scene_index_used") is not True:
            errors.append("scene_asset_coverage.authoritative_scene_index_used != true"); ok = False
        if not ratio_is_one(checks.get("scene_coverage_ratio")):
            errors.append("scene_asset_coverage.scene_coverage_ratio != 1.0"); ok = False
        if not ratio_is_one(checks.get("primary_binding_ratio")):
            errors.append("scene_asset_coverage.primary_binding_ratio != 1.0"); ok = False
    elif name == "location_prompt_manifest":
        if data.get("passed") is not True:
            errors.append("location_prompt_manifest.passed != true"); ok = False
        if not ratio_is_one(data.get("coverage_ratio")):
            errors.append("location_prompt_manifest.coverage_ratio != 1.0"); ok = False
        if data.get("missing_asset_ids") not in ([], None):
            errors.append("location_prompt_manifest 存在 missing_asset_ids"); ok = False
        if data.get("unexpected_asset_ids") not in ([], None):
            errors.append("location_prompt_manifest 存在 unexpected_asset_ids"); ok = False
    elif name == "angle_pack":
        if data.get("passed") is not True:
            errors.append("angle_pack.passed != true"); ok = False
        if data.get("pack_count") != data.get("validated_pack_count"):
            errors.append("angle_pack validated_pack_count 不完整"); ok = False
    elif name == "asset_retry_budget":
        if data.get("passed") is not True:
            errors.append("asset_retry_budget.passed != true"); ok = False
    elif name == "environment_continuity":
        if data.get("passed") is not True:
            errors.append("environment_continuity.passed != true"); ok = False
        if not ratio_is_one(data.get("route_anchor_coverage_ratio")):
            errors.append("environment_continuity.route_anchor_coverage_ratio != 1.0"); ok = False
    elif name == "shot_scene_binding":
        if data.get("passed") is not True:
            errors.append("shot_scene_binding.passed != true"); ok = False
        if data.get("authoritative_scene_index_used") is not True:
            errors.append("shot_scene_binding.authoritative_scene_index_used != true"); ok = False
        for key in ("scene_coverage_ratio", "shot_binding_ratio", "prompt_binding_ratio"):
            if not ratio_is_one(data.get(key)):
                errors.append(f"shot_scene_binding.{key} != 1.0"); ok = False
    elif name == "video_prompt_review":
        if data.get("ready_for_video_prompt_generation") is not True:
            errors.append("video_prompt_review.ready_for_video_prompt_generation != true"); ok = False
        gates = data.get("gates")
        if isinstance(gates, dict):
            for gate_name, gate in gates.items():
                if isinstance(gate, dict) and str(gate.get("status", "")).lower() in BAD_STATES | {"pending"}:
                    errors.append(f"video_prompt_review.gates.{gate_name} 未通过"); ok = False
    elif name == "video_scene_binding":
        if data.get("passed") is not True:
            errors.append("video_scene_binding.passed != true"); ok = False
        if not ratio_is_one(data.get("binding_coverage_ratio")):
            errors.append("video_scene_binding.binding_coverage_ratio != 1.0"); ok = False
    return ok


def validate_project(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    artifact_records: dict[str, Any] = {}
    gate_records: dict[str, Any] = {}
    loaded_artifacts: dict[str, dict[str, Any]] = {}
    loaded_gates: dict[str, dict[str, Any]] = {}

    # Existing in-flight v1.2 contracts remain verifiable with their original
    # five gates. Only newly dispatched schema 1.3 contracts require the new
    # safety artifacts/gates.
    contract_probe = safe_path(root, "input/production_pipeline_contract.json")
    contract_schema = None
    if contract_probe.is_file():
        try:
            contract_schema = str(load_json(contract_probe).get("schema_version") or "")
        except Exception:
            contract_schema = None
    legacy_v12 = contract_schema == "1.2"
    artifact_spec = LEGACY_V12_ARTIFACTS if legacy_v12 else FIXED_ARTIFACTS
    gate_spec = LEGACY_V12_GATES if legacy_v12 else FIXED_GATES
    required_gate_names = tuple(gate_spec)

    for name, relative in artifact_spec.items():
        try:
            record = artifact_record(root, relative)
            artifact_records[name] = record
            loaded_artifacts[name] = load_json(safe_path(root, relative))
        except Exception as exc:
            errors.append(f"artifact {name}: {exc}")

    episode_project_id = None
    context = loaded_artifacts.get("series_episode_context")
    if context:
        episode_project_id = context.get("episode_project_id")
        pipeline = context.get("production_pipeline") or {}
        if pipeline.get("pipeline_profile") != PIPELINE_PROFILE:
            errors.append("series_episode_context.production_pipeline.pipeline_profile 不匹配")
        if pipeline.get("require_pipeline_evidence") is not True:
            errors.append("series_episode_context 未要求 pipeline evidence")

    contract = loaded_artifacts.get("pipeline_contract")
    if contract:
        stored_contract_sha = str(contract.get("contract_sha256") or "").lower()
        unsigned_contract = dict(contract)
        unsigned_contract.pop("contract_sha256", None)
        encoded = json.dumps(unsigned_contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        actual_contract_sha = hashlib.sha256(encoded).hexdigest()
        if not stored_contract_sha or stored_contract_sha != actual_contract_sha:
            errors.append("production_pipeline_contract.contract_sha256 校验失败")
        if contract.get("pipeline_profile") != PIPELINE_PROFILE:
            errors.append("production_pipeline_contract.pipeline_profile 不匹配")
        if contract.get("require_pipeline_evidence") is not True:
            errors.append("production_pipeline_contract.require_pipeline_evidence != true")
        required = contract.get("required_gates")
        if not isinstance(required, list) or set(required_gate_names) - {str(x) for x in required}:
            errors.append("production_pipeline_contract.required_gates 不完整")
        if episode_project_id and contract.get("episode_project_id") != episode_project_id:
            errors.append("production_pipeline_contract.episode_project_id 与 context 不一致")

    handoff = loaded_artifacts.get("scene_asset_handoff")
    if handoff:
        if handoff.get("gate_passed") is not True:
            errors.append("scene_asset_handoff.gate_passed != true")
        bindings = handoff.get("scene_bindings")
        if not isinstance(bindings, dict) or not bindings:
            errors.append("scene_asset_handoff.scene_bindings 为空")
        if episode_project_id and handoff.get("episode_project_id") not in (None, episode_project_id):
            errors.append("scene_asset_handoff.episode_project_id 与 context 不一致")

    requirements = loaded_artifacts.get("location_asset_requirements")
    prompt_manifest = loaded_artifacts.get("location_asset_prompt_manifest")
    if requirements and prompt_manifest:
        req = requirements.get("generation_requirements")
        out = prompt_manifest.get("assets")
        if not isinstance(req, list):
            errors.append("location_asset_requirements.generation_requirements 不是数组")
        if not isinstance(out, list):
            errors.append("location_asset_prompt_manifest.assets 不是数组")
        if isinstance(req, list) and isinstance(out, list):
            req_ids = [x.get("asset_id") for x in req if isinstance(x, dict)]
            out_ids = [x.get("asset_id") for x in out if isinstance(x, dict)]
            if len(req_ids) != len(set(req_ids)):
                errors.append("location requirements 存在重复 asset_id")
            if len(out_ids) != len(set(out_ids)):
                errors.append("location prompt manifest 存在重复 asset_id")
            if set(req_ids) != set(out_ids):
                errors.append("location prompt manifest 与 generation requirements 资产集合不一致")

    actual = loaded_artifacts.get("actual_asset_manifest")
    if actual:
        assets = actual.get("assets")
        if not isinstance(assets, list) or not assets:
            errors.append("actual_asset_manifest.assets 必须为非空数组")
        else:
            ids: list[str] = []
            for row in assets:
                if not isinstance(row, dict) or not row.get("asset_id"):
                    errors.append("actual_asset_manifest 存在无 asset_id 项")
                    continue
                aid = str(row["asset_id"]); ids.append(aid)
                if str(row.get("status", "approved")).lower() in BAD_STATES:
                    errors.append(f"actual asset {aid} 状态不可用")
                kind = row.get("asset_kind") or row.get("category")
                if kind in {"character", "creature"} and not str(row.get("tier") or (row.get("metadata") or {}).get("tier") or ""):
                    errors.append(f"actual asset {aid} 缺少 character/creature tier")
            if len(ids) != len(set(ids)):
                errors.append("actual_asset_manifest 存在重复 asset_id")

    angle_manifest = loaded_artifacts.get("angle_pack_manifest")
    if actual and angle_manifest and isinstance(actual.get("assets"), list):
        full_tiers = {"series_core", "recurring", "episode_important", "pet", "companion_creature", "recurring_creature"}
        packed_subjects = {
            str(pack.get("subject_id"))
            for pack in (angle_manifest.get("packs") or [])
            if isinstance(pack, dict) and pack.get("subject_id")
        }
        required_subjects: set[str] = set()
        for row in actual.get("assets") or []:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            kind = row.get("asset_kind") or row.get("category")
            tier = row.get("tier") or metadata.get("tier")
            subject_id = row.get("subject_id") or metadata.get("subject_id")
            if kind in {"character", "creature"} and tier in full_tiers and subject_id:
                required_subjects.add(str(subject_id))
        missing_packs = sorted(required_subjects - packed_subjects)
        if missing_packs:
            errors.append("重要角色/生物缺少独立八方向资产包：" + ", ".join(missing_packs))

    prompts = loaded_artifacts.get("video_prompt_manifest")
    if prompts:
        clips = prompts.get("clips")
        if not isinstance(clips, list) or not clips:
            errors.append("video_prompt_manifest.clips 必须为非空数组")
        else:
            clip_ids: list[str] = []
            for clip in clips:
                if not isinstance(clip, dict):
                    errors.append("video_prompt_manifest 存在非对象 clip"); continue
                cid = str(clip.get("clip_id") or ""); clip_ids.append(cid)
                if not cid:
                    errors.append("video prompt clip 缺少 clip_id")
                for field in ("scene_id", "location_id", "sub_location_id", "location_asset_id"):
                    if not str(clip.get(field) or ""):
                        errors.append(f"{cid or '<clip>'} 缺少 {field}")
                duration = clip.get("duration")
                if not isinstance(duration, int) or not 4 <= duration <= 15:
                    errors.append(f"{cid or '<clip>'} duration 必须为 4-15 整数")
            if len(clip_ids) != len(set(clip_ids)):
                errors.append("video_prompt_manifest 存在重复 clip_id")

    for name, relative in gate_spec.items():
        try:
            record = artifact_record(root, relative)
            data = load_json(safe_path(root, relative))
            passed = gate_passed(name, data, errors)
            gate_records[name] = {**record, "passed": passed}
            loaded_gates[name] = data
        except Exception as exc:
            errors.append(f"gate {name}: {exc}")

    # Bind the actual video job to the passed video gate.
    video_gate = loaded_gates.get("video_scene_binding")
    video_job_path: Path | None = None
    if video_gate:
        video_job_id = str(video_gate.get("video_job_id") or "")
        if video_job_id:
            candidate = safe_path(root, f"dispatch/video_jobs/{video_job_id}.json")
            if candidate.is_file():
                video_job_path = candidate
            else:
                errors.append(f"video_scene_binding 指向的视频任务不存在：{candidate.relative_to(root)}")
        else:
            jobs_dir = safe_path(root, "dispatch/video_jobs")
            jobs = sorted(jobs_dir.glob("*.json")) if jobs_dir.is_dir() else []
            if len(jobs) == 1:
                video_job_path = jobs[0]
                warnings.append("video_scene_binding 缺少 video_job_id；使用唯一 video job")
            else:
                errors.append("无法唯一确定 video job")
    if video_job_path:
        relative = video_job_path.relative_to(root).as_posix()
        try:
            artifact_records["video_job"] = artifact_record(root, relative)
            job = load_json(video_job_path)
            clips = job.get("clips")
            if not isinstance(clips, list) or not clips:
                errors.append("video job clips 为空")
            if video_gate and video_gate.get("video_job_id") and job.get("video_job_id") != video_gate.get("video_job_id"):
                errors.append("video job id 与 video scene gate 不一致")
        except Exception as exc:
            errors.append(f"video job: {exc}")

    passed_gate_count = sum(1 for name in required_gate_names if gate_records.get(name, {}).get("passed") is True)
    passed = not errors and passed_gate_count == len(required_gate_names)
    return {
        "schema_version": "1.0",
        "pipeline_profile": PIPELINE_PROFILE,
        "episode_project_id": episode_project_id,
        "pipeline_contract_schema_version": contract_schema,
        "passed": passed,
        "required_gate_count": len(required_gate_names),
        "passed_gate_count": passed_gate_count,
        "artifacts": artifact_records,
        "gates": gate_records,
        "errors": errors,
        "warnings": warnings,
        "created_at": utc_now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 DeepWhite scene_bound_auto_v1.2 单集生产链")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    root = Path(args.project_root).expanduser().resolve()
    try:
        evidence = validate_project(root)
    except Exception as exc:
        evidence = {
            "schema_version": "1.0",
            "pipeline_profile": PIPELINE_PROFILE,
            "passed": False,
            "errors": [str(exc)],
            "warnings": [],
            "created_at": utc_now(),
        }
    text = json.dumps(evidence, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        out = Path(args.out).expanduser().resolve()
        try:
            out.relative_to(root)
        except ValueError:
            print("--out 必须位于 project-root 内", file=sys.stderr)
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    return 0 if evidence.get("passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
