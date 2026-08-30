#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path

MODES = {"user_locked", "downstream_auto", "reference_locked"}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def read_json(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def canonical_sha256(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def version_tuple(value):
    values = []
    for token in str(value or "0").split("."):
        try:
            values.append(int(token))
        except ValueError:
            values.append(0)
    return tuple(values)


def validate_contract(contract, errors, label):
    if not isinstance(contract, dict):
        errors.append(f"{label} 必须是对象")
        return None
    if contract.get("authority") != "drama-producer":
        errors.append(f"{label}.authority 必须为 drama-producer")
    mode = contract.get("mode")
    if mode not in MODES:
        errors.append(f"{label}.mode 无效")
    if contract.get("user_confirmed") is True:
        evidence = contract.get("confirmation_evidence")
        valid = (
            isinstance(evidence, dict)
            and evidence.get("type") == "user_explicit_selection"
            and str(evidence.get("source_excerpt", "")).strip()
        )
        if not valid:
            errors.append(f"{label}.user_confirmed 缺少真实用户选择证据")
    if mode == "user_locked":
        if contract.get("source") != "user_explicit_request":
            errors.append(f"{label}.source 必须为 user_explicit_request")
        if not str(contract.get("raw_user_request", "")).strip():
            errors.append(f"{label}.raw_user_request 不能为空")
        for key in ("must_preserve", "must_not_transform_to"):
            value = contract.get(key)
            if not isinstance(value, list) or not value or any(not str(item).strip() for item in value):
                errors.append(f"{label}.{key} 必须是非空字符串数组")
    if mode == "downstream_auto" and contract.get("user_confirmed") is True:
        errors.append(f"{label} downstream_auto 不得标记 user_confirmed")
    if mode == "reference_locked":
        references = contract.get("reference_assets")
        if not isinstance(references, list) or not references:
            errors.append(f"{label}.reference_assets 必须是非空数组")
        else:
            for index, item in enumerate(references):
                if not isinstance(item, dict):
                    errors.append(f"{label}.reference_assets[{index}] 必须是对象")
                    continue
                if not str(item.get("asset_id", "")).strip():
                    errors.append(f"{label}.reference_assets[{index}].asset_id 不能为空")
                if not isinstance(item.get("file_size"), int) or item["file_size"] <= 0:
                    errors.append(f"{label}.reference_assets[{index}].file_size 必须大于0")
                if not SHA_RE.fullmatch(str(item.get("sha256", "")).lower()):
                    errors.append(f"{label}.reference_assets[{index}].sha256 无效")
    if not isinstance(contract.get("story_visual_context", {}), dict):
        errors.append(f"{label}.story_visual_context 必须是对象")
    return canonical_sha256(contract)


def validate_strategy(strategy, episodes, errors, label):
    contract = strategy.get("style_handoff")
    if contract is None and version_tuple(strategy.get("schema_version")) < (1, 2):
        return None, True, ""
    actual_hash = validate_contract(contract, errors, f"{label}.style_handoff")
    expected_hash = str(strategy.get("style_handoff_sha256", "")).lower()
    if not expected_hash:
        errors.append(f"{label}.style_handoff_sha256 不能为空")
    elif actual_hash and expected_hash != actual_hash:
        errors.append(f"{label}.style_handoff_sha256 与合同内容不一致")
    for episode_label, episode in episodes:
        if str(episode.get("style_handoff_sha256", "")).lower() != expected_hash:
            errors.append(f"{episode_label}.style_handoff_sha256 与系列合同不一致")
    return contract, False, expected_hash


def validate_asset_job(job, contract, expected_hash, errors):
    if job.get("style_contract") != contract:
        errors.append("asset_job.style_contract 与系列合同不一致")
    if str(job.get("style_contract_sha256", "")).lower() != expected_hash:
        errors.append("asset_job.style_contract_sha256 不一致")
    assets = job.get("assets")
    if not isinstance(assets, list) or not assets:
        errors.append("asset_job.assets 必须是非空数组")
        return
    forbidden = [str(item).casefold() for item in contract.get("must_not_transform_to", [])]
    for index, asset in enumerate(assets):
        if "【系列风格硬约束】" not in str(asset.get("prompt_zh", "")):
            errors.append(f"assets[{index}].prompt_zh 缺少系列风格硬约束前缀")
        negative = str(asset.get("negative_prompt", "")).casefold()
        missing = [term for term in forbidden if term not in negative]
        if missing:
            errors.append(f"assets[{index}].negative_prompt 未覆盖禁止方向：{missing}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--series-root")
    parser.add_argument("--context")
    parser.add_argument("--asset-job")
    args = parser.parse_args()
    if bool(args.series_root) == bool(args.context):
        raise SystemExit("必须且只能指定 --series-root 或 --context")

    errors = []
    if args.series_root:
        root = Path(args.series_root)
        strategy = read_json(root / "plan" / "format_strategy.json")
        episodes = [(p.name, read_json(p)) for p in sorted((root / "episodes").glob("episode_*.json"))]
        contract, legacy, expected_hash = validate_strategy(strategy, episodes, errors, "format_strategy")
    else:
        context = read_json(args.context)
        strategy = context.get("series_format_strategy")
        if not isinstance(strategy, dict):
            strategy = {}
        episode = context.get("episode") if isinstance(context.get("episode"), dict) else {}
        contract, legacy, expected_hash = validate_strategy(
            strategy, [("context.episode", episode)], errors, "context.series_format_strategy"
        )
        if context.get("style_handoff") is not None and context.get("style_handoff") != contract:
            errors.append("context 顶层 style_handoff 与系列合同不一致")
        top_hash = context.get("style_handoff_sha256")
        if top_hash is not None and str(top_hash).lower() != expected_hash:
            errors.append("context 顶层 style_handoff_sha256 不一致")

    if args.asset_job:
        if legacy or contract is None:
            errors.append("legacy 项目没有可用于资产派发的 style_handoff")
        else:
            validate_asset_job(read_json(args.asset_job), contract, expected_hash, errors)

    result = {"ok": not errors, "legacy": legacy, "style_handoff_sha256": expected_hash or None}
    if errors:
        result["errors"] = errors
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
