#!/usr/bin/env python3
"""Workspace video submit entrypoint with mandatory reference-safety gate."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SAFETY_VALIDATOR = WORKSPACE_ROOT / "scripts" / "validate_video_reference_safety.py"
OPENCLAW_STATE_DIR = Path(
    os.environ.get("OPENCLAW_STATE_DIR", os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
).expanduser()
SKILLS_DIR = Path(os.environ.get("OPENCLAW_SKILLS_DIR", OPENCLAW_STATE_DIR / "skills")).expanduser()
DEPLOYED_UPSTREAM_SUBMITTER = Path(
    SKILLS_DIR / "deepwhite-n8n-video-dispatcher" / "scripts" / "submit_video_job.py"
)
UPSTREAM_SUBMITTER = (
    DEPLOYED_UPSTREAM_SUBMITTER
    if DEPLOYED_UPSTREAM_SUBMITTER.is_file()
    else WORKSPACE_ROOT.parents[1] / "skills" / "deepwhite-n8n-video-dispatcher" / "scripts" / "submit_video_job.py"
)
def project_root_from_job(job_path: Path) -> Path:
    resolved = job_path.expanduser().resolve()
    if resolved.parent.name != "video_jobs" or resolved.parent.parent.name != "dispatch":
        raise ValueError("video-job 必须位于项目 dispatch/video_jobs/ 目录")
    return resolved.parents[2]


def run(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: dict) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="安全校验并提交 DeepWhite 视频任务")
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        job_path = args.job.expanduser().resolve()
        project_root = project_root_from_job(job_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    actual_manifest = project_root / "assets" / "actual_asset_manifest.json"
    reference_manifest = project_root / "assets" / "video_reference_manifest.json"
    scene_handoff = project_root / "handoffs" / "scene_asset_handoff.json"
    binding_gate = project_root / "gates" / "video_scene_binding_gate.json"
    gate_code = run(
        [
            sys.executable,
            str(SAFETY_VALIDATOR),
            "--job",
            str(job_path),
            "--actual-manifest",
            str(actual_manifest),
            "--reference-manifest",
            str(reference_manifest),
        ]
    )
    if gate_code != 0:
        print("视频任务未提交：视频参考图安全 Gate 未通过", file=sys.stderr)
        return gate_code

    command = [
        sys.executable,
        str(UPSTREAM_SUBMITTER),
        "--job",
        str(job_path),
        "--scene-handoff",
        str(scene_handoff),
        "--assets",
        str(actual_manifest),
        "--binding-gate-out",
        str(binding_gate),
    ]
    if args.dry_run:
        command.append("--dry-run")
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0 or args.dry_run:
        return completed.returncode

    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError:
        response = {"raw_stdout": completed.stdout[-2000:]}
    atomic_write_json(
        project_root / "dispatch" / "last_video_submission.json",
        {
            "schema_version": "1.0",
            "video_job_id": json.loads(job_path.read_text(encoding="utf-8")).get("video_job_id"),
            "payload_sha256": sha256_file(job_path),
            "status": response.get("status") or "webhook_accepted_unverified",
            "http_status": response.get("http_status"),
            "execution_id": response.get("execution_id"),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "response": response,
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
