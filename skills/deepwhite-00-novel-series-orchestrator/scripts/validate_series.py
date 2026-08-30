#!/usr/bin/env python3
"""Validate a planned novel-series project before episodes are enqueued."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from common import canonical_sha256, read_json, require_safe_id


EPISODE_RE = re.compile(r"^episode_(\d{3,4})\.json$")
REQUIRED_FILES = (
    "series.json",
    "chapters/chapter_index.json",
    "bible/book_bible.json",
    "bible/characters.json",
    "bible/timeline.json",
    "bible/clue_ledger.json",
    "plan/series_plan.json",
    "plan/adaptation_ledger.json",
)


def add_error(errors: list[str], message: str) -> None:
    if message not in errors:
        errors.append(message)


PROTECTED_DIMENSIONS = ("source_fidelity", "character_integrity", "continuity_safety")
ALL_DIMENSIONS = (
    "source_fidelity", "hook_clarity", "conflict_progression", "emotion_payoff",
    "character_integrity", "visual_storytelling", "continuity_safety",
    "production_feasibility", "asset_efficiency", "ending_pull",
)


def validate_professional_gate(gate: object, label: str, errors: list[str]) -> None:
    if not isinstance(gate, dict):
        add_error(errors, f"{label}.professional_gate 缺失或不是对象")
        return
    if gate.get("passed") is not True:
        add_error(errors, f"{label}.professional_gate.passed 必须为 true")
    score = gate.get("overall_score")
    if not isinstance(score, (int, float)) or score < 82 or score > 100:
        add_error(errors, f"{label}.professional_gate.overall_score 必须在 82-100")
    dimensions = gate.get("dimension_scores")
    if not isinstance(dimensions, dict):
        add_error(errors, f"{label}.professional_gate.dimension_scores 必须是对象")
    else:
        for name in ALL_DIMENSIONS:
            value = dimensions.get(name)
            if not isinstance(value, (int, float)) or not 0 <= value <= 100:
                add_error(errors, f"{label}.professional_gate.dimension_scores.{name} 必须在 0-100")
        for name in PROTECTED_DIMENSIONS:
            value = dimensions.get(name)
            if isinstance(value, (int, float)) and value < 80:
                add_error(errors, f"{label}.professional_gate.dimension_scores.{name} 不得低于 80")
    hard_failures = gate.get("hard_failures")
    if not isinstance(hard_failures, list) or hard_failures:
        add_error(errors, f"{label}.professional_gate.hard_failures 必须为空数组")
    evidence = gate.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        add_error(errors, f"{label}.professional_gate.evidence 必须是非空数组")
    if not isinstance(gate.get("issues"), list):
        add_error(errors, f"{label}.professional_gate.issues 必须是数组")
    if not isinstance(gate.get("repairs"), list):
        add_error(errors, f"{label}.professional_gate.repairs 必须是数组")
    attempts = gate.get("attempts", 1)
    if not isinstance(attempts, int) or not 1 <= attempts <= 2:
        add_error(errors, f"{label}.professional_gate.attempts 必须是 1 或 2")


def validate_legacy_gate(gate: object, label: str, errors: list[str]) -> None:
    """Keep already-planned v1.0 series runnable after a v1.1 upgrade."""
    if not isinstance(gate, dict):
        add_error(errors, f"{label}.gate 缺失或不是对象")
        return
    if gate.get("passed") is not True:
        add_error(errors, f"{label}.gate.passed 必须为 true")
    score = gate.get("score")
    if not isinstance(score, (int, float)) or score < 80 or score > 100:
        add_error(errors, f"{label}.gate.score 必须在 80-100")
    if not isinstance(gate.get("evidence"), list) or not gate.get("evidence"):
        add_error(errors, f"{label}.gate.evidence 必须是非空数组")


def validate_episode(data: object, path: Path, known_chapters: set[str], errors: list[str]) -> dict | None:
    label = path.name
    if not isinstance(data, dict):
        add_error(errors, f"{label} 顶层必须是对象")
        return None
    try:
        require_safe_id(data.get("series_id"), f"{label}.series_id")
        require_safe_id(data.get("episode_project_id"), f"{label}.episode_project_id")
    except ValueError as exc:
        add_error(errors, str(exc))
    number = data.get("episode_number")
    if not isinstance(number, int) or number < 1:
        add_error(errors, f"{label}.episode_number 必须是正整数")
    duration = data.get("target_duration_seconds")
    if not isinstance(duration, int) or not 15 <= duration <= 600:
        add_error(errors, f"{label}.target_duration_seconds 必须在 15-600 秒")
    duration_limit = duration if isinstance(duration, int) and 15 <= duration <= 600 else 600
    if data.get("status", "planned") != "planned":
        add_error(errors, f"{label}.status 必须为 planned")
    schema_version = str(data.get("schema_version", "1.0"))
    is_professional = schema_version in {"1.1", "1.2"}
    if not is_professional:
        source_ids = data.get("source_chapter_ids")
        if not isinstance(source_ids, list) or not source_ids:
            add_error(errors, f"{label}.source_chapter_ids 必须为非空数组")
        else:
            unknown = sorted({str(item) for item in source_ids} - known_chapters)
            if unknown:
                add_error(errors, f"{label} 引用了不存在章节：{', '.join(unknown)}")
        if not isinstance(data.get("adaptation_brief"), dict):
            add_error(errors, f"{label}.adaptation_brief 必须是对象")
        if not isinstance(data.get("continuity_in"), dict):
            add_error(errors, f"{label}.continuity_in 必须是对象")
        validate_legacy_gate(data.get("gate"), label, errors)
        for prompt in data.get("video_prompt_groups", []):
            if not isinstance(prompt, dict):
                add_error(errors, f"{label}.video_prompt_groups 存在非对象")
                continue
            seconds = prompt.get("duration_seconds")
            if not isinstance(seconds, (int, float)) or seconds <= 0 or seconds > 15:
                add_error(errors, f"{label} 的单条视频提示词必须 >0 且 <=15 秒")
        return data
    if data.get("aspect_ratio") not in {"9:16", "16:9", "1:1", "4:3", "3:4", "21:9"}:
        add_error(errors, f"{label}.aspect_ratio 不是支持的画幅")
    if data.get("format_profile") not in {"auto", "domestic_vertical_manga", "cinematic_horizontal"}:
        add_error(errors, f"{label}.format_profile 无效")
    if data.get("genre_profile") not in {"growth_reversal", "emotional_relationship", "suspense_mystery", "comedy_absurd", "ensemble_reality", "hybrid"}:
        add_error(errors, f"{label}.genre_profile 无效")
    source_ids = data.get("source_chapter_ids")
    if not isinstance(source_ids, list) or not source_ids:
        add_error(errors, f"{label}.source_chapter_ids 必须为非空数组")
    else:
        unknown = sorted({str(item) for item in source_ids} - known_chapters)
        if unknown:
            add_error(errors, f"{label} 引用了不存在章节：{', '.join(unknown)}")
    if not isinstance(data.get("adaptation_brief"), dict):
        add_error(errors, f"{label}.adaptation_brief 必须是对象")
    else:
        for key in ("logline", "episode_goal", "primary_conflict", "ending_hook"):
            if not str(data["adaptation_brief"].get(key, "")).strip():
                add_error(errors, f"{label}.adaptation_brief.{key} 不能为空")
    hook = data.get("hook_contract")
    if not isinstance(hook, dict):
        add_error(errors, f"{label}.hook_contract 必须是对象")
    else:
        if not str(hook.get("hook_text", "")).strip():
            add_error(errors, f"{label}.hook_contract.hook_text 不能为空")
        established = hook.get("established_by_seconds")
        if not isinstance(established, (int, float)) or not 0 <= established <= 10:
            add_error(errors, f"{label}.hook_contract.established_by_seconds 必须在 0-10 秒")
        conflict = hook.get("conflict_clear_by_seconds")
        if not isinstance(conflict, (int, float)) or not 0 < conflict <= 30:
            add_error(errors, f"{label}.hook_contract.conflict_clear_by_seconds 必须在 0-30 秒")
        if not isinstance(hook.get("visual_evidence"), list) or not hook.get("visual_evidence"):
            add_error(errors, f"{label}.hook_contract.visual_evidence 必须是非空数组")
    rhythm = data.get("rhythm_map")
    if not isinstance(rhythm, list) or len(rhythm) < 4:
        add_error(errors, f"{label}.rhythm_map 至少需要 4 个有效节拍")
    else:
        times: list[float] = []
        functions: set[str] = set()
        for beat in rhythm:
            if not isinstance(beat, dict):
                add_error(errors, f"{label}.rhythm_map 存在非对象")
                continue
            at_seconds = beat.get("at_seconds")
            if not isinstance(at_seconds, (int, float)) or not 0 <= at_seconds <= duration_limit:
                add_error(errors, f"{label}.rhythm_map.at_seconds 必须在本集时长内")
                continue
            times.append(float(at_seconds))
            functions.add(str(beat.get("function", "")))
            if not str(beat.get("change", "")).strip():
                add_error(errors, f"{label}.rhythm_map.change 不能为空")
        if times != sorted(times):
            add_error(errors, f"{label}.rhythm_map 必须按时间递增")
        if "hook" not in functions or "ending_hook" not in functions:
            add_error(errors, f"{label}.rhythm_map 必须包含 hook 和 ending_hook")
    emotion = data.get("emotion_curve")
    if not isinstance(emotion, dict) or any(not str(emotion.get(key, "")).strip() for key in ("start", "pressure", "turn", "primary_payoff", "residual")):
        add_error(errors, f"{label}.emotion_curve 必须完整包含五段情绪变化")
    payoffs = data.get("payoff_map")
    if not isinstance(payoffs, list) or not any(isinstance(row, dict) and row.get("type") == "primary" for row in payoffs):
        add_error(errors, f"{label}.payoff_map 至少需要一个 primary 回报")
    visual = data.get("visual_strategy")
    if not isinstance(visual, dict):
        add_error(errors, f"{label}.visual_strategy 必须是对象")
    else:
        if not str(visual.get("visual_anchor", "")).strip():
            add_error(errors, f"{label}.visual_strategy.visual_anchor 不能为空")
        for key in ("asset_reuse_ids", "new_asset_requirements", "high_risk_shots", "risk_mitigation"):
            if not isinstance(visual.get(key), list):
                add_error(errors, f"{label}.visual_strategy.{key} 必须是数组")
        if schema_version == "1.2":
            scene_policy = visual.get("scene_asset_policy")
            if not isinstance(scene_policy, dict):
                add_error(errors, f"{label}.visual_strategy.scene_asset_policy 必须是对象")
            else:
                if scene_policy.get("required") is not True:
                    add_error(errors, f"{label}.visual_strategy.scene_asset_policy.required 必须为 true")
                if scene_policy.get("planner_skill") != "deepwhite-scene-asset-planner":
                    add_error(errors, f"{label}.visual_strategy.scene_asset_policy.planner_skill 必须为 deepwhite-scene-asset-planner")
                if scene_policy.get("require_100_percent_scene_coverage") is not True:
                    add_error(errors, f"{label}.visual_strategy.scene_asset_policy.require_100_percent_scene_coverage 必须为 true")
                soft = scene_policy.get("same_background_soft_limit_seconds")
                hard = scene_policy.get("same_background_hard_limit_seconds")
                if not isinstance(soft, (int, float)) or soft <= 0:
                    add_error(errors, f"{label}.visual_strategy.scene_asset_policy.same_background_soft_limit_seconds 必须 >0")
                if not isinstance(hard, (int, float)) or hard <= 0:
                    add_error(errors, f"{label}.visual_strategy.scene_asset_policy.same_background_hard_limit_seconds 必须 >0")
                if isinstance(soft, (int, float)) and isinstance(hard, (int, float)) and hard < soft:
                    add_error(errors, f"{label}.visual_strategy.scene_asset_policy hard limit 不得小于 soft limit")
            for path_key in ("scene_asset_plan_path", "location_asset_requirements_path", "scene_asset_handoff_path", "scene_asset_gate_path"):
                value = visual.get(path_key)
                if not isinstance(value, str) or not value.strip():
                    add_error(errors, f"{label}.visual_strategy.{path_key} 不能为空")
                elif Path(value).is_absolute() or ".." in Path(value).parts:
                    add_error(errors, f"{label}.visual_strategy.{path_key} 必须是安全相对路径")
    if not isinstance(data.get("continuity_in"), dict):
        add_error(errors, f"{label}.continuity_in 必须是对象")
    production = data.get("production")
    if not isinstance(production, dict):
        add_error(errors, f"{label}.production 必须是对象")
    elif schema_version == "1.2":
        if production.get("auto_production_mode") is not True:
            add_error(errors, f"{label}.production.auto_production_mode 必须为 true")
        if production.get("pipeline_profile") != "scene_bound_auto_v1.2":
            add_error(errors, f"{label}.production.pipeline_profile 必须为 scene_bound_auto_v1.2")
        if production.get("require_pipeline_evidence") is not True:
            add_error(errors, f"{label}.production.require_pipeline_evidence 必须为 true")
        min_clip = production.get("min_auto_video_clip_seconds")
        max_clip = production.get("max_video_prompt_seconds")
        if min_clip != 4:
            add_error(errors, f"{label}.production.min_auto_video_clip_seconds 必须为 4")
        if max_clip != 15:
            add_error(errors, f"{label}.production.max_video_prompt_seconds 必须为 15")
    validate_professional_gate(data.get("professional_gate"), label, errors)
    for prompt in data.get("video_prompt_groups", []):
        if not isinstance(prompt, dict):
            add_error(errors, f"{label}.video_prompt_groups 存在非对象")
            continue
        seconds = prompt.get("duration_seconds")
        if not isinstance(seconds, (int, float)) or seconds <= 0 or seconds > 15:
            add_error(errors, f"{label} 的单条视频提示词必须 >0 且 <=15 秒")
    return data


def validate_series_root(series_root: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    for relative in REQUIRED_FILES:
        if not (series_root / relative).is_file():
            add_error(errors, f"缺少必需文件：{relative}")
    index_path = series_root / "chapters" / "chapter_index.json"
    known_chapters: set[str] = set()
    index = None
    if index_path.is_file():
        try:
            index = read_json(index_path)
            rows = index.get("chapters", []) if isinstance(index, dict) else []
            for row in rows:
                if isinstance(row, dict) and row.get("chapter_id"):
                    chapter_id = str(row["chapter_id"])
                    known_chapters.add(chapter_id)
                    chapter_path = series_root / str(row.get("relative_path", ""))
                    if not chapter_path.is_file():
                        add_error(errors, f"章节正文不存在：{row.get('relative_path')}")
            if index.get("chapter_count") != len(rows):
                add_error(errors, "chapter_index.chapter_count 与章节数组数量不一致")
            if float(index.get("coverage_ratio", 0)) < 0.95:
                add_error(errors, "章节覆盖率低于 95%")
        except Exception as exc:
            add_error(errors, f"无法读取 chapter_index：{exc}")

    episodes_dir = series_root / "episodes"
    episode_files = sorted(path for path in episodes_dir.glob("episode_*.json") if EPISODE_RE.match(path.name))
    if not episode_files:
        add_error(errors, "episodes 目录中没有 episode_XXX.json")
    numbers: list[int] = []
    project_ids: set[str] = set()
    episode_hashes: dict[str, str] = {}
    series_ids: set[str] = set()
    professional_episode_count = 0
    for path in episode_files:
        try:
            data = validate_episode(read_json(path), path, known_chapters, errors)
        except Exception as exc:
            add_error(errors, f"无法读取 {path.name}：{exc}")
            continue
        if not data:
            continue
        if str(data.get("schema_version", "1.0")) in {"1.1", "1.2"}:
            professional_episode_count += 1
        if isinstance(data.get("episode_number"), int):
            numbers.append(data["episode_number"])
        project_id = str(data.get("episode_project_id", ""))
        if project_id in project_ids:
            add_error(errors, f"episode_project_id 重复：{project_id}")
        project_ids.add(project_id)
        series_ids.add(str(data.get("series_id", "")))
        episode_hashes[project_id] = canonical_sha256(data)
    if numbers and sorted(numbers) != list(range(1, len(numbers) + 1)):
        add_error(errors, "episode_number 必须从 1 开始连续递增")
    if len(series_ids) > 1:
        add_error(errors, "分集简报中出现多个 series_id")
    if professional_episode_count and not (series_root / "plan" / "format_strategy.json").is_file():
        add_error(errors, "v1.1 专业版项目缺少必需文件：plan/format_strategy.json")
    summary_files = list((series_root / "summaries").glob("chapter_*.summary.json"))
    if known_chapters and len(summary_files) < len(known_chapters):
        add_error(errors, f"逐章摘要不完整：章节 {len(known_chapters)}，摘要 {len(summary_files)}")

    return {
        "ok": not errors,
        "series_root": str(series_root),
        "chapter_count": len(known_chapters),
        "episode_count": len(episode_files),
        "episode_hashes": episode_hashes,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证小说系列项目")
    parser.add_argument("--series-root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate_series_root(Path(args.series_root).expanduser().resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"验证通过：{result['chapter_count']} 章，{result['episode_count']} 集")
    else:
        print("验证失败：", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
