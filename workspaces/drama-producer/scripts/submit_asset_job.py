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
OPENCLAW_STATE_DIR = Path(
    os.environ.get("OPENCLAW_STATE_DIR", os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
).expanduser()
SKILLS_DIR = Path(os.environ.get("OPENCLAW_SKILLS_DIR", OPENCLAW_STATE_DIR / "skills")).expanduser()
HOST_ASSET_ROOT = Path(
    os.environ.get(
        "OPENCLAW_ASSET_SHARED_ROOT",
        os.environ.get("OPENCLAW_ASSET_ROOT", OPENCLAW_STATE_DIR / "data" / "openclaw-assets"),
    )
).expanduser()
N8N_ASSET_ROOT = Path(os.environ.get("N8N_ASSET_ROOT", "/data/openclaw-assets"))
REFERENCE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
REFERENCE_MAX_BYTES = 20 * 1024 * 1024
OPENAI_NATIVE_MULTIPART_MAX_REFERENCES = 2
VALIDATOR = ROOT / "scripts" / "validate_asset_render_specs.py"
RETRY_GUARD = ROOT / "scripts" / "asset_retry_guard.py"
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


def validate_reference_images_for_n8n(payload: dict) -> list[str]:
    """Validate n8n-visible paths and their host-side mounted files before dispatch."""
    errors: list[str] = []
    n8n_root = N8N_ASSET_ROOT.resolve()
    host_root = HOST_ASSET_ROOT.resolve()
    for asset_index, asset in enumerate(payload.get("assets") or []):
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("asset_id") or f"assets[{asset_index}]")
        references = asset.get("reference_images")
        if references is None:
            continue
        if not isinstance(references, list):
            errors.append(f"{asset_id}: reference_images 必须是数组")
            continue
        if len(references) > OPENAI_NATIVE_MULTIPART_MAX_REFERENCES:
            errors.append(
                f"{asset_id}: 当前 OpenAI 原生 multipart 分支最多支持 "
                f"{OPENAI_NATIVE_MULTIPART_MAX_REFERENCES} 张参考图，实际为 {len(references)} 张"
            )
            continue
        for reference_index, raw_path in enumerate(references):
            label = f"{asset_id}.reference_images[{reference_index}]"
            if not isinstance(raw_path, str) or not raw_path.strip():
                errors.append(f"{label}: 必须是非空字符串")
                continue
            n8n_path = Path(raw_path.strip())
            try:
                relative = n8n_path.resolve().relative_to(n8n_root)
            except ValueError:
                errors.append(
                    f"{label}: 必须使用 n8n 容器固定根 {N8N_ASSET_ROOT}/，"
                    f"不能使用宿主机路径"
                )
                continue
            host_path = (host_root / relative).resolve()
            try:
                host_path.relative_to(host_root)
            except ValueError:
                errors.append(f"{label}: 映射后超出宿主机固定资产根目录")
                continue
            try:
                stat = host_path.stat()
            except OSError as exc:
                errors.append(f"{label}: 宿主机映射文件不可读：{exc}")
                continue
            if not host_path.is_file() or stat.st_size <= 0 or stat.st_size > REFERENCE_MAX_BYTES:
                errors.append(f"{label}: 文件大小非法：{stat.st_size}")
            if host_path.suffix.lower() not in REFERENCE_EXTENSIONS:
                errors.append(f"{label}: 文件格式不受支持：{host_path.suffix}")
    return errors


def validate_partial_recovery(
    project_root: Path,
    payload: dict,
    missing_ids: set[str],
) -> list[str]:
    """Allow an immutable replacement Job to omit assets already accepted by its predecessor."""
    if not missing_ids:
        return []
    context = payload.get("recovery_context")
    if not isinstance(context, dict):
        return ["缺少计划生成资产：" + ", ".join(sorted(missing_ids))]
    source_job_id = str(context.get("source_job_id") or "")
    if not source_job_id or source_job_id != str(payload.get("supersedes_job_id") or ""):
        return ["recovery_context.source_job_id 必须等于 supersedes_job_id"]
    accepted_ids = {
        str(value)
        for value in (context.get("accepted_asset_ids") or [])
        if isinstance(value, str) and value
    }
    uncovered = missing_ids - accepted_ids
    errors = []
    if uncovered:
        errors.append("缺少计划生成资产：" + ", ".join(sorted(uncovered)))
    project_id = str(payload.get("project_id") or "")
    source_dir = (HOST_ASSET_ROOT / project_id / source_job_id).resolve()
    try:
        source_dir.relative_to(HOST_ASSET_ROOT.resolve())
    except ValueError:
        return errors + ["recovery_context 指向固定资产根目录之外"]
    for asset_id in sorted(missing_ids & accepted_ids):
        status_path = source_dir / "_status" / f"{asset_id}.json"
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
            filename = str(status.get("relative_path") or status.get("filename") or "")
            output_path = (source_dir / filename).resolve()
            output_path.relative_to(source_dir)
            stat = output_path.stat()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{asset_id}: 前序 Job accepted 证据不可验证：{exc}")
            continue
        if status.get("project_id") != project_id or status.get("job_id") != source_job_id:
            errors.append(f"{asset_id}: 前序 Job 状态标识不匹配")
        if status.get("asset_id") != asset_id or status.get("final_status") != "accepted":
            errors.append(f"{asset_id}: 前序 Job 未证明 accepted")
        if stat.st_size != status.get("file_size") or sha256_file(output_path) != status.get("sha256"):
            errors.append(f"{asset_id}: 前序 Job 输出大小或 SHA256 不匹配")
    return errors


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

    reference_errors = validate_reference_images_for_n8n(job_payload)
    if reference_errors:
        print("资产任务未提交：n8n 参考图执行边界 Gate 未通过", file=sys.stderr)
        for error in reference_errors:
            print(f"- {error}", file=sys.stderr)
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
            missing_ids = required_ids - submitted_ids
            reuse_overlap = sorted(reuse_ids & submitted_ids)
            recovery_errors = validate_partial_recovery(project_root, job_payload, missing_ids)
            if recovery_errors or reuse_overlap:
                for error in recovery_errors:
                    print(error, file=sys.stderr)
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
