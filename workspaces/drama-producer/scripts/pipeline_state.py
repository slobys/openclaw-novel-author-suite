#!/usr/bin/env python3
"""Deterministic pipeline checkpoint and external-job state manager."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PIPELINE_PROFILE = "scene_bound_auto_v1.2"
STAGE_ORDER = (0, 10, 20, 25, 30, 35, 37, 40, 45, 50, 52, 55, 60, 65, 70, 80, 90, 95, 100)
GATE_STAGES = {25, 35, 37, 52, 55, 70, 95}
STAGE_PREREQUISITES = {
    10: (0,),
    20: (10,),
    25: (20,),
    30: (25,),
    35: (30,),
    37: (35,),
    40: (37,),
    45: (40,),
    50: (45,),
    52: (50,),
    55: (52,),
    60: (55,),
    65: (55,),
    70: (65,),
    80: (70,),
    90: (80,),
    95: (90,),
    100: (95,),
}
JOB_STATUS_ORDER = (
    "prepared",
    "validated",
    "webhook_accepted_unverified",
    "execution_confirmed",
    "generating",
    "callback_received",
    "verified",
    "terminal",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层必须为 JSON object")
    return data


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def state_path(project_root: Path) -> Path:
    return project_root / "state" / "pipeline_state.json"


def resolved_project_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"项目目录不存在：{root}")
    return root


def safe_artifact(project_root: Path, value: str | Path) -> Path:
    raw = Path(value)
    path = raw.resolve() if raw.is_absolute() else (project_root / raw).resolve()
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"证据文件超出项目目录：{path}") from exc
    if not path.is_file() or path.stat().st_size <= 0:
        raise ValueError(f"证据文件不存在或为空：{path}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_state(project_root: Path) -> tuple[Path, dict[str, Any]]:
    path = state_path(project_root)
    if not path.is_file():
        raise ValueError("缺少 state/pipeline_state.json；先执行 init")
    state = read_json(path)
    if state.get("pipeline_profile") != PIPELINE_PROFILE:
        raise ValueError("pipeline_profile 不匹配")
    return path, state


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    root = resolved_project_root(args.project_root)
    path = state_path(root)
    if path.exists():
        state = read_json(path)
        return {"ok": True, "event": "already_initialized", "state": state}
    state = {
        "schema_version": "1.0",
        "pipeline_profile": PIPELINE_PROFILE,
        "project_id": args.project_id,
        "revision": 0,
        "current_stage": 0,
        "current_status": "initialized",
        "stages": {str(stage): {"status": "pending"} for stage in STAGE_ORDER},
        "jobs": {"asset": {}, "video": {}},
        "job_archive": {"asset": [], "video": []},
        "invalidations": [],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    state["stages"]["0"] = {"status": "completed", "completed_at": utc_now(), "artifacts": {}}
    atomic_write_json(path, state)
    return {"ok": True, "event": "initialized", "state_path": str(path)}


def gate_passed(path: Path) -> bool:
    gate = read_json(path)
    return gate.get("passed") is True or gate.get("ok") is True or gate.get("gate_passed") is True


def command_complete_stage(args: argparse.Namespace) -> dict[str, Any]:
    root = resolved_project_root(args.project_root)
    path, state = load_state(root)
    stage = int(args.stage)
    if stage not in STAGE_ORDER:
        raise ValueError(f"未知阶段：{stage}")
    missing_prerequisites = [
        required
        for required in STAGE_PREREQUISITES.get(stage, ())
        if state["stages"].get(str(required), {}).get("status") != "completed"
    ]
    if missing_prerequisites:
        raise ValueError(
            "前置阶段未完成：" + ", ".join(str(value) for value in missing_prerequisites)
        )
    artifacts: dict[str, dict[str, Any]] = {}
    for value in args.artifact or []:
        artifact = safe_artifact(root, value)
        relative = artifact.relative_to(root).as_posix()
        artifacts[relative] = {"sha256": sha256_file(artifact), "size": artifact.stat().st_size}
    if stage != 0 and not artifacts:
        raise ValueError("完成阶段至少需要一个 --artifact 证据文件")
    if stage in GATE_STAGES:
        if not args.gate:
            raise ValueError(f"Stage {stage} 必须提供 --gate")
        gate = safe_artifact(root, args.gate)
        if not gate_passed(gate):
            raise ValueError(f"Gate 未通过：{gate}")
        relative = gate.relative_to(root).as_posix()
        artifacts.setdefault(relative, {"sha256": sha256_file(gate), "size": gate.stat().st_size})

    previous = state["stages"].get(str(stage), {})
    if previous.get("status") == "completed" and previous.get("artifacts") == artifacts:
        return {"ok": True, "event": "already_completed", "stage": stage}

    state["stages"][str(stage)] = {
        "status": "completed",
        "completed_at": utc_now(),
        "artifacts": artifacts,
    }
    state["current_stage"] = max(int(state.get("current_stage", 0)), stage)
    state["current_status"] = args.status or "stage_completed"
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = utc_now()
    atomic_write_json(path, state)
    return {"ok": True, "event": "stage_completed", "stage": stage, "artifact_count": len(artifacts)}


def command_invalidate(args: argparse.Namespace) -> dict[str, Any]:
    root = resolved_project_root(args.project_root)
    path, state = load_state(root)
    start = int(args.from_stage)
    if start not in STAGE_ORDER:
        raise ValueError(f"未知阶段：{start}")
    invalidated = []
    for stage in STAGE_ORDER:
        if stage < start:
            continue
        entry = state["stages"].setdefault(str(stage), {})
        if entry.get("status") != "pending":
            invalidated.append(stage)
        state["stages"][str(stage)] = {"status": "pending"}
    completed = [stage for stage in STAGE_ORDER if state["stages"].get(str(stage), {}).get("status") == "completed"]
    state["current_stage"] = max(completed, default=0)
    state["current_status"] = "needs_regeneration"
    state["invalidations"].append({
        "from_stage": start,
        "reason": args.reason,
        "invalidated_stages": invalidated,
        "at": utc_now(),
    })
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = utc_now()
    atomic_write_json(path, state)
    return {"ok": True, "event": "invalidated", "from_stage": start, "invalidated_stages": invalidated}


def command_record_job(args: argparse.Namespace) -> dict[str, Any]:
    root = resolved_project_root(args.project_root)
    path, state = load_state(root)
    payload = safe_artifact(root, args.payload)
    payload_sha = sha256_file(payload)
    existing = state["jobs"].get(args.kind) or {}
    if existing:
        if existing.get("job_id") != args.job_id and existing.get("status") != "terminal":
            raise ValueError(f"{args.kind} 已有未终结 job_id：{existing.get('job_id')}")
        if existing.get("job_id") != args.job_id and existing.get("status") == "terminal":
            state.setdefault("job_archive", {}).setdefault(args.kind, []).append(existing)
            existing = {}
        if existing.get("job_id") == args.job_id and existing.get("payload_sha256") != payload_sha:
            raise ValueError("同一 job_id 不得对应不同 payload_sha256")
        old_status = existing.get("status")
        if old_status in JOB_STATUS_ORDER:
            if JOB_STATUS_ORDER.index(args.status) < JOB_STATUS_ORDER.index(old_status):
                raise ValueError(f"Job 状态不得回退：{old_status} -> {args.status}")

    job = {
        **existing,
        "job_id": args.job_id,
        "status": args.status,
        "payload_path": payload.relative_to(root).as_posix(),
        "payload_sha256": payload_sha,
        "updated_at": utc_now(),
    }
    if args.http_status is not None:
        job["http_status"] = args.http_status
    if args.execution_id:
        job["execution_id"] = args.execution_id
    history = list(job.get("history") or [])
    history.append({"status": args.status, "at": utc_now()})
    job["history"] = history
    state["jobs"][args.kind] = job
    state["revision"] = int(state.get("revision", 0)) + 1
    state["updated_at"] = utc_now()
    atomic_write_json(path, state)
    return {"ok": True, "event": "job_recorded", "kind": args.kind, "job_id": args.job_id, "status": args.status}


def command_show(args: argparse.Namespace) -> dict[str, Any]:
    root = resolved_project_root(args.project_root)
    _, state = load_state(root)
    return {"ok": True, "state": state}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理 DeepWhite 单集生产检查点")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--project-root", required=True)
    init.add_argument("--project-id", required=True)

    complete = sub.add_parser("complete-stage")
    complete.add_argument("--project-root", required=True)
    complete.add_argument("--stage", required=True, type=int)
    complete.add_argument("--artifact", action="append")
    complete.add_argument("--gate")
    complete.add_argument("--status")

    invalidate = sub.add_parser("invalidate")
    invalidate.add_argument("--project-root", required=True)
    invalidate.add_argument("--from-stage", required=True, type=int)
    invalidate.add_argument("--reason", required=True)

    job = sub.add_parser("record-job")
    job.add_argument("--project-root", required=True)
    job.add_argument("--kind", choices=("asset", "video"), required=True)
    job.add_argument("--job-id", required=True)
    job.add_argument("--status", choices=JOB_STATUS_ORDER, required=True)
    job.add_argument("--payload", required=True)
    job.add_argument("--http-status", type=int)
    job.add_argument("--execution-id")

    show = sub.add_parser("show")
    show.add_argument("--project-root", required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handlers = {
        "init": command_init,
        "complete-stage": command_complete_stage,
        "invalidate": command_invalidate,
        "record-job": command_record_job,
        "show": command_show,
    }
    try:
        result = handlers[args.command](args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
