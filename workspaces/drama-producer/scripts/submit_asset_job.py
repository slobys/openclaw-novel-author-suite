#!/usr/bin/env python3
"""Workspace asset submit entrypoint with mandatory per-asset render-spec gate."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_asset_render_specs.py"
RETRY_GUARD = ROOT / "scripts" / "asset_retry_guard.py"
OPENCLAW_STATE_DIR = Path(
    os.environ.get("OPENCLAW_STATE_DIR", os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
).expanduser()
SKILLS_DIR = Path(os.environ.get("OPENCLAW_SKILLS_DIR", OPENCLAW_STATE_DIR / "skills")).expanduser()
DEPLOYED_UPSTREAM = SKILLS_DIR / "deepwhite-n8n-asset-dispatcher" / "scripts" / "send-assets-to-n8n.mjs"
DEPLOYED_PROMPT_VALIDATOR = Path(
    SKILLS_DIR / "deepwhite-image-prompt-builder" / "scripts" / "validate_location_prompt_manifest.py"
)
UPSTREAM = DEPLOYED_UPSTREAM if DEPLOYED_UPSTREAM.is_file() else ROOT.parents[1] / "skills" / "deepwhite-n8n-asset-dispatcher" / "scripts" / "send-assets-to-n8n.mjs"
PROMPT_VALIDATOR = DEPLOYED_PROMPT_VALIDATOR if DEPLOYED_PROMPT_VALIDATOR.is_file() else ROOT.parents[1] / "skills" / "deepwhite-image-prompt-builder" / "scripts" / "validate_location_prompt_manifest.py"
DEPLOYED_ANGLE_VALIDATOR = Path(
    SKILLS_DIR / "deepwhite-image-prompt-builder" / "scripts" / "validate_angle_pack.py"
)
ANGLE_VALIDATOR = DEPLOYED_ANGLE_VALIDATOR if DEPLOYED_ANGLE_VALIDATOR.is_file() else ROOT.parents[1] / "skills" / "deepwhite-image-prompt-builder" / "scripts" / "validate_angle_pack.py"


def project_root_from_job(job_path: Path) -> Path:
    if job_path.parent.name != "asset_jobs" or job_path.parent.parent.name != "dispatch":
        raise ValueError("asset-job 必须位于项目 dispatch/asset_jobs/ 目录")
    return job_path.parents[2]


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


def auto_retry_guard_required(project_root: Path, payload: dict) -> bool:
    contract = project_root / "input" / "production_pipeline_contract.json"
    if contract.is_file():
        try:
            if json.loads(contract.read_text(encoding="utf-8")).get("pipeline_profile") == "scene_bound_auto_v1.2":
                return True
        except (OSError, json.JSONDecodeError):
            return True
    return any(isinstance(row, dict) and row.get("asset_lineage_id") for row in (payload.get("assets") or []))


def run_guard(job: Path, command: str, *extra: str) -> int:
    completed = subprocess.run(
        [sys.executable, str(RETRY_GUARD), command, "--job", str(job), *extra],
        check=False, capture_output=True, text=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="安全校验并提交 DeepWhite 资产任务")
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        job = args.job.expanduser().resolve()
        project_root = project_root_from_job(job)
        job_payload = json.loads(job.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"asset-job 不可读：{exc}", file=sys.stderr)
        return 2

    requirements = project_root / "assets" / "location_asset_requirements.json"
    manifest = project_root / "assets" / "location_asset_prompt_manifest.json"
    if requirements.is_file():
        try:
            requirement_payload = json.loads(requirements.read_text(encoding="utf-8"))
            generation = requirement_payload.get("generation_requirements") or []
        except (OSError, json.JSONDecodeError) as exc:
            print(f"场景资产需求文件不可读：{exc}", file=sys.stderr)
            return 2
        if generation:
            if not manifest.is_file():
                print("缺少 assets/location_asset_prompt_manifest.json", file=sys.stderr)
                return 2
            gate_out = project_root / "gates" / "location_prompt_manifest_gate.json"
            prompt_gate = subprocess.run(
                [
                    sys.executable,
                    str(PROMPT_VALIDATOR),
                    "--requirements",
                    str(requirements),
                    "--manifest",
                    str(manifest),
                    "--gate-out",
                    str(gate_out),
                ],
                check=False,
            )
            if prompt_gate.returncode != 0:
                print("资产任务未提交：Location Prompt Manifest Gate 未通过", file=sys.stderr)
                return prompt_gate.returncode
            required_ids = {str(row.get("asset_id")) for row in generation if isinstance(row, dict) and row.get("asset_id")}
            reuse_ids = {
                str(row.get("asset_id"))
                for row in (requirement_payload.get("reuse_assets") or [])
                if isinstance(row, dict) and row.get("asset_id")
            }
            submitted_ids = {
                str(row.get("asset_id"))
                for row in (job_payload.get("assets") or [])
                if isinstance(row, dict) and row.get("asset_id")
            }
            missing_ids = sorted(required_ids - submitted_ids)
            reuse_overlap = sorted(reuse_ids & submitted_ids)
            if missing_ids or reuse_overlap:
                if missing_ids:
                    print("asset-job 缺少计划生成资产：" + ", ".join(missing_ids), file=sys.stderr)
                if reuse_overlap:
                    print("asset-job 错误包含复用资产：" + ", ".join(reuse_overlap), file=sys.stderr)
                return 2

    gate = subprocess.run([sys.executable, str(VALIDATOR), "--job", str(job)], check=False)
    if gate.returncode != 0:
        print("资产任务未提交：单图与分类画幅 Gate 未通过", file=sys.stderr)
        return gate.returncode

    angle_pack_ids = {
        str(row.get("angle_pack_id"))
        for row in (job_payload.get("assets") or [])
        if isinstance(row, dict) and row.get("angle_pack_id")
    }
    if angle_pack_ids:
        angle_manifest = project_root / "assets" / "angle_pack_manifest.json"
        if not angle_manifest.is_file():
            print("资产任务未提交：缺少 assets/angle_pack_manifest.json", file=sys.stderr)
            return 2
        angle_gate = subprocess.run(
            [sys.executable, str(ANGLE_VALIDATOR), "--manifest", str(angle_manifest), "--job", str(job),
             "--out", str(project_root / "gates" / "angle_pack_gate.json")],
            check=False,
        )
        if angle_gate.returncode != 0:
            print("资产任务未提交：独立多视角资产包 Gate 未通过", file=sys.stderr)
            return angle_gate.returncode

    use_retry_guard = auto_retry_guard_required(project_root, job_payload)
    guard_command = "check" if args.dry_run else "reserve"
    retry_gate = project_root / "gates" / "asset_retry_budget_gate.json"
    if use_retry_guard and run_guard(job, guard_command, "--out", str(retry_gate)) != 0:
        print("资产任务未提交：跨 Job 重试预算 Gate 未通过", file=sys.stderr)
        return 2
    command = ["node", str(UPSTREAM), str(job)]
    if args.dry_run:
        command.append("--dry-run")
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        if use_retry_guard and not args.dry_run:
            match = re.search(r"HTTP\s+([0-9]{3})", completed.stderr or "")
            http_status = int(match.group(1)) if match else None
            permanent_client_error = http_status is not None and 400 <= http_status < 500 and http_status not in {408, 429}
            if permanent_client_error:
                run_guard(job, "update", "--status", "failed", "--reason-code", f"dispatcher_http_{http_status}")
            else:
                run_guard(job, "update", "--status", "transport_failed", "--reason-code", "dispatcher_transport_error")
        return completed.returncode
    if args.dry_run:
        return completed.returncode

    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError:
        response = {"raw_stdout": completed.stdout[-2000:]}
    atomic_write_json(
        project_root / "dispatch" / "last_submission.json",
        {
            "schema_version": "1.0",
            "job_id": job_payload.get("job_id"),
            "payload_sha256": sha256_file(job),
            "status": response.get("status") or "webhook_accepted_unverified",
            "http_status": response.get("http_status"),
            "execution_id": response.get("execution_id"),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "response": response,
        },
    )
    if use_retry_guard:
        submitted_status = response.get("status") or "webhook_accepted_unverified"
        if submitted_status not in {"webhook_accepted_unverified", "execution_confirmed"}:
            submitted_status = "webhook_accepted_unverified"
        guard_result = run_guard(job, "update", "--status", submitted_status)
        if guard_result != 0:
            print("Webhook 已返回，但资产重试账本状态更新失败；禁止自动重发", file=sys.stderr)
            return guard_result
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
