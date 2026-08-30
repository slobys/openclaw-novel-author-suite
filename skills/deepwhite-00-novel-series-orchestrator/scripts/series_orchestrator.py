#!/usr/bin/env python3
"""Idempotent one-episode-at-a-time queue for novel-to-drama production."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from common import (
    atomic_write_json,
    canonical_sha256,
    ensure_within,
    json_result,
    load_env_file,
    read_json,
    require_safe_id,
    sha256_file,
    utc_now,
)
from series_asset_gate import canonicalize_asset_delta, resolve_reuse_assets
from validate_episode_pipeline import PIPELINE_PROFILE, REQUIRED_GATE_NAMES, validate_project as validate_episode_pipeline_project


DEFAULT_OPENCLAW_HOME = Path(
    os.environ.get("OPENCLAW_STATE_DIR", os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
).expanduser()
QUEUE_NAMES = ("ready", "running", "done", "failed")
PIPELINE_CONTRACT_VERSION = "1.3"


class SeriesLock:
    def __init__(self, path: Path, stale_seconds: int = 300):
        self.path = path
        self.stale_seconds = stale_seconds
        self.acquired = False

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump({"pid": os.getpid(), "created_at": utc_now()}, handle)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale_seconds:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                raise RuntimeError("系列队列正被另一进程修改，请稍后重试")
        raise RuntimeError("无法取得系列队列锁")

    def __exit__(self, exc_type, exc, tb):
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def queue_dirs(root: Path) -> dict[str, Path]:
    dirs = {name: root / "queue" / name for name in QUEUE_NAMES}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def queue_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("episode_*.json"))


def refresh_progress(root: Path, status_override: str | None = None) -> dict[str, Any]:
    dirs = queue_dirs(root)
    series = read_json(root / "series.json")
    counts = {name: len(queue_files(path)) for name, path in dirs.items()}
    planned_count = len(list((root / "episodes").glob("episode_*.json")))
    current = None
    running_files = queue_files(dirs["running"])
    if running_files:
        current = read_json(running_files[0]).get("episode_project_id")
    if status_override:
        status = status_override
    elif counts["failed"]:
        status = "paused_on_failure"
    elif counts["running"]:
        running_state = read_json(running_files[0]).get("dispatch_status") if running_files else None
        status = "paused_on_failure" if running_state == "dispatch_error" else "processing"
    elif planned_count and counts["done"] == planned_count:
        status = "completed"
    elif counts["ready"]:
        status = "ready"
    else:
        status = str(series.get("status", "planning"))
    progress = {
        "schema_version": "1.0", "series_id": series["series_id"], "status": status,
        "planned_count": planned_count, "ready_count": counts["ready"],
        "running_count": counts["running"], "done_count": counts["done"],
        "failed_count": counts["failed"], "current_episode_project_id": current,
        "updated_at": utc_now(),
    }
    atomic_write_json(root / "progress.json", progress)
    series["status"] = status
    series["episode_count"] = planned_count
    series["updated_at"] = progress["updated_at"]
    atomic_write_json(root / "series.json", series)
    return progress


def find_episode(root: Path, project_id: str) -> tuple[str, Path] | None:
    for name, directory in queue_dirs(root).items():
        for path in queue_files(directory):
            try:
                if read_json(path).get("episode_project_id") == project_id:
                    return name, path
            except Exception:
                continue
    return None


def enqueue(root: Path) -> dict[str, Any]:
    from validate_series import validate_series_root

    validation = validate_series_root(root)
    if not validation["ok"]:
        raise ValueError("系列验证失败：" + "；".join(validation["errors"]))
    dirs = queue_dirs(root)
    added = 0
    skipped = 0
    with SeriesLock(root / "queue" / ".series.lock"):
        for source_path in sorted((root / "episodes").glob("episode_*.json")):
            episode = read_json(source_path)
            project_id = require_safe_id(episode.get("episode_project_id"), "episode_project_id")
            episode_hash = canonical_sha256(episode)
            existing = find_episode(root, project_id)
            if existing:
                # Completed episode IDs are immutable execution records.  A
                # later continuity correction to the planning brief must not
                # requeue them or block newly planned episodes.
                if existing[0] == "done":
                    skipped += 1
                    continue
                existing_data = read_json(existing[1])
                if existing_data.get("episode_content_sha256") != episode_hash:
                    raise RuntimeError(f"幂等冲突：{project_id} 已存在但内容不同；请使用新的 episode_project_id")
                skipped += 1
                continue
            queued = dict(episode)
            queued["episode_content_sha256"] = episode_hash
            queued["queue_status"] = "ready"
            queued["queued_at"] = utc_now()
            queued["whole_episode_retry_count"] = int(queued.get("whole_episode_retry_count", 0))
            atomic_write_json(dirs["ready"] / source_path.name, queued)
            added += 1
        progress = refresh_progress(root)
    return {"ok": True, "event": "episodes_enqueued", "added": added, "skipped": skipped, "progress": progress}


def openclaw_home_from_args(args: argparse.Namespace) -> Path:
    return Path(args.openclaw_home or os.environ.get("OPENCLAW_HOME") or DEFAULT_OPENCLAW_HOME).expanduser().resolve()


def hook_token(openclaw_home: Path) -> str:
    token = os.environ.get("OPENCLAW_ASSET_HOOK_TOKEN", "").strip()
    if not token:
        token = load_env_file(openclaw_home / ".env").get("OPENCLAW_ASSET_HOOK_TOKEN", "").strip()
    if not token:
        raise RuntimeError("缺少 OPENCLAW_ASSET_HOOK_TOKEN；未调用 Hook")
    return token


def post_hook(url: str, payload: dict[str, Any], token: str, attempts: int = 3) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error = None
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8", errors="replace")
                return {"status_code": response.status, "body": text[:500]}
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"OpenClaw Hook 调用失败（已尝试 {attempts} 次）：{last_error}")



def build_pipeline_contract(episode: dict[str, Any]) -> dict[str, Any]:
    """Build the immutable per-episode AUTO production contract.

    Existing v1.1 episodes are upgraded to the scene-bound profile by default.
    Legacy behavior is available only through an explicit migration flag.
    """
    project_id = require_safe_id(episode.get("episode_project_id"), "episode_project_id")
    production = episode.get("production") or {}
    if not isinstance(production, dict):
        production = {}
    legacy = (
        production.get("legacy_pipeline_allowed") is True
        and production.get("pipeline_profile") == "legacy_v1.1"
    )
    if legacy:
        return {
            "schema_version": PIPELINE_CONTRACT_VERSION,
            "pipeline_profile": "legacy_v1.1",
            "episode_project_id": project_id,
            "require_pipeline_evidence": False,
            "legacy_pipeline_allowed": True,
            "required_skill_sequence": [
                "deepwhite-screenwriting-v1",
                "deepwhite-continuity-worldstate-zh",
                "deepwhite-image-prompt-builder",
                "deepwhite-shotlist-builder-zh-user",
            ],
            "required_gates": [],
            "created_at": utc_now(),
        }

    visual = episode.get("visual_strategy") or {}
    configured_policy = visual.get("scene_asset_policy") if isinstance(visual, dict) else None
    scene_policy = {
        "required": True,
        "planner_skill": "deepwhite-scene-asset-planner",
        "require_100_percent_scene_coverage": True,
        "allow_editorial_sublocation_enrichment": True,
        "same_background_soft_limit_seconds": 24,
        "same_background_hard_limit_seconds": 35,
    }
    if isinstance(configured_policy, dict):
        # User/planning values may tighten composition limits, but cannot
        # disable scene coverage or replace the planner in AUTO v1.2.
        for key in (
            "allow_editorial_sublocation_enrichment",
            "same_background_soft_limit_seconds",
            "same_background_hard_limit_seconds",
        ):
            if key in configured_policy:
                scene_policy[key] = configured_policy[key]

    return {
        "schema_version": PIPELINE_CONTRACT_VERSION,
        "pipeline_profile": PIPELINE_PROFILE,
        "episode_project_id": project_id,
        "require_pipeline_evidence": True,
        "scene_asset_policy": scene_policy,
        "required_skill_sequence": [
            "deepwhite-screenwriting-v1",
            "deepwhite-continuity-worldstate-zh",
            "deepwhite-scene-asset-planner",
            "deepwhite-image-prompt-builder",
            "deepwhite-n8n-asset-dispatcher",
            "deepwhite-shotlist-builder-zh-user",
            "deepwhite-n8n-video-dispatcher",
        ],
        "optional_skill_sequence": ["deepwhite-shot-transition-builder-zh"],
        "required_artifacts": {
            "scene_index": "script/scene_index.json",
            "scene_asset_plan": "assets/scene_asset_plan.json",
            "location_asset_requirements": "assets/location_asset_requirements.json",
            "scene_asset_handoff": "handoffs/scene_asset_handoff.json",
            "location_asset_prompt_manifest": "assets/location_asset_prompt_manifest.json",
            "angle_pack_manifest": "assets/angle_pack_manifest.json",
            "actual_asset_manifest": "assets/actual_asset_manifest.json",
            "spatial_blocking": "shots/spatial_blocking.json",
            "video_prompt_manifest": "video_prompts/video_prompt_manifest.json",
        },
        "required_gates": list(REQUIRED_GATE_NAMES),
        "gate_paths": {
            "scene_asset_coverage": "gates/scene_asset_coverage_gate.json",
            "location_prompt_manifest": "gates/location_prompt_manifest_gate.json",
            "angle_pack": "gates/angle_pack_gate.json",
            "asset_retry_budget": "gates/asset_retry_budget_gate.json",
            "environment_continuity": "gates/environment_continuity_gate.json",
            "shot_scene_binding": "gates/shot_scene_binding_gate.json",
            "video_prompt_review": "review/video_prompt_gate_review.json",
            "video_scene_binding": "gates/video_scene_binding_gate.json",
        },
        "asset_policy": {
            "image_prompt_mode_for_scene_assets": "STRICT_ASSET_PLAN_MODE",
            "planner_verified_reuse_ids_are_forbidden_generation_ids": True,
            "require_actual_asset_manifest_to_include_series_reuse": True,
            "required_angle_pack_tiers": ["series_core", "recurring", "episode_important", "pet", "companion_creature", "recurring_creature"],
            "one_independent_9_16_asset_per_angle": True,
            "max_semantic_generation_attempts_per_lineage_requirement": 3,
        },
        "environment_continuity_policy": {
            "movement_scenes_require_ordered_route_anchors": True,
            "require_verified_predecessor_reference": True,
            "require_landmark_world_relationship_lock": True,
        },
        "video_policy": {
            "min_generated_clip_seconds": 4,
            "max_generated_clip_seconds": 15,
            "forbid_cross_scene_clip": True,
            "require_exact_scene_location_asset_binding": True,
        },
        "completion_policy": {
            "pipeline_evidence_path": "review/series_pipeline_evidence.json",
            "require_pipeline_evidence": True,
            "verify_evidence_hashes_at_complete": True,
        },
        "created_at": utc_now(),
    }


def _safe_project_relative(project_root: Path, relative: str) -> Path:
    rel = Path(str(relative))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"pipeline evidence 包含不安全路径：{relative}")
    target = ensure_within(project_root, project_root / rel)
    return target


def verify_pipeline_evidence(project_root: Path, evidence_path: Path, project_id: str) -> dict[str, Any]:
    evidence_path = ensure_within(project_root, evidence_path)
    if not evidence_path.is_file() or evidence_path.stat().st_size <= 0:
        raise FileNotFoundError(f"Pipeline Evidence 不存在或为空：{evidence_path}")
    evidence = read_json(evidence_path)
    if not isinstance(evidence, dict):
        raise ValueError("series_pipeline_evidence.json 顶层必须是对象")
    if evidence.get("passed") is not True:
        raise ValueError("series_pipeline_evidence.passed 必须为 true")
    if evidence.get("pipeline_profile") != PIPELINE_PROFILE:
        raise ValueError("series_pipeline_evidence.pipeline_profile 不匹配")
    if evidence.get("episode_project_id") != project_id:
        raise ValueError("series_pipeline_evidence.episode_project_id 与当前集不一致")

    # Independently re-run the deterministic validator.  Do not trust a
    # self-authored passed=true evidence document.
    fresh = validate_episode_pipeline_project(project_root)
    if fresh.get("passed") is not True:
        problems = fresh.get("errors") or []
        raise ValueError("Pipeline fresh validation 失败：" + "；".join(str(x) for x in problems[:10]))

    for section in ("artifacts", "gates"):
        supplied_rows = evidence.get(section)
        fresh_rows = fresh.get(section)
        if not isinstance(supplied_rows, dict) or not isinstance(fresh_rows, dict):
            raise ValueError(f"pipeline evidence.{section} 必须是对象")
        for name, fresh_row in fresh_rows.items():
            supplied = supplied_rows.get(name)
            if not isinstance(supplied, dict):
                raise ValueError(f"pipeline evidence 缺少 {section}.{name}")
            if supplied.get("relative_path") != fresh_row.get("relative_path"):
                raise ValueError(f"pipeline evidence {section}.{name}.relative_path 已变化")
            if str(supplied.get("sha256", "")).lower() != str(fresh_row.get("sha256", "")).lower():
                raise ValueError(f"pipeline evidence {section}.{name}.sha256 已失效")
            _safe_project_relative(project_root, str(fresh_row.get("relative_path")))
            if section == "gates" and supplied.get("passed") is not True:
                raise ValueError(f"pipeline evidence gate 未通过：{name}")

    return {
        "path": str(evidence_path),
        "sha256": sha256_file(evidence_path),
        "pipeline_profile": PIPELINE_PROFILE,
        "required_gate_count": fresh.get("required_gate_count"),
        "passed_gate_count": fresh.get("passed_gate_count"),
    }

def dispatch_next(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    dirs = queue_dirs(root)
    with SeriesLock(root / "queue" / ".series.lock"):
        claimed_from_ready = False
        running = queue_files(dirs["running"])
        if len(running) > 1:
            raise RuntimeError("发现多个 running 集，已停止以防重复费用")
        if running:
            current = read_json(running[0])
            if current.get("dispatch_status") == "dispatched":
                return {"ok": True, "event": "already_running", "episode_project_id": current.get("episode_project_id")}
            running_path = running[0]
        else:
            ready = queue_files(dirs["ready"])
            if not ready:
                progress = refresh_progress(root)
                return {"ok": True, "event": "nothing_to_dispatch", "progress": progress}
            source = ready[0]
            current = read_json(source)
            running_path = dirs["running"] / source.name
            claimed_from_ready = True

        registry = read_json(root / "asset_registry.json")
        format_strategy_path = root / "plan" / "format_strategy.json"
        format_strategy = read_json(format_strategy_path) if format_strategy_path.is_file() else None
        visual_strategy = current.get("visual_strategy") or {}
        reuse_ids = visual_strategy.get("asset_reuse_ids") or []
        if not isinstance(reuse_ids, list):
            raise ValueError("episode.visual_strategy.asset_reuse_ids 必须为数组")
        resolved_reuse_assets = resolve_reuse_assets(root, registry, reuse_ids)
        new_requirements = visual_strategy.get("new_asset_requirements") or []
        if not isinstance(new_requirements, list):
            raise ValueError("episode.visual_strategy.new_asset_requirements 必须为数组")

        if claimed_from_ready:
            current["queue_status"] = "running"
            current["claimed_at"] = utc_now()
            current["dispatch_status"] = "pending"
            atomic_write_json(running_path, current)
            source.unlink()

        project_id = require_safe_id(current.get("episode_project_id"), "episode_project_id")
        series_id = require_safe_id(current.get("series_id"), "series_id")
        openclaw_home = openclaw_home_from_args(args)
        drama_root = openclaw_home / "workspace-drama-producer" / "projects"
        project_root = ensure_within(drama_root, drama_root / project_id)
        context_path = project_root / "input" / "series_episode_context.json"
        pipeline_contract_path = project_root / "input" / "production_pipeline_contract.json"
        pipeline_contract = build_pipeline_contract(current)
        pipeline_contract_sha = canonical_sha256(pipeline_contract)
        pipeline_contract["contract_sha256"] = pipeline_contract_sha
        atomic_write_json(pipeline_contract_path, pipeline_contract)
        format_strategy_path = root / "plan" / "format_strategy.json"
        format_strategy = read_json(format_strategy_path) if format_strategy_path.is_file() else None
        context = {
            "schema_version": "1.1", "event": "deepwhite_series_episode_ready",
            "series_id": series_id, "episode_project_id": project_id,
            "episode_number": current.get("episode_number"),
            "episode_content_sha256": current.get("episode_content_sha256"),
            "episode": current,
            "series_format_strategy": format_strategy,
            "series_format_strategy_sha256": canonical_sha256(format_strategy) if format_strategy else None,
            "series_world_state": read_json(root / "world_state" / "current.json"),
            "series_asset_registry": registry,
            "resolved_reuse_assets": resolved_reuse_assets,
            "production_pipeline": {
                "pipeline_profile": pipeline_contract.get("pipeline_profile"),
                "contract_path": "input/production_pipeline_contract.json",
                "contract_sha256": pipeline_contract_sha,
                "require_pipeline_evidence": pipeline_contract.get("require_pipeline_evidence") is True,
                "required_skill_sequence": pipeline_contract.get("required_skill_sequence", []),
                "required_gates": pipeline_contract.get("required_gates", []),
            },
            "asset_generation_policy": {
                "mode": "strict_series_asset_reuse_v1.3_scene_aware",
                "reuse_asset_ids": [row["asset_id"] for row in resolved_reuse_assets],
                "forbidden_generation_asset_ids": [row["asset_id"] for row in resolved_reuse_assets],
                "new_asset_requirements": new_requirements,
                "canonical_asset_root": str((root / "series_assets").resolve()),
                "require_generation_plan_gate": True,
                "scene_planner_reuse_source": "handoffs/scene_asset_handoff.json",
                "require_scene_handoff_for_location_generation_plan": pipeline_contract.get("pipeline_profile") == PIPELINE_PROFILE,
            },
            "dispatched_at": utc_now(),
        }
        context_sha = canonical_sha256(context)
        context["context_sha256"] = context_sha
        atomic_write_json(context_path, context)

        payload = {
            "event": "deepwhite_series_episode_ready", "series_id": series_id,
            "episode_project_id": project_id, "episode_number": current.get("episode_number"),
            "context_sha256": context_sha,
            "pipeline_profile": pipeline_contract.get("pipeline_profile"),
            "pipeline_contract_sha256": pipeline_contract_sha,
        }
        try:
            if args.no_hook:
                hook_result = {"status_code": 0, "body": "no-hook simulation"}
            else:
                hook_result = post_hook(args.hook_url, payload, hook_token(openclaw_home), attempts=3)
            current["dispatch_status"] = "dispatched" if not args.no_hook else "simulated"
            current["dispatched_at"] = utc_now()
            current["context_sha256"] = context_sha
            current["pipeline_profile"] = pipeline_contract.get("pipeline_profile")
            current["pipeline_contract_sha256"] = pipeline_contract_sha
            current["require_pipeline_evidence"] = pipeline_contract.get("require_pipeline_evidence") is True
            current.pop("last_dispatch_error", None)
            atomic_write_json(running_path, current)
            progress = refresh_progress(root)
            return {
                "ok": True, "event": "episode_dispatched", "episode_project_id": project_id,
                "context_path": str(context_path),
                "pipeline_contract_path": str(pipeline_contract_path),
                "pipeline_profile": pipeline_contract.get("pipeline_profile"),
                "hook_status_code": hook_result["status_code"],
                "simulated": bool(args.no_hook), "progress": progress,
            }
        except Exception as exc:
            current["dispatch_status"] = "dispatch_error"
            current["last_dispatch_error"] = str(exc)
            current["last_dispatch_error_at"] = utc_now()
            atomic_write_json(running_path, current)
            refresh_progress(root, "paused_on_failure")
            raise


def verify_final_manifest(manifest_path: Path) -> tuple[dict[str, Any], Path]:
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("status") != "completed":
        raise ValueError("final_video_manifest.status 必须为 completed")
    relative = manifest.get("relative_path")
    if not relative or Path(str(relative)).is_absolute() or ".." in Path(str(relative)).parts:
        raise ValueError("final_video_manifest.relative_path 无效")
    video_path = ensure_within(manifest_path.parent, manifest_path.parent / str(relative))
    if not video_path.is_file() or video_path.stat().st_size <= 0:
        raise FileNotFoundError(f"最终 MP4 不存在或为空：{video_path}")
    expected_size = manifest.get("file_size")
    if expected_size is not None and int(expected_size) != video_path.stat().st_size:
        raise ValueError("最终 MP4 文件大小与 manifest 不一致")
    expected_sha = str(manifest.get("sha256", "")).lower()
    actual_sha = sha256_file(video_path)
    if not expected_sha or expected_sha != actual_sha:
        raise ValueError("最终 MP4 SHA256 与 manifest 不一致")
    return manifest, video_path


def verify_context(context_path: Path, series_id: str, project_id: str, context_sha256: str) -> dict[str, Any]:
    context = read_json(context_path)
    if not isinstance(context, dict):
        raise ValueError("series_episode_context.json 顶层必须是对象")
    if context.get("series_id") != require_safe_id(series_id, "series_id"):
        raise ValueError("上下文 series_id 与 Hook 不一致")
    if context.get("episode_project_id") != require_safe_id(project_id, "episode_project_id"):
        raise ValueError("上下文 episode_project_id 与 Hook 不一致")
    stored = str(context.get("context_sha256", "")).lower()
    expected = str(context_sha256 or "").lower()
    unsigned = dict(context)
    unsigned.pop("context_sha256", None)
    actual = canonical_sha256(unsigned)
    if not expected or stored != expected or actual != expected:
        raise ValueError("上下文 SHA256 校验失败")
    return {
        "ok": True, "event": "series_context_verified", "series_id": series_id,
        "episode_project_id": project_id, "episode_number": context.get("episode_number"),
        "context_sha256": actual,
    }


def complete(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    project_id = require_safe_id(args.episode_project_id, "episode_project_id")
    manifest_path = Path(args.final_manifest).expanduser().resolve()
    continuity_path = Path(args.continuity_out).expanduser().resolve()
    manifest, video_path = verify_final_manifest(manifest_path)
    continuity = read_json(continuity_path)
    if not isinstance(continuity, dict) or continuity.get("episode_project_id") != project_id:
        raise ValueError("continuity_out 与 episode_project_id 不匹配")
    if continuity.get("gate", {}).get("passed") is not True:
        raise ValueError("continuity_out.gate.passed 必须为 true")

    dirs = queue_dirs(root)
    with SeriesLock(root / "queue" / ".series.lock"):
        found = find_episode(root, project_id)
        if not found:
            raise FileNotFoundError(f"队列中找不到：{project_id}")
        if found[0] == "done":
            return {"ok": True, "event": "already_completed", "episode_project_id": project_id}
        if found[0] != "running":
            raise RuntimeError(f"只有 running 集可以完成提交；当前为 {found[0]}")
        episode = read_json(found[1])
        episode_number = int(episode["episode_number"])
        series_id = require_safe_id(episode.get("series_id"), "series_id")

        production = episode.get("production") or {}
        auto_mode = not isinstance(production, dict) or production.get("auto_production_mode", True) is True
        legacy = (
            isinstance(production, dict)
            and production.get("legacy_pipeline_allowed") is True
            and production.get("pipeline_profile") == "legacy_v1.1"
        )
        require_evidence = (episode.get("require_pipeline_evidence") is True) or (auto_mode and not legacy)
        pipeline_evidence_info = None
        if require_evidence:
            if not args.pipeline_evidence:
                raise ValueError("AUTO v1.2 完成本集必须提供 --pipeline-evidence")
            openclaw_home = openclaw_home_from_args(args)
            project_root = ensure_within(
                openclaw_home / "workspace-drama-producer" / "projects",
                openclaw_home / "workspace-drama-producer" / "projects" / project_id,
            )
            evidence_path = Path(args.pipeline_evidence).expanduser().resolve()
            pipeline_evidence_info = verify_pipeline_evidence(project_root, evidence_path, project_id)

        delta_path = Path(args.asset_delta).expanduser().resolve()
        delta = read_json(delta_path)
        registry = canonicalize_asset_delta(
            root, read_json(root / "asset_registry.json"), delta,
            series_id, project_id, episode_number,
        )
        reused_ids = (episode.get("visual_strategy") or {}).get("asset_reuse_ids") or []
        resolved_reuse = resolve_reuse_assets(root, registry, reused_ids)
        reused_set = {row["asset_id"] for row in resolved_reuse}
        for row in registry.get("assets", []):
            if row.get("asset_id") in reused_set:
                row["last_used_episode"] = episode_number
                row["updated_at"] = utc_now()

        episode["queue_status"] = "done"
        episode["completed_at"] = utc_now()
        episode["final_video_manifest"] = str(manifest_path)
        episode["final_video_sha256"] = manifest["sha256"]
        episode["final_video_path"] = str(video_path)
        if pipeline_evidence_info is not None:
            episode["pipeline_evidence"] = pipeline_evidence_info
        done_path = dirs["done"] / found[1].name
        atomic_write_json(done_path, episode)
        found[1].unlink()

        state_path = root / "world_state" / f"episode_{episode_number:03d}.json"
        atomic_write_json(state_path, continuity)
        current_state = dict(continuity)
        current_state["after_episode"] = episode_number
        current_state["updated_at"] = utc_now()
        atomic_write_json(root / "world_state" / "current.json", current_state)
        atomic_write_json(root / "asset_registry.json", registry)
        commit_marker = root / "queue" / "done" / f".{project_id}.series_commit.json"
        atomic_write_json(commit_marker, {
            "episode_project_id": project_id, "episode_number": episode_number,
            "final_video_sha256": manifest["sha256"],
            "pipeline_evidence_sha256": pipeline_evidence_info.get("sha256") if pipeline_evidence_info else None,
            "pipeline_profile": pipeline_evidence_info.get("pipeline_profile") if pipeline_evidence_info else "legacy_v1.1",
            "committed_at": utc_now(),
        })
        progress = refresh_progress(root)

    result: dict[str, Any] = {
        "ok": True, "event": "episode_completed", "episode_project_id": project_id,
        "episode_number": episode_number, "progress": progress,
    }
    recovery = (episode.get("production") or {}).get("recovery_directive") or {}
    hold_next = recovery.get("do_not_dispatch_next_episode") is True
    if args.dispatch_next and progress["status"] != "completed" and not hold_next:
        result["next_dispatch"] = dispatch_next(root, args)
    elif hold_next:
        result["next_dispatch"] = {
            "ok": True,
            "event": "held_for_user_confirmation",
            "reason": "episode production directive forbids automatic next-episode dispatch",
        }
    return result


def fail_episode(root: Path, project_id: str, reason: str) -> dict[str, Any]:
    project_id = require_safe_id(project_id, "episode_project_id")
    if not reason.strip():
        raise ValueError("reason 不能为空")
    dirs = queue_dirs(root)
    with SeriesLock(root / "queue" / ".series.lock"):
        found = find_episode(root, project_id)
        if not found:
            raise FileNotFoundError(f"队列中找不到：{project_id}")
        if found[0] == "failed":
            return {"ok": True, "event": "already_failed", "episode_project_id": project_id}
        if found[0] != "running":
            raise RuntimeError(f"只有 running 集可以标记失败；当前为 {found[0]}")
        episode = read_json(found[1])
        episode["queue_status"] = "failed"
        episode["failed_at"] = utc_now()
        episode["failure_reason"] = reason.strip()
        atomic_write_json(dirs["failed"] / found[1].name, episode)
        found[1].unlink()
        progress = refresh_progress(root, "paused_on_failure")
    return {"ok": True, "event": "episode_failed", "episode_project_id": project_id, "progress": progress}


def retry_failed(root: Path, project_id: str, max_whole_episode_retries: int) -> dict[str, Any]:
    project_id = require_safe_id(project_id, "episode_project_id")
    dirs = queue_dirs(root)
    with SeriesLock(root / "queue" / ".series.lock"):
        if queue_files(dirs["running"]):
            raise RuntimeError("已有 running 集，禁止恢复失败集")
        found = find_episode(root, project_id)
        if not found or found[0] != "failed":
            raise FileNotFoundError(f"failed 队列中找不到：{project_id}")
        episode = read_json(found[1])
        count = int(episode.get("whole_episode_retry_count", 0))
        if count >= max_whole_episode_retries:
            raise RuntimeError(f"整集人工恢复次数已达上限 {max_whole_episode_retries}")
        episode["whole_episode_retry_count"] = count + 1
        episode["queue_status"] = "ready"
        episode["retried_at"] = utc_now()
        episode.pop("failure_reason", None)
        episode.pop("failed_at", None)
        atomic_write_json(dirs["ready"] / found[1].name, episode)
        found[1].unlink()
        progress = refresh_progress(root)
    return {"ok": True, "event": "failed_episode_requeued", "episode_project_id": project_id, "progress": progress}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepWhite 小说系列队列总控")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("enqueue", "status"):
        command = sub.add_parser(name)
        command.add_argument("--series-root", required=True)
    dispatch = sub.add_parser("dispatch-next")
    dispatch.add_argument("--series-root", required=True)
    dispatch.add_argument("--openclaw-home")
    dispatch.add_argument("--hook-url", default="http://127.0.0.1:18789/hooks/deepwhite-series-episode")
    dispatch.add_argument("--no-hook", action="store_true", help="仅供本地部署前模拟，不调用 OpenClaw Hook")
    complete_cmd = sub.add_parser("complete")
    complete_cmd.add_argument("--series-root", required=True)
    complete_cmd.add_argument("--episode-project-id", required=True)
    complete_cmd.add_argument("--final-manifest", required=True)
    complete_cmd.add_argument("--continuity-out", required=True)
    complete_cmd.add_argument("--asset-delta", required=True)
    complete_cmd.add_argument("--pipeline-evidence", help="AUTO v1.2 必填：review/series_pipeline_evidence.json")
    complete_cmd.add_argument("--dispatch-next", action="store_true")
    complete_cmd.add_argument("--openclaw-home")
    complete_cmd.add_argument("--hook-url", default="http://127.0.0.1:18789/hooks/deepwhite-series-episode")
    complete_cmd.add_argument("--no-hook", action="store_true")
    fail_cmd = sub.add_parser("fail")
    fail_cmd.add_argument("--series-root", required=True)
    fail_cmd.add_argument("--episode-project-id", required=True)
    fail_cmd.add_argument("--reason", required=True)
    retry = sub.add_parser("retry-failed")
    retry.add_argument("--series-root", required=True)
    retry.add_argument("--episode-project-id", required=True)
    retry.add_argument("--max-whole-episode-retries", type=int, default=1)
    verify = sub.add_parser("verify-context")
    verify.add_argument("--series-root", required=True)
    verify.add_argument("--context", required=True)
    verify.add_argument("--series-id", required=True)
    verify.add_argument("--episode-project-id", required=True)
    verify.add_argument("--context-sha256", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.series_root).expanduser().resolve()
    if not (root / "series.json").is_file():
        raise FileNotFoundError(f"不是有效系列项目：{root}")
    if args.command == "enqueue":
        result = enqueue(root)
    elif args.command == "dispatch-next":
        result = dispatch_next(root, args)
    elif args.command == "complete":
        result = complete(root, args)
    elif args.command == "fail":
        result = fail_episode(root, args.episode_project_id, args.reason)
    elif args.command == "retry-failed":
        result = retry_failed(root, args.episode_project_id, args.max_whole_episode_retries)
    elif args.command == "verify-context":
        result = verify_context(
            Path(args.context).expanduser().resolve(), args.series_id,
            args.episode_project_id, args.context_sha256,
        )
    else:
        result = {"ok": True, "event": "status", "progress": refresh_progress(root)}
    json_result(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
