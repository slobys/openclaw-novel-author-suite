#!/usr/bin/env python3
"""Deterministically block unsafe multi-panel assets before video dispatch."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


ALLOWED_LAYOUT = "single_view_clean"
ALLOWED_ROLE = "video_reference"
ALLOWED_SCOPES = {
    "character_single",
    "prop_single",
    "prop_group_locked",
    "ui_single_state",
    "location_single_composition",
}
ASSET_ROOT = Path(
    os.environ.get("OPENCLAW_ASSET_ROOT", Path.home() / ".openclaw" / "data" / "openclaw-assets")
).expanduser()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 JSON {path}: {exc}") from exc


def indexed_assets(payload: dict, label: str) -> dict:
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ValueError(f"{label}.assets 必须是数组")
    result = {}
    for index, asset in enumerate(assets):
        asset_id = asset.get("asset_id")
        if not asset_id:
            raise ValueError(f"{label}.assets[{index}] 缺少 asset_id")
        if asset_id in result:
            raise ValueError(f"{label} 存在重复 asset_id: {asset_id}")
        result[asset_id] = asset
    return result


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def indexed_additional_bundle_assets(job: dict) -> dict:
    job_rows = job.get("additional_asset_jobs", [])
    if job_rows is None:
        job_rows = []
    if not isinstance(job_rows, list):
        raise ValueError("additional_asset_jobs 必须是数组")

    project_id = job.get("project_id")
    if not project_id:
        raise ValueError("video-job 缺少 project_id")
    job_ids = job.get("additional_asset_job_ids", [])
    if job_ids is None:
        job_ids = []
    if not isinstance(job_ids, list):
        raise ValueError("additional_asset_job_ids 必须是数组")

    sources = [(project_id, job_id) for job_id in job_ids]
    for index, row in enumerate(job_rows):
        if not isinstance(row, dict):
            raise ValueError(
                f"additional_asset_jobs[{index}] 必须是包含 project_id 和 asset_job_id 的对象"
            )
        sources.append((row.get("project_id", project_id), row.get("asset_job_id") or row.get("job_id")))

    result = {}

    for index, (source_project_id, job_id) in enumerate(sources):
        if (
            not isinstance(source_project_id, str)
            or not source_project_id
            or Path(source_project_id).name != source_project_id
        ):
            raise ValueError(f"附加资产来源[{index}] 不是安全的 project_id")
        if not isinstance(job_id, str) or not job_id or Path(job_id).name != job_id:
            raise ValueError(f"附加资产来源[{index}] 不是安全的 asset_job_id")
        project_dir = (ASSET_ROOT / source_project_id).resolve()
        bundle_dir = (project_dir / job_id).resolve()
        try:
            bundle_dir.relative_to(project_dir)
        except ValueError as exc:
            raise ValueError(f"附加资产来源[{index}] 路径越界") from exc

        manifest_path = bundle_dir / "result_manifest.json"
        done_path = bundle_dir / ".done"
        bundle_job_path = bundle_dir / "job.json"
        if not manifest_path.is_file() or not done_path.is_file():
            raise ValueError(f"附加资产任务 {job_id} 缺少 result_manifest.json 或 .done")

        manifest = load_json(manifest_path)
        if manifest.get("project_id") != source_project_id or manifest.get("job_id") != job_id:
            raise ValueError(f"附加资产任务 {job_id} 的项目或任务编号不匹配")
        if manifest.get("status") != "completed" or manifest.get("failed_count") != 0:
            raise ValueError(f"附加资产任务 {job_id} 未完整成功")

        # n8n's global progress scanner also touches read-only reference bundles.
        # It cannot infer accepted files for these synthetic bundles and may write
        # a misleading processing/accepted=0 sidecar.  A bundle is authoritative
        # only when both job.json and result_manifest.json explicitly agree that
        # the immutable bundle is complete; normal generation jobs still require
        # the strict progress check below.
        completed_read_only_bundle = False
        if bundle_job_path.is_file():
            bundle_job = load_json(bundle_job_path)
            expected = manifest.get("expected_count")
            completed_read_only_bundle = (
                bundle_job.get("project_id") == source_project_id
                and bundle_job.get("job_id") == job_id
                and bundle_job.get("status") == "completed"
                and bundle_job.get("expected_count") == expected
                and bundle_job.get("accepted_count") == expected
                and bundle_job.get("failed_count") == 0
                and manifest.get("accepted_count") == expected
            )

        partial_path = bundle_dir / ".partial"
        progress_path = bundle_dir / "progress.json"
        if partial_path.exists():
            raise ValueError(f"附加资产任务 {job_id} 仍存在 .partial，不能作为完成来源")
        if progress_path.exists() and not completed_read_only_bundle:
            progress = load_json(progress_path)
            if (
                progress.get("status") != "completed"
                or progress.get("failed_count") != 0
                or progress.get("accepted_count") != progress.get("expected_count")
            ):
                raise ValueError(f"附加资产任务 {job_id} 的 progress.json 未完整成功")

        for asset_id, asset in indexed_assets(manifest, f"additional_asset_job[{job_id}]").items():
            relative = asset.get("relative_path") or asset.get("filename")
            if not relative:
                raise ValueError(f"附加资产任务 {job_id} 的 {asset_id} 缺少文件名")
            asset_path = (bundle_dir / relative).resolve()
            try:
                asset_path.relative_to(bundle_dir)
            except ValueError as exc:
                raise ValueError(f"附加资产任务 {job_id} 的 {asset_id} 路径越界") from exc
            if not asset_path.is_file() or asset_path.stat().st_size <= 0:
                raise ValueError(f"附加资产任务 {job_id} 的 {asset_id} 文件缺失或为空")
            if asset.get("file_size") != asset_path.stat().st_size:
                raise ValueError(f"附加资产任务 {job_id} 的 {asset_id} 文件大小不匹配")
            if asset.get("sha256") != file_sha256(asset_path):
                raise ValueError(f"附加资产任务 {job_id} 的 {asset_id} SHA256 不匹配")
            if asset_id in result and result[asset_id].get("sha256") != asset.get("sha256"):
                raise ValueError(f"附加资产任务对 {asset_id} 提供了冲突版本")
            result[asset_id] = asset

    return result


def indexed_previous_episode_source_assets(job: dict) -> dict:
    rows = job.get("reference_source_assets", [])
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("reference_source_assets 必须是数组")

    result = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"reference_source_assets[{index}] 必须是对象")
        asset_id = row.get("asset_id")
        source_project_id = row.get("source_project_id")
        source_job_id = row.get("source_asset_job_id")
        source_asset_id = row.get("source_asset_id") or asset_id
        filename = row.get("filename")
        for label, value in (
            ("asset_id", asset_id),
            ("source_project_id", source_project_id),
            ("source_asset_job_id", source_job_id),
            ("source_asset_id", source_asset_id),
            ("filename", filename),
        ):
            if not isinstance(value, str) or not value or Path(value).name != value:
                raise ValueError(f"reference_source_assets[{index}].{label} 不安全或为空")

        source_project_dir = (ASSET_ROOT / source_project_id).resolve()
        source_job_dir = (source_project_dir / source_job_id).resolve()
        try:
            source_job_dir.relative_to(source_project_dir)
        except ValueError as exc:
            raise ValueError(f"reference_source_assets[{index}] 来源路径越界") from exc

        manifest_path = source_job_dir / "result_manifest.json"
        done_path = source_job_dir / ".done"
        if not manifest_path.is_file() or not done_path.is_file():
            raise ValueError(f"来源资产任务 {source_job_id} 缺少 result_manifest.json 或 .done")
        manifest = load_json(manifest_path)
        if (
            manifest.get("project_id") != source_project_id
            or manifest.get("job_id") != source_job_id
            or manifest.get("status") != "completed"
            or manifest.get("failed_count") != 0
            or manifest.get("accepted_count") != manifest.get("expected_count")
        ):
            raise ValueError(f"来源资产任务 {source_job_id} 未完整成功")

        source_assets = indexed_assets(manifest, f"reference_source_asset[{source_job_id}]")
        source_asset = source_assets.get(source_asset_id)
        if source_asset is None:
            raise ValueError(f"来源资产任务 {source_job_id} 缺少 {source_asset_id}")
        manifest_filename = source_asset.get("relative_path") or source_asset.get("filename")
        if manifest_filename != filename:
            raise ValueError(f"{asset_id}: 来源文件名与清单不一致")
        source_path = (source_job_dir / filename).resolve()
        try:
            source_path.relative_to(source_job_dir)
        except ValueError as exc:
            raise ValueError(f"{asset_id}: 来源文件路径越界") from exc
        if not source_path.is_file() or source_path.stat().st_size <= 0:
            raise ValueError(f"{asset_id}: 来源文件缺失或为空")
        size = source_asset.get("file_size") or source_asset.get("size_bytes")
        if size != source_path.stat().st_size or row.get("file_size") != size:
            raise ValueError(f"{asset_id}: 来源文件大小不匹配")
        digest = source_asset.get("sha256")
        if not digest or digest != file_sha256(source_path) or row.get("sha256") != digest:
            raise ValueError(f"{asset_id}: 来源 SHA256 不匹配")
        if asset_id in result and result[asset_id].get("sha256") != digest:
            raise ValueError(f"{asset_id}: 存在冲突来源")
        result[asset_id] = {**row, "sha256": digest, "file_size": size}

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="校验视频参考图是否为干净单画面")
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--actual-manifest", required=True, type=Path)
    parser.add_argument("--reference-manifest", required=True, type=Path)
    args = parser.parse_args()

    try:
        job = load_json(args.job)
        actual = indexed_assets(load_json(args.actual_manifest), "actual_manifest")
        refs_payload = load_json(args.reference_manifest)
        refs = indexed_assets(refs_payload, "video_reference_manifest")
        sole_location_asset_id = (
            refs_payload.get("video_reference_bundle", {}).get("sole_location_asset_id")
        )
        bundle_assets = indexed_additional_bundle_assets(job)
        source_assets = indexed_previous_episode_source_assets(job)
        if refs_payload.get("gate_status") != "passed":
            raise ValueError("video_reference_manifest.gate_status 必须为 passed")

        referenced_ids = []
        for clip_index, clip in enumerate(job.get("clips", [])):
            ids = clip.get("reference_asset_ids", [])
            if not isinstance(ids, list):
                raise ValueError(f"clips[{clip_index}].reference_asset_ids 必须是数组")
            referenced_ids.extend(ids)

        if not referenced_ids:
            raise ValueError("任务没有任何 reference_asset_ids")

        errors = []
        for asset_id in sorted(set(referenced_ids)):
            if asset_id not in actual:
                errors.append(f"{asset_id}: 不存在于 actual_asset_manifest")
                continue
            actual_asset = actual[asset_id]
            if actual_asset.get("source_type") == "series_canonical_reuse":
                bundle_asset = bundle_assets.get(asset_id)
                source_asset = source_assets.get(asset_id)
                if bundle_asset is None and source_asset is None:
                    errors.append(
                        f"{asset_id}: 跨集复用资产未通过有效 additional_asset_jobs 或 reference_source_assets 解析"
                    )
                elif bundle_asset is not None:
                    if bundle_asset.get("sha256") != actual_asset.get("sha256"):
                        errors.append(f"{asset_id}: 附加任务 SHA256 与 actual_manifest 不一致")
                    if bundle_asset.get("file_size") != actual_asset.get("size_bytes"):
                        errors.append(f"{asset_id}: 附加任务文件大小与 actual_manifest 不一致")
                elif source_asset is not None:
                    if source_asset.get("sha256") != actual_asset.get("sha256"):
                        errors.append(f"{asset_id}: 早期剧集来源 SHA256 与 actual_manifest 不一致")
                    if source_asset.get("file_size") != actual_asset.get("size_bytes"):
                        errors.append(f"{asset_id}: 早期剧集来源文件大小与 actual_manifest 不一致")
            ref = refs.get(asset_id)
            if ref is None:
                errors.append(f"{asset_id}: 缺少视频参考安全记录")
                continue
            if ref.get("asset_role") != ALLOWED_ROLE:
                errors.append(f"{asset_id}: asset_role={ref.get('asset_role')!r}，必须为 {ALLOWED_ROLE}")
            if ref.get("layout_type") != ALLOWED_LAYOUT:
                errors.append(f"{asset_id}: layout_type={ref.get('layout_type')!r}，必须为 {ALLOWED_LAYOUT}")
            if ref.get("contains_text_or_annotations") is not False:
                errors.append(f"{asset_id}: 含文字/标注或状态未知")
            if ref.get("contains_multiple_independent_assets") is not False:
                errors.append(f"{asset_id}: 包含多个独立资产或状态未知")
            if ref.get("reference_scope") not in ALLOWED_SCOPES:
                errors.append(
                    f"{asset_id}: reference_scope={ref.get('reference_scope')!r} 不允许"
                )
            if (
                sole_location_asset_id
                and ref.get("reference_scope") == "location_single_composition"
                and asset_id != sole_location_asset_id
            ):
                errors.append(
                    f"{asset_id}: 与唯一地点母资产 {sole_location_asset_id} 冲突"
                )
            if ref.get("video_reference_eligible") is not True:
                errors.append(f"{asset_id}: video_reference_eligible 未明确为 true")
            if not ref.get("filename"):
                errors.append(f"{asset_id}: 缺少安全参考文件名")

        if errors:
            raise ValueError("视频参考图安全 Gate 失败:\n- " + "\n- ".join(errors))

        result = {
            "ok": True,
            "gate": "video_reference_safety",
            "project_id": job.get("project_id"),
            "video_job_id": job.get("video_job_id"),
            "referenced_asset_count": len(set(referenced_ids)),
            "additional_bundle_asset_count": len(bundle_assets),
            "previous_episode_source_asset_count": len(source_assets),
            "policy": "clean_single_view_and_resolvable_source",
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
