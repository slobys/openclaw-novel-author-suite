#!/usr/bin/env python3
"""Read one video job's durable state and emit a compact progress snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


VIDEO_ROOT = Path(
    os.environ.get("OPENCLAW_ASSET_ROOT", Path.home() / ".openclaw" / "data" / "openclaw-assets")
).expanduser()


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def as_int(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    args = parser.parse_args()

    project_path = args.project.expanduser().resolve()
    project = read_object(project_path)
    project_id = str(project.get("project_id") or "").strip()
    video_job_id = str(project.get("video_dispatch_job_id") or "").strip()
    if not project_id or not video_job_id:
        raise SystemExit("project_id and video_dispatch_job_id are required")

    evidence = project.get("video_execution_evidence")
    fixed_dir_value = evidence.get("fixed_output_directory") if isinstance(evidence, dict) else None
    job_dir = (
        Path(str(fixed_dir_value)).expanduser().resolve()
        if fixed_dir_value
        else (VIDEO_ROOT / project_id / "video_jobs" / video_job_id).resolve()
    )
    expected_dir = (VIDEO_ROOT / project_id / "video_jobs" / video_job_id).resolve()
    if job_dir != expected_dir:
        raise SystemExit("fixed video job directory does not match project_id/video_job_id")

    progress = read_object(job_dir / "progress.json")
    final_manifest = read_object(job_dir / "final_video_manifest.json")
    evidence_counts = project.get("video_execution_evidence")
    if not isinstance(evidence_counts, dict):
        evidence_counts = {}
    expected = as_int(progress.get("expected_count") or evidence_counts.get("expected_count"))
    completed = as_int(progress.get("completed_count"))
    failed = as_int(progress.get("failed_count"))
    queued = as_int(progress.get("queued_count"))
    running = as_int(progress.get("running_count"))
    project_status = str(project.get("status") or "unknown")
    progress_state = str(project.get("progress_state") or "unknown")
    progress_status = str(progress.get("status") or "waiting_for_queue_state")

    composed = (job_dir / ".composed").is_file()
    clips_done = (job_dir / ".done").is_file()
    terminal_failure = any(
        marker.is_file()
        for marker in (
            job_dir / ".compose_failed",
            job_dir / ".compose_terminal_failed",
            job_dir / ".terminal_failed",
        )
    )
    final_ready = project_status == "final_video_ready" and progress_state == "completed"
    project_failed = project_status.startswith("blocked_") or project_status.endswith("_failed")

    if final_ready:
        display_status = "completed"
        terminal = True
    elif project_failed or terminal_failure or failed:
        display_status = "failed"
        terminal = True
    elif composed and final_manifest.get("status") == "completed":
        display_status = "final_detected"
        terminal = False
    elif clips_done or (expected and completed == expected):
        display_status = "composing"
        terminal = False
    elif progress:
        display_status = "generating"
        terminal = False
    else:
        display_status = "accepted_waiting_queue_state"
        terminal = False

    snapshot: dict[str, Any] = {
        "schema_version": "1.0",
        "project_id": project_id,
        "video_job_id": video_job_id,
        "display_status": display_status,
        "terminal": terminal,
        "expected_count": expected,
        "completed_count": completed,
        "failed_count": failed,
        "queued_count": queued,
        "running_count": running,
        "progress_status": progress_status,
        "project_status": project_status,
        "progress_state": progress_state,
        "clips_done": clips_done,
        "composed": composed,
        "updated_at": progress.get("updated_at") or final_manifest.get("created_at") or project.get("updated_at"),
    }
    signature_source = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot["signature"] = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()
    print(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
