#!/usr/bin/env python3
"""Build canonical asset manifests from n8n Registry evidence without re-reviewing every image."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path, *, required: bool = True) -> dict[str, Any]:
    if not path.exists() and not required:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是对象")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def normalized_sha256(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text and not text.startswith("sha256:"):
        text = f"sha256:{text}"
    return text


def asset_rows(payload: dict[str, Any], label: str) -> list[dict[str, Any]]:
    for key in ("assets", "expanded_assets", "generation_requirements"):
        rows = payload.get(key)
        if isinstance(rows, list):
            result = []
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    raise ValueError(f"{label}.{key}[{index}] 必须是对象")
                result.append(row)
            return result
    if not payload:
        return []
    raise ValueError(f"{label} 缺少 assets/expanded_assets/generation_requirements 数组")


def reference_scope(asset: dict[str, Any]) -> str | None:
    explicit = asset.get("reference_scope")
    if explicit:
        return str(explicit)
    category = str(asset.get("category") or asset.get("asset_kind") or "").lower()
    return {
        "character": "character_single",
        "animal": "character_single",
        "creature": "character_single",
        "prop": "prop_single",
        "ui": "ui_single_state",
        "location": "location_single_composition",
        "scene": "location_single_composition",
        "environment": "location_single_composition",
    }.get(category)


def resolution_approves(
    resolutions: dict[str, Any], asset_id: str, digest: str
) -> bool:
    entries = resolutions.get("assets", {})
    if not isinstance(entries, dict):
        return False
    item = entries.get(asset_id)
    if not isinstance(item, dict):
        return False
    return (
        item.get("decision") == "approved"
        and normalized_sha256(item.get("sha256")) == digest
        and bool(str(item.get("reviewer") or "").strip())
        and bool(str(item.get("reason") or "").strip())
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从 n8n Registry 结构化质检证据生成实际资产清单"
    )
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--registry", default="assets/reference_registry.json")
    parser.add_argument("--base-list", default="assets/expanded_asset_list.base.json")
    parser.add_argument("--shot-list", default="assets/expanded_asset_list.shot.json")
    parser.add_argument(
        "--resolutions", default="review/asset_review_resolutions.json"
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    now = datetime.now(timezone.utc).isoformat()
    gate_path = project_root / "gates" / "asset_evidence_gate.json"
    exception_path = project_root / "review" / "asset_review_exceptions.json"

    try:
        project = load_json(project_root / "project.json", required=False)
        registry = load_json(project_root / args.registry)
        base = load_json(project_root / args.base_list, required=False)
        shot = load_json(project_root / args.shot_list, required=False)
        resolutions = load_json(project_root / args.resolutions, required=False)

        expected: dict[str, dict[str, Any]] = {}
        for label, payload in (("base", base), ("shot", shot)):
            for row in asset_rows(payload, label):
                asset_id = str(row.get("asset_id") or "").strip()
                if not asset_id:
                    raise ValueError(f"{label} 子资产缺少 asset_id")
                if asset_id in expected and expected[asset_id] != row:
                    raise ValueError(f"基础资产与镜头资产存在冲突 ID: {asset_id}")
                expected[asset_id] = row
        if not expected:
            raise ValueError("没有可接收的 expanded asset；Stage 48 不能凭空生成清单")

        entries = registry.get("assets")
        if not isinstance(entries, dict):
            raise ValueError("reference_registry.assets 必须是以 asset_id 为键的对象")

        errors: list[dict[str, Any]] = []
        exceptions: list[dict[str, Any]] = []
        actual_assets: list[dict[str, Any]] = []
        video_assets: list[dict[str, Any]] = []

        for asset_id, planned in expected.items():
            entry = entries.get(asset_id)
            if not isinstance(entry, dict):
                errors.append({"asset_id": asset_id, "code": "REGISTRY_ENTRY_MISSING"})
                continue
            if (entry.get("status") or entry.get("registry_status")) != "approved":
                errors.append(
                    {
                        "asset_id": asset_id,
                        "code": "REGISTRY_NOT_APPROVED",
                        "status": entry.get("status") or entry.get("registry_status"),
                    }
                )
                continue
            if planned.get("lock_hash") and entry.get("lock_hash") != planned.get("lock_hash"):
                errors.append({"asset_id": asset_id, "code": "LOCK_HASH_MISMATCH"})
                continue

            raw_path = entry.get("path") or entry.get("absolute_path")
            asset_path = Path(str(raw_path or "")).expanduser()
            if not asset_path.is_absolute() or not asset_path.is_file():
                errors.append(
                    {"asset_id": asset_id, "code": "ASSET_FILE_MISSING", "path": raw_path}
                )
                continue
            stat = asset_path.stat()
            digest = file_sha256(asset_path)
            if normalized_sha256(entry.get("sha256")) != digest:
                errors.append({"asset_id": asset_id, "code": "ASSET_SHA256_MISMATCH"})
                continue
            if int(entry.get("file_size") or 0) != stat.st_size:
                errors.append({"asset_id": asset_id, "code": "ASSET_FILE_SIZE_MISMATCH"})
                continue

            qa = entry.get("qa_evidence")
            if not isinstance(qa, dict):
                errors.append({"asset_id": asset_id, "code": "N8N_QA_EVIDENCE_MISSING"})
                continue
            hard_failures = qa.get("hard_requirement_failures")
            safety = qa.get("production_safety")
            if (
                qa.get("review_authority") != "n8n_structured_visual_qa"
                or qa.get("pass") is not True
                or not isinstance(hard_failures, list)
                or hard_failures
                or not isinstance(safety, dict)
            ):
                errors.append({"asset_id": asset_id, "code": "N8N_QA_EVIDENCE_INVALID"})
                continue

            reference_inputs = planned.get("reference_inputs") or []
            required_references = [
                row
                for row in reference_inputs
                if isinstance(row, dict) and row.get("required") is not False
            ]
            if required_references and safety.get("reference_consistency_checked") is not True:
                errors.append(
                    {"asset_id": asset_id, "code": "REFERENCE_CONSISTENCY_NOT_CHECKED"}
                )
                continue

            category = str(planned.get("category") or entry.get("category") or "").lower()
            if required_references and category in {"character", "animal", "creature"}:
                if (
                    safety.get("identity_consistency_applicable") is not True
                    or safety.get("identity_consistent") is not True
                ):
                    errors.append(
                        {"asset_id": asset_id, "code": "IDENTITY_CONTINUITY_NOT_PASSED"}
                    )
                    continue
            if required_references and category in {
                "location",
                "scene",
                "environment",
                "shot",
                "storyboard",
            }:
                if (
                    safety.get("scene_topology_applicable") is not True
                    or safety.get("scene_topology_consistent") is not True
                ):
                    errors.append(
                        {"asset_id": asset_id, "code": "SCENE_TOPOLOGY_NOT_PASSED"}
                    )
                    continue

            if (planned.get("asset_role") or entry.get("asset_role")) == "video_reference":
                if (
                    safety.get("single_view_clean") is not True
                    or safety.get("contains_multiple_independent_assets") is not False
                    or safety.get("contains_text_or_annotations") is not False
                ):
                    errors.append(
                        {"asset_id": asset_id, "code": "VIDEO_REFERENCE_SAFETY_NOT_PASSED"}
                    )
                    continue

            ambiguity = [
                str(value).strip()
                for value in (safety.get("ambiguity_reasons") or [])
                if str(value).strip()
            ]
            if ambiguity and not resolution_approves(resolutions, asset_id, digest):
                exceptions.append(
                    {
                        "asset_id": asset_id,
                        "path": str(asset_path),
                        "sha256": digest,
                        "reasons": ambiguity,
                        "required_action": "Agent 只检查这一张图并写入同 Hash 的人工结论",
                    }
                )

            actual = {
                **planned,
                "asset_id": asset_id,
                "status": "approved",
                "source_type": "n8n_registry_approved",
                "source_job_id": entry.get("job_id"),
                "payload_sha256": entry.get("payload_sha256"),
                "filename": entry.get("filename") or asset_path.name,
                "absolute_path": str(asset_path),
                "size_bytes": stat.st_size,
                "sha256": digest.removeprefix("sha256:"),
                "readable": True,
                "qa_evidence": qa,
            }
            actual_assets.append(actual)

            if (planned.get("asset_role") or entry.get("asset_role")) == "video_reference":
                video_assets.append(
                    {
                        "asset_id": asset_id,
                        "filename": actual["filename"],
                        "asset_role": "video_reference",
                        "layout_type": "single_view_clean",
                        "reference_scope": reference_scope({**planned, **entry}),
                        "contains_text_or_annotations": False,
                        "contains_multiple_independent_assets": False,
                        "video_reference_eligible": True,
                        "decision": "eligible_from_n8n_structured_qa",
                        "sha256": actual["sha256"],
                    }
                )

        unresolved = len(exceptions)
        passed = not errors and unresolved == 0
        project_id = (
            registry.get("project_id")
            or project.get("project_id")
            or project.get("id")
            or project_root.name
        )
        gate = {
            "schema_version": "1.0",
            "gate": "asset_evidence_ingest",
            "project_id": project_id,
            "passed": passed,
            "review_policy": "n8n_semantic_authority_agent_exception_only",
            "expected_asset_count": len(expected),
            "approved_asset_count": len(actual_assets),
            "video_reference_count": len(video_assets),
            "error_count": len(errors),
            "manual_visual_review_required_count": unresolved,
            "errors": errors,
            "checked_at": now,
        }
        exception_report = {
            "schema_version": "1.0",
            "project_id": project_id,
            "review_mode": "exception_only",
            "exception_count": unresolved,
            "exceptions": exceptions,
            "generated_at": now,
        }
        actual_manifest = {
            "schema_version": "1.3",
            "project_id": project_id,
            "source_authority": "n8n_reference_registry_with_structured_qa",
            "assets": actual_assets,
            "integrity_gate": {
                "status": "passed" if passed else "failed",
                "all_files_nonempty_readable": not any(
                    item["code"] == "ASSET_FILE_MISSING" for item in errors
                ),
                "all_hashes_match": not any(
                    item["code"] in {"ASSET_SHA256_MISMATCH", "ASSET_FILE_SIZE_MISMATCH"}
                    for item in errors
                ),
                "all_n8n_qa_evidence_valid": not any(
                    item["code"].startswith("N8N_QA") for item in errors
                ),
                "unresolved_visual_exceptions": unresolved,
            },
        }
        observed = {
            "schema_version": "1.0",
            "project_id": project_id,
            "observation_authority": "n8n_structured_visual_qa",
            "agent_visual_review_mode": "exception_only",
            "assets": [
                {
                    "asset_id": row["asset_id"],
                    "sha256": row["sha256"],
                    "qa_evidence": row["qa_evidence"],
                }
                for row in actual_assets
            ],
        }
        video_manifest = {
            "schema_version": "1.3",
            "project_id": project_id,
            "gate_policy": "n8n_qa_clean_single_view_only",
            "gate_status": "passed" if passed else "failed",
            "assets": video_assets,
            "eligible_asset_ids": [row["asset_id"] for row in video_assets],
        }

        atomic_json(project_root / "assets" / "actual_asset_manifest.json", actual_manifest)
        atomic_json(project_root / "assets" / "observed_asset_state.json", observed)
        atomic_json(project_root / "assets" / "video_reference_manifest.json", video_manifest)
        atomic_json(exception_path, exception_report)
        atomic_json(gate_path, gate)
        print(json.dumps(gate, ensure_ascii=False))
        return 0 if passed else 2
    except ValueError as exc:
        gate = {
            "schema_version": "1.0",
            "gate": "asset_evidence_ingest",
            "passed": False,
            "error": str(exc),
            "checked_at": now,
        }
        atomic_json(gate_path, gate)
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
