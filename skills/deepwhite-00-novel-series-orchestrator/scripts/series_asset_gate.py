#!/usr/bin/env python3
"""Canonical series-asset registry, reuse verification and generation filtering."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from common import (
    atomic_write_json,
    ensure_within,
    json_result,
    read_json,
    require_safe_id,
    sha256_file,
    utc_now,
)


ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
ASSET_ROLES = {"base", "state_version"}


def _registry_rows(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for raw in registry.get("assets", []):
        if not isinstance(raw, dict):
            raise ValueError("asset_registry.assets 中存在非对象项目")
        asset_id = require_safe_id(raw.get("asset_id"), "asset_registry.asset_id")
        if asset_id in rows:
            raise ValueError(f"资产注册表存在重复 asset_id：{asset_id}")
        rows[asset_id] = dict(raw)
    return rows


def _canonical_file(root: Path, row: dict[str, Any]) -> Path:
    relative = str(row.get("canonical_relative_path") or "").strip()
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"资产 {row.get('asset_id')} 缺少有效 canonical_relative_path")
    target = ensure_within(root, root / relative)
    asset_root = (root / "series_assets").resolve()
    try:
        target.relative_to(asset_root)
    except ValueError as exc:
        raise ValueError(f"资产 {row.get('asset_id')} 不在 series_assets 目录内") from exc
    return target


def verify_registry_asset(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    asset_id = require_safe_id(row.get("asset_id"), "asset_registry.asset_id")
    target = _canonical_file(root, row)
    if not target.is_file():
        raise FileNotFoundError(f"复用资产文件不存在：{asset_id} -> {target}")
    size = target.stat().st_size
    if size <= 0:
        raise ValueError(f"复用资产文件为空：{asset_id}")
    expected_size = int(row.get("file_size") or 0)
    if expected_size <= 0 or expected_size != size:
        raise ValueError(f"复用资产文件大小不一致：{asset_id}，登记 {expected_size}，实际 {size}")
    expected_sha = str(row.get("sha256") or "").strip().lower()
    actual_sha = sha256_file(target)
    if len(expected_sha) != 64 or expected_sha != actual_sha:
        raise ValueError(f"复用资产 SHA256 不一致：{asset_id}")
    result = dict(row)
    result["canonical_path"] = str(target)
    result["verified_file_size"] = size
    result["verified_sha256"] = actual_sha
    result["verified_at"] = utc_now()
    return result


def resolve_reuse_assets(root: Path, registry: dict[str, Any], asset_ids: list[Any]) -> list[dict[str, Any]]:
    rows = _registry_rows(registry)
    resolved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_id in asset_ids:
        asset_id = require_safe_id(raw_id, "visual_strategy.asset_reuse_ids")
        if asset_id in seen:
            continue
        seen.add(asset_id)
        if asset_id not in rows:
            raise ValueError(f"复用资产未注册：{asset_id}")
        resolved.append(verify_registry_asset(root, rows[asset_id]))
    return resolved


def verify_entire_registry(root: Path, registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [verify_registry_asset(root, row) for row in _registry_rows(registry).values()]


def _copy_atomic(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copyfile(source, tmp)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()


def canonicalize_asset_delta(
    root: Path,
    registry: dict[str, Any],
    delta: dict[str, Any],
    series_id: str,
    episode_project_id: str,
    episode_number: int,
) -> dict[str, Any]:
    if not isinstance(delta, dict) or not isinstance(delta.get("assets"), list):
        raise ValueError("asset_delta 顶层必须是对象且 assets 必须为数组")
    if delta.get("series_id") != series_id:
        raise ValueError("asset_delta.series_id 与系列不一致")
    if delta.get("episode_project_id") != episode_project_id:
        raise ValueError("asset_delta.episode_project_id 与当前集不一致")

    existing = _registry_rows(registry)
    prepared: list[tuple[dict[str, Any], Path, Path]] = []
    incoming_ids: set[str] = set()
    for raw in delta["assets"]:
        if not isinstance(raw, dict):
            raise ValueError("asset_delta.assets 中存在非对象项目")
        asset_id = require_safe_id(raw.get("asset_id"), "asset_delta.asset_id")
        if asset_id in incoming_ids:
            raise ValueError(f"asset_delta 存在重复 asset_id：{asset_id}")
        incoming_ids.add(asset_id)
        role = str(raw.get("asset_role") or "").strip()
        if role not in ASSET_ROLES:
            raise ValueError(f"资产 {asset_id} 的 asset_role 必须为 base 或 state_version")
        fingerprint = str(raw.get("identity_fingerprint") or "").strip()
        if not fingerprint:
            raise ValueError(f"资产 {asset_id} 缺少 identity_fingerprint")
        source_text = str(raw.get("source_path") or "").strip()
        if not source_text:
            raise ValueError(f"资产 {asset_id} 缺少 source_path")
        source = Path(source_text).expanduser().resolve()
        if not source.is_file() or source.stat().st_size <= 0:
            raise FileNotFoundError(f"资产源图片不存在或为空：{asset_id} -> {source}")
        suffix = source.suffix.lower()
        if suffix not in ALLOWED_IMAGE_SUFFIXES:
            raise ValueError(f"资产 {asset_id} 的图片格式不支持：{suffix}")
        size = source.stat().st_size
        digest = sha256_file(source)
        if raw.get("source_file_size") is not None and int(raw["source_file_size"]) != size:
            raise ValueError(f"资产 {asset_id} 的 source_file_size 与文件不一致")
        if raw.get("source_sha256") and str(raw["source_sha256"]).lower() != digest:
            raise ValueError(f"资产 {asset_id} 的 source_sha256 与文件不一致")
        old = existing.get(asset_id)
        if old and old.get("identity_fingerprint") != fingerprint:
            raise ValueError(f"资产身份冲突：{asset_id}；不能用状态图覆盖基础身份")
        if old and old.get("asset_role") and old.get("asset_role") != role:
            raise ValueError(f"资产角色冲突：{asset_id}；base/state_version 不可互换")
        base_asset_id = None
        if role == "state_version":
            base_asset_id = require_safe_id(raw.get("base_asset_id"), f"{asset_id}.base_asset_id")
            base = existing.get(base_asset_id)
            if base is None:
                raise ValueError(f"状态资产 {asset_id} 的基础资产未注册：{base_asset_id}")
            if base.get("asset_role") not in (None, "base"):
                raise ValueError(f"状态资产 {asset_id} 指向的不是基础资产：{base_asset_id}")
            if base.get("identity_fingerprint") != fingerprint:
                raise ValueError(f"状态资产 {asset_id} 与基础资产 {base_asset_id} 身份指纹不一致")
        relative = Path("series_assets") / asset_id / f"{asset_id}__{digest[:16]}{suffix}"
        target = ensure_within(root, root / relative)
        old_first_used = old.get("first_used_episode") if old else None
        try:
            first_used_episode = int(old_first_used) if old_first_used is not None else episode_number
        except (TypeError, ValueError):
            first_used_episode = episode_number
        record = {
            "asset_id": asset_id,
            "category": str(raw.get("category") or "").strip(),
            "name": str(raw.get("name") or "").strip(),
            "asset_role": role,
            "base_asset_id": base_asset_id,
            "state_version": raw.get("state_version") if role == "state_version" else None,
            "identity_fingerprint": fingerprint,
            "canonical_relative_path": relative.as_posix(),
            "filename": target.name,
            "mime_type": mimetypes.guess_type(target.name)[0] or "application/octet-stream",
            "file_size": size,
            "sha256": digest,
            "source_provenance": {"source_path": str(source), "registered_from_episode": episode_project_id},
            "first_used_episode": first_used_episode,
            "last_used_episode": episode_number,
            "updated_at": utc_now(),
        }
        revisions = list(old.get("revisions", [])) if old else []
        if not any(isinstance(item, dict) and item.get("sha256") == digest for item in revisions):
            revisions.append({
                "sha256": digest, "file_size": size,
                "canonical_relative_path": relative.as_posix(),
                "registered_from_episode": episode_project_id, "registered_at": utc_now(),
            })
        record["revisions"] = revisions
        prepared.append((record, source, target))

    for record, source, target in prepared:
        _copy_atomic(source, target)
        verify_registry_asset(root, record)
        existing[record["asset_id"]] = record

    registry["schema_version"] = "1.2"
    registry["series_id"] = series_id
    registry["asset_root"] = "series_assets"
    registry["assets"] = sorted(existing.values(), key=lambda row: str(row.get("asset_id")))
    registry["updated_at"] = utc_now()
    return registry


def build_generation_plan(
    context: dict[str, Any],
    requested: dict[str, Any],
    scene_handoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = context.get("asset_generation_policy") or {}
    reuse_ids = {str(value) for value in policy.get("forbidden_generation_asset_ids", [])}

    planner_reuse_ids: set[str] = set()
    if scene_handoff is not None:
        if not isinstance(scene_handoff, dict):
            raise ValueError("scene-handoff 顶层必须是对象")
        if scene_handoff.get("gate_passed") is not True:
            raise ValueError("scene-handoff.gate_passed 必须为 true")
        raw_planner_reuse = scene_handoff.get("verified_reuse_asset_ids") or []
        if not isinstance(raw_planner_reuse, list):
            raise ValueError("scene-handoff.verified_reuse_asset_ids 必须为数组")
        planner_reuse_ids = {require_safe_id(value, "verified_reuse_asset_id") for value in raw_planner_reuse}

        registry = context.get("series_asset_registry") or {}
        registry_rows = registry.get("assets") if isinstance(registry, dict) else []
        known_registry_ids = {
            str(row.get("asset_id"))
            for row in (registry_rows or [])
            if isinstance(row, dict) and row.get("asset_id")
        }
        unknown = sorted(planner_reuse_ids - known_registry_ids)
        if unknown:
            raise ValueError("Scene Planner 声明了未注册的复用资产：" + ", ".join(unknown))
        reuse_ids.update(planner_reuse_ids)

    source_assets = requested.get("assets")
    if not isinstance(source_assets, list):
        raise ValueError("requested-assets 顶层必须包含 assets 数组")
    generation_assets: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in source_assets:
        if not isinstance(raw, dict):
            raise ValueError("requested-assets.assets 中存在非对象项目")
        asset_id = require_safe_id(raw.get("asset_id"), "requested asset_id")
        if asset_id in seen:
            raise ValueError(f"待生成清单存在重复 asset_id：{asset_id}")
        seen.add(asset_id)
        if asset_id in reuse_ids:
            reason = (
                "scene_planner_verified_series_reuse"
                if asset_id in planner_reuse_ids
                else "registered_series_asset_reuse"
            )
            excluded.append({"asset_id": asset_id, "reason": reason})
        else:
            generation_assets.append(dict(raw))
    return {
        "schema_version": "1.3",
        "series_id": context.get("series_id"),
        "episode_project_id": context.get("episode_project_id"),
        "reused_assets": context.get("resolved_reuse_assets", []),
        "planner_verified_reuse_asset_ids": sorted(planner_reuse_ids),
        "forbidden_generation_asset_ids": sorted(reuse_ids),
        "excluded_reuse_assets": excluded,
        "generation_assets": generation_assets,
        "generation_count": len(generation_assets),
        "reuse_count": len(excluded),
        "created_at": utc_now(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepWhite 系列资产复用强校验 Gate")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify-registry")
    verify.add_argument("--series-root", required=True)
    plan = sub.add_parser("build-plan")
    plan.add_argument("--context", required=True)
    plan.add_argument("--requested-assets", required=True)
    plan.add_argument("--scene-handoff", help="可选：Scene Asset Planner 的 handoffs/scene_asset_handoff.json")
    plan.add_argument("--output", required=True)
    register = sub.add_parser("register-delta")
    register.add_argument("--series-root", required=True)
    register.add_argument("--asset-delta", required=True)
    register.add_argument("--episode-number", required=True, type=int)
    args = parser.parse_args()
    if args.command == "verify-registry":
        root = Path(args.series_root).expanduser().resolve()
        verified = verify_entire_registry(root, read_json(root / "asset_registry.json"))
        result = {"ok": True, "verified_count": len(verified), "assets": verified}
    elif args.command == "build-plan":
        context = read_json(Path(args.context).expanduser().resolve())
        requested = read_json(Path(args.requested_assets).expanduser().resolve())
        handoff = read_json(Path(args.scene_handoff).expanduser().resolve()) if args.scene_handoff else None
        result = build_generation_plan(context, requested, handoff)
        atomic_write_json(Path(args.output).expanduser().resolve(), result)
        result = {"ok": True, **result, "output": str(Path(args.output).expanduser().resolve())}
    else:
        root = Path(args.series_root).expanduser().resolve()
        delta = read_json(Path(args.asset_delta).expanduser().resolve())
        series_id = require_safe_id(delta.get("series_id"), "asset_delta.series_id")
        episode_project_id = require_safe_id(
            delta.get("episode_project_id"), "asset_delta.episode_project_id"
        )
        registry_path = root / "asset_registry.json"
        registry = canonicalize_asset_delta(
            root, read_json(registry_path), delta,
            series_id, episode_project_id, int(args.episode_number),
        )
        atomic_write_json(registry_path, registry)
        verified = verify_entire_registry(root, registry)
        result = {
            "ok": True, "event": "series_assets_registered",
            "registered_count": len(delta["assets"]),
            "verified_registry_count": len(verified),
            "asset_registry": str(registry_path),
        }
    json_result(result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(1)
