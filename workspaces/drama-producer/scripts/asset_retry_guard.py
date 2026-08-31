#!/usr/bin/env python3
"""Cross-job semantic retry budget and circuit breaker for image assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_ATTEMPTS_DEFAULT = 3
NONTERMINAL = {"reserved", "webhook_accepted_unverified", "execution_confirmed", "generating"}
FINAL_RETRYABLE = {"rejected", "failed", "transport_failed", "cancelled"}
STATUSES = NONTERMINAL | FINAL_RETRYABLE | {"accepted", "held_for_asset_review"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} 顶层必须为 object")
    return data


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def canonical_sha(data: Any) -> str:
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_root(job_path: Path) -> Path:
    if job_path.parent.name != "asset_jobs" or job_path.parent.parent.name != "dispatch":
        raise ValueError("asset job 必须位于 project/dispatch/asset_jobs/")
    return job_path.parents[2]


def ledger_path(job_path: Path) -> Path:
    return project_root(job_path) / "state" / "asset_attempt_ledger.json"


def empty_ledger(max_attempts: int) -> dict[str, Any]:
    return {"schema_version": "1.0", "max_generation_attempts": max_attempts, "lineages": {}, "updated_at": now()}


def load_ledger(path: Path, max_attempts: int) -> dict[str, Any]:
    if not path.is_file():
        return empty_ledger(max_attempts)
    ledger = load(path)
    ledger.setdefault("lineages", {})
    ledger.setdefault("max_generation_attempts", max_attempts)
    return ledger


def asset_records(job: dict[str, Any], payload_sha: str, errors: list[str]) -> list[dict[str, Any]]:
    rows = job.get("assets")
    if not isinstance(rows, list) or not rows:
        errors.append("asset job.assets 必须为非空数组")
        return []
    job_id = str(job.get("job_id") or "")
    if not job_id:
        errors.append("asset job 缺少 job_id")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"assets[{index}] 必须为 object"); continue
        asset_id = str(row.get("asset_id") or "")
        lineage_id = str(row.get("asset_lineage_id") or "")
        requirement_sha = str(row.get("requirement_sha256") or "").lower()
        reason = str(row.get("revision_reason_code") or "")
        if not asset_id or not lineage_id or len(requirement_sha) != 64 or not reason:
            errors.append(f"{asset_id or f'assets[{index}]'}: 缺少 asset_lineage_id/64位 requirement_sha256/revision_reason_code")
            continue
        lineage_key = canonical_sha({"asset_lineage_id": lineage_id, "requirement_sha256": requirement_sha})
        if lineage_key in seen:
            errors.append(f"同一 Job 重复 lineage+requirement：{lineage_id}")
        seen.add(lineage_key)
        prompt_sha = canonical_sha({
            "prompt": row.get("prompt"), "negative_prompt": row.get("negative_prompt"),
            "style_hard_constraint": row.get("style_hard_constraint"), "angle_id": row.get("angle_id"),
            "reference_asset_ids": row.get("reference_asset_ids"),
        })
        result.append({
            "lineage_key": lineage_key, "asset_lineage_id": lineage_id,
            "requirement_sha256": requirement_sha, "asset_id": asset_id,
            "job_id": job_id, "payload_sha256": payload_sha,
            "prompt_sha256": prompt_sha, "revision_reason_code": reason,
        })
    return result


def evaluate(ledger: dict[str, Any], records: list[dict[str, Any]], max_attempts: int) -> list[str]:
    errors: list[str] = []
    lineages = ledger.get("lineages") or {}
    for record in records:
        entry = lineages.get(record["lineage_key"]) or {}
        attempts = entry.get("attempts") or []
        same_job = next((row for row in attempts if row.get("job_id") == record["job_id"]), None)
        if same_job:
            if same_job.get("payload_sha256") != record["payload_sha256"]:
                errors.append(f"{record['asset_lineage_id']}: 同一 job_id 不得更换 payload")
            elif same_job.get("status") != "transport_failed":
                errors.append(
                    f"{record['asset_lineage_id']}: Job {record['job_id']} 已记录为 "
                    f"{same_job.get('status')}，仅 transport_failed 可原 Job 重传"
                )
            continue
        if entry.get("status") == "accepted" or any(row.get("status") == "accepted" for row in attempts):
            errors.append(f"{record['asset_lineage_id']}: 已有 accepted 资产，禁止再次生成")
            continue
        active = [row for row in attempts if row.get("status") in NONTERMINAL]
        if active:
            errors.append(f"{record['asset_lineage_id']}: 仍有未终结 Job {active[-1].get('job_id')}")
            continue
        if len(attempts) >= max_attempts:
            errors.append(f"{record['asset_lineage_id']}: 已达到总生成上限 {max_attempts}，必须人工审核")
            continue
        if attempts and record["revision_reason_code"] == "initial":
            errors.append(f"{record['asset_lineage_id']}: 后续尝试不得使用 revision_reason_code=initial")
        if any(row.get("prompt_sha256") == record["prompt_sha256"] and row.get("status") in {"rejected", "failed"} for row in attempts):
            errors.append(f"{record['asset_lineage_id']}: 被拒绝/失败后不得原样重复同一 prompt")
    return errors


def command_check(job_path: Path, max_attempts: int) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    job = load(job_path)
    errors: list[str] = []
    records = asset_records(job, file_sha(job_path), errors)
    path = ledger_path(job_path)
    ledger = load_ledger(path, max_attempts)
    errors.extend(evaluate(ledger, records, max_attempts))
    return ledger, {"schema_version": "1.0", "passed": not errors, "job_id": job.get("job_id"), "errors": errors}, records


def reserve(job_path: Path, max_attempts: int) -> dict[str, Any]:
    ledger, report, records = command_check(job_path, max_attempts)
    if not report["passed"]:
        return report
    lineages = ledger.setdefault("lineages", {})
    for record in records:
        entry = lineages.setdefault(record["lineage_key"], {
            "asset_lineage_id": record["asset_lineage_id"],
            "requirement_sha256": record["requirement_sha256"], "attempts": [],
        })
        existing = next((row for row in entry["attempts"] if row.get("job_id") == record["job_id"]), None)
        if existing is None:
            existing = {**record, "status": "reserved", "reserved_at": now(), "history": [{"status": "reserved", "at": now()}]}
            entry["attempts"].append(existing)
        entry["status"] = existing.get("status")
    ledger["updated_at"] = now()
    atomic_write(ledger_path(job_path), ledger)
    return {**report, "event": "reserved", "reserved_asset_count": len(records), "ledger_path": str(ledger_path(job_path))}


def update_status(
    job_path: Path,
    status: str,
    max_attempts: int,
    reason_code: str | None,
    evidence: str | None,
    asset_ids: set[str] | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"未知 status：{status}")
    job = load(job_path)
    parse_errors: list[str] = []
    records = asset_records(job, file_sha(job_path), parse_errors)
    if parse_errors:
        return {"schema_version": "1.0", "passed": False, "errors": parse_errors}
    if asset_ids:
        known_ids = {record["asset_id"] for record in records}
        unknown_ids = sorted(asset_ids - known_ids)
        if unknown_ids:
            return {"schema_version": "1.0", "passed": False, "errors": [
                "Job 中不存在 asset_id：" + ", ".join(unknown_ids)
            ]}
        records = [record for record in records if record["asset_id"] in asset_ids]
    path = ledger_path(job_path)
    ledger = load_ledger(path, max_attempts)
    errors: list[str] = []
    for record in records:
        entry = (ledger.get("lineages") or {}).get(record["lineage_key"])
        attempt = next((row for row in (entry or {}).get("attempts", []) if row.get("job_id") == record["job_id"]), None)
        if not attempt:
            errors.append(f"{record['asset_lineage_id']}: Job 尚未 reserve")
            continue
        old = attempt.get("status")
        if old == "accepted" and status != "accepted":
            errors.append(f"{record['asset_lineage_id']}: accepted 状态不可回退"); continue
        if status in {"rejected", "failed"} and not reason_code:
            errors.append(f"{record['asset_lineage_id']}: {status} 必须提供 --reason-code"); continue
        attempt["status"] = status
        attempt["updated_at"] = now()
        if reason_code:
            attempt["result_reason_code"] = reason_code
        if evidence:
            attempt["evidence"] = evidence
        attempt.setdefault("history", []).append({"status": status, "reason_code": reason_code, "at": now()})
        entry["status"] = status
        if status in FINAL_RETRYABLE and len(entry["attempts"]) >= max_attempts:
            entry["status"] = "held_for_asset_review"
    if errors:
        return {"schema_version": "1.0", "passed": False, "errors": errors}
    ledger["updated_at"] = now()
    atomic_write(path, ledger)
    return {"schema_version": "1.0", "passed": True, "event": "status_updated", "status": status, "asset_count": len(records)}


def main() -> int:
    parser = argparse.ArgumentParser(description="资产跨 Job 重试预算与熔断")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "reserve"):
        command = sub.add_parser(name)
        command.add_argument("--job", required=True, type=Path)
        command.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS_DEFAULT)
        command.add_argument("--out", type=Path)
    update = sub.add_parser("update")
    update.add_argument("--job", required=True, type=Path)
    update.add_argument("--status", required=True, choices=sorted(STATUSES))
    update.add_argument("--reason-code")
    update.add_argument("--evidence")
    update.add_argument("--asset-id", action="append", default=[])
    update.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS_DEFAULT)
    update.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        job_path = args.job.expanduser().resolve()
        if args.max_attempts < 1:
            raise ValueError("max-attempts 必须大于 0")
        if args.command == "check":
            _, report, _ = command_check(job_path, args.max_attempts)
        elif args.command == "reserve":
            report = reserve(job_path, args.max_attempts)
        else:
            report = update_status(
                job_path,
                args.status,
                args.max_attempts,
                args.reason_code,
                args.evidence,
                set(args.asset_id),
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {"schema_version": "1.0", "passed": False, "errors": [str(exc)]}
    if args.out:
        atomic_write(args.out.expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
