#!/usr/bin/env python3
"""Validate a complete angle pack while reusing hash-bound approved members."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPENCLAW_HOME = Path(
    os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw"))
).expanduser().resolve()
HOST_ASSET_ROOT = Path(
    os.environ.get("OPENCLAW_ASSET_SHARED_ROOT", str(ROOT / "shared-assets"))
).expanduser().resolve()
N8N_ASSET_ROOT = Path("/data/openclaw-assets")
BASE_VALIDATOR = OPENCLAW_HOME / "skills/deepwhite-image-prompt-builder/scripts/validate_angle_pack.py"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须为 object")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def host_path(raw_path: str) -> Path:
    relative = Path(raw_path).resolve().relative_to(N8N_ASSET_ROOT.resolve())
    resolved = (HOST_ASSET_ROOT / relative).resolve()
    resolved.relative_to(HOST_ASSET_ROOT.resolve())
    return resolved


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def load_base_validator():
    spec = importlib.util.spec_from_file_location("deepwhite_validate_angle_pack", BASE_VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载部署的 angle-pack validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    try:
        manifest = load(args.manifest.resolve())
        job = load(args.job.resolve())
        manifest_rows = {
            str(row.get("asset_id")): row
            for pack in (manifest.get("packs") or []) if isinstance(pack, dict)
            for row in (pack.get("assets") or []) if isinstance(row, dict) and row.get("asset_id")
        }
        synthetic = copy.deepcopy(job)
        synthetic.setdefault("assets", [])
        submitted_ids = {
            str(row.get("asset_id")) for row in synthetic["assets"] if isinstance(row, dict)
        }
        reused_ids: list[str] = []
        for index, reuse in enumerate(job.get("angle_pack_reuse_assets") or []):
            label = f"angle_pack_reuse_assets[{index}]"
            if not isinstance(reuse, dict):
                errors.append(f"{label} 必须为 object")
                continue
            asset_id = str(reuse.get("asset_id") or "")
            source_job_id = str(reuse.get("source_job_id") or "")
            raw_path = str(reuse.get("path") or "")
            declared_hash = str(reuse.get("sha256") or "").removeprefix("sha256:")
            declared_size = reuse.get("file_size")
            declared = manifest_rows.get(asset_id)
            if not asset_id or not source_job_id or not raw_path or not declared_hash or not isinstance(declared_size, int):
                errors.append(f"{label} 缺少 asset_id/source_job_id/path/file_size/sha256")
                continue
            if asset_id in submitted_ids:
                errors.append(f"{asset_id}: 复用成员不得同时出现在待生成 assets")
                continue
            if declared is None:
                errors.append(f"{asset_id}: 完整 angle-pack manifest 未声明该复用成员")
                continue
            try:
                image_path = host_path(raw_path)
                status_path = HOST_ASSET_ROOT / str(job.get("project_id")) / source_job_id / "_status" / f"{asset_id}.json"
                status = load(status_path)
                stat = image_path.stat()
                actual_hash = sha256_file(image_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{asset_id}: 复用证据不可验证：{exc}")
                continue
            if status.get("project_id") != job.get("project_id") or status.get("job_id") != source_job_id:
                errors.append(f"{asset_id}: 复用状态的项目或 Job 标识不匹配")
            if status.get("asset_id") != asset_id or status.get("final_status") != "accepted":
                errors.append(f"{asset_id}: 复用成员不是严格 accepted")
            if status.get("acceptance_mode") != "strict_review":
                errors.append(f"{asset_id}: 复用成员不是 strict_review")
            if stat.st_size != declared_size or status.get("file_size") != declared_size:
                errors.append(f"{asset_id}: 复用文件大小不匹配")
            if actual_hash != declared_hash or str(status.get("sha256") or "").removeprefix("sha256:") != declared_hash:
                errors.append(f"{asset_id}: 复用 SHA256 不匹配")
            synthetic["assets"].append(copy.deepcopy(declared))
            reused_ids.append(asset_id)

        base_report = load_base_validator().validate(manifest, synthetic)
        errors.extend(base_report.get("errors") or [])
        report = {
            **base_report,
            "passed": not errors,
            "errors": errors,
            "submitted_asset_count": len(job.get("assets") or []),
            "approved_reuse_asset_count": len(reused_ids),
            "approved_reuse_asset_ids": reused_ids,
        }
    except Exception as exc:
        report = {"schema_version": "1.0", "passed": False, "errors": [str(exc)], "warnings": []}

    if args.out:
        atomic_write(args.out.resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
