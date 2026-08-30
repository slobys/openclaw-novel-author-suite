#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from validate_video_scene_bindings import validate_job

SUCCESS_CODES = {200, 201, 202, 204}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_top_level(payload: dict) -> None:
    required = ["project_id", "video_job_id", "source_asset_job_id", "clips"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"缺少必填字段: {', '.join(missing)}")
    if not isinstance(payload["clips"], list) or not payload["clips"]:
        raise ValueError("clips 必须是非空数组")


def write_gate(gate: dict, path: Path | None) -> None:
    if not path:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="提交 DeepWhite 视频任务到 n8n（含场景绑定 Gate）")
    parser.add_argument("--job", required=True, help="video_job.json 路径")
    parser.add_argument("--scene-handoff", required=True, help="scene_asset_handoff.json 路径")
    parser.add_argument("--assets", required=True, help="actual_asset_manifest.json 路径")
    parser.add_argument("--binding-gate-out", help="保存 video_scene_binding_gate.json")
    parser.add_argument("--dry-run", action="store_true", help="只校验，不发送")
    args = parser.parse_args()

    job_path = Path(args.job).expanduser().resolve()
    handoff_path = Path(args.scene_handoff).expanduser().resolve()
    assets_path = Path(args.assets).expanduser().resolve()
    gate_out = Path(args.binding_gate_out).expanduser().resolve() if args.binding_gate_out else None

    for label, path in (("任务文件", job_path), ("Scene Asset Handoff", handoff_path), ("Actual Asset Manifest", assets_path)):
        if not path.is_file():
            print(f"{label}不存在: {path}", file=sys.stderr)
            return 2

    try:
        payload = load_json(job_path)
        handoff = load_json(handoff_path)
        assets = load_json(assets_path)
        validate_top_level(payload)
        gate = validate_job(payload, handoff, assets)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"任务校验失败: {exc}", file=sys.stderr)
        return 2

    write_gate(gate, gate_out)
    if not gate.get("passed"):
        safe_errors = gate.get("errors", [])[:20]
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "video_scene_binding_gate_failed",
                    "video_job_id": payload.get("video_job_id"),
                    "errors": safe_errors,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    summary = {
        "project_id": payload["project_id"],
        "video_job_id": payload["video_job_id"],
        "clip_count": len(payload["clips"]),
        "scene_binding_gate": "passed",
    }

    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, **summary}, ensure_ascii=False))
        return 0

    webhook_url = os.environ.get("N8N_VIDEO_WEBHOOK_URL", "").strip()
    webhook_secret = os.environ.get("N8N_VIDEO_WEBHOOK_SECRET", "").strip()
    if not webhook_url or not webhook_secret:
        print("缺少 N8N_VIDEO_WEBHOOK_URL 或 N8N_VIDEO_WEBHOOK_SECRET", file=sys.stderr)
        return 3

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-openclaw-video-secret": webhook_secret,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = int(response.status)
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        response_body = exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        print(f"n8n 请求失败: {exc}", file=sys.stderr)
        return 4

    if status not in SUCCESS_CODES:
        safe_body = response_body[:1000]
        print(f"n8n 返回 HTTP {status}: {safe_body}", file=sys.stderr)
        return 5

    try:
        response_json = json.loads(response_body) if response_body.strip() else {}
    except json.JSONDecodeError:
        response_json = {}
    execution_id = None
    if isinstance(response_json, dict):
        execution_id = (
            response_json.get("execution_id")
            or response_json.get("executionId")
            or response_json.get("task_id")
            or response_json.get("taskId")
            or response_json.get("provider_task_id")
        )
    acceptance_status = "execution_confirmed" if execution_id else "webhook_accepted_unverified"
    print(
        json.dumps(
            {
                "ok": True,
                "http_status": status,
                "status": acceptance_status,
                "execution_id": execution_id,
                **summary,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
