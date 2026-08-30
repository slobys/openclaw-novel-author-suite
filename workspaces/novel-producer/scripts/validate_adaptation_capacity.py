#!/usr/bin/env python3
"""Reject episode plans that exceed source/event/screen-time capacity."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


SOFT_SOURCE_CHARS_PER_90S = 1200
HARD_SOURCE_CHARS_PER_90S = 1800
MIN_SECONDS_PER_EFFECTIVE_BEAT = 10
PRESERVING_SOFT_SOURCE_CHARS_PER_90S = 350
PRESERVING_HARD_SOURCE_CHARS_PER_90S = 550


def read_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def add_unique(rows: list[str], message: str) -> None:
    if message not in rows:
        rows.append(message)


def episode_number(row: dict) -> int | None:
    value = row.get("global_episode_number", row.get("episode_number"))
    return value if isinstance(value, int) and value > 0 else None


def validate(series_root: Path) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    index_path = series_root / "chapters" / "chapter_index.json"
    strategy_path = series_root / "plan" / "format_strategy.json"
    plan_path = series_root / "plan" / "series_plan.json"
    ledger_path = series_root / "plan" / "adaptation_ledger.json"
    for path in (index_path, strategy_path, plan_path, ledger_path):
        if not path.is_file():
            add_unique(errors, f"缺少容量验证输入：{path.relative_to(series_root)}")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings}

    index = read_json(index_path)
    strategy = read_json(strategy_path)
    plan = read_json(plan_path)
    ledger = read_json(ledger_path)
    if not all(isinstance(row, dict) for row in (index, strategy, plan, ledger)):
        return {"ok": False, "errors": ["容量验证输入的顶层必须是对象"], "warnings": []}

    chapter_chars = {
        str(row.get("chapter_id")): int(row.get("char_count", 0))
        for row in index.get("chapters", [])
        if isinstance(row, dict) and row.get("chapter_id")
    }
    segment_path = series_root / "segments" / "source_segments.json"
    segment_chars: dict[str, int] = {}
    if segment_path.is_file():
        segment_manifest = read_json(segment_path)
        if isinstance(segment_manifest, dict):
            segment_chars = {
                str(item.get("segment_id")): int(item.get("char_count", 0))
                for item in segment_manifest.get("segments", [])
                if isinstance(item, dict) and item.get("segment_id")
            }
    ledger_entries = {
        str(row.get("event_id")): row
        for row in ledger.get("entries", [])
        if isinstance(row, dict) and row.get("event_id")
    }
    default_duration = int(strategy.get("episode_duration_seconds", 90))
    preservation_path = series_root / "plan" / "source_preservation_contract.json"
    preservation = read_json(preservation_path) if preservation_path.is_file() else {}
    preserving_mode = isinstance(preservation, dict) and preservation.get("adaptation_mode") == "source_preserving_segmentation"
    soft_rate = PRESERVING_SOFT_SOURCE_CHARS_PER_90S if preserving_mode else SOFT_SOURCE_CHARS_PER_90S
    hard_rate = PRESERVING_HARD_SOURCE_CHARS_PER_90S if preserving_mode else HARD_SOURCE_CHARS_PER_90S
    episode_rows = plan.get("episodes", [])
    if not isinstance(episode_rows, list) or not episode_rows:
        add_unique(errors, "plan/series_plan.json 缺少 episodes")
        episode_rows = []

    report_rows: list[dict] = []
    plan_by_number: dict[int, dict] = {}
    for row in episode_rows:
        if not isinstance(row, dict):
            add_unique(errors, "series_plan.episodes 存在非对象")
            continue
        number = episode_number(row)
        if number is None:
            add_unique(errors, "series_plan 存在无有效集号的分集")
            continue
        plan_by_number[number] = row
        label = f"第{number}集"
        duration = row.get("target_duration_seconds", default_duration)
        if not isinstance(duration, (int, float)) or duration <= 0:
            add_unique(errors, f"{label} 目标时长无效")
            duration = default_duration
        chapter_ids = row.get("source_chapter_ids", [])
        event_ids = row.get("source_event_ids", [])
        if not isinstance(chapter_ids, list) or not isinstance(event_ids, list):
            add_unique(errors, f"{label} 来源章节或事件不是数组")
            continue
        missing_chapters = [item for item in chapter_ids if str(item) not in chapter_chars]
        if missing_chapters:
            add_unique(errors, f"{label} 引用未知章节：{missing_chapters}")
        source_segment_ids = row.get("source_segment_ids", [])
        if preserving_mode:
            if not isinstance(source_segment_ids, list) or not source_segment_ids:
                add_unique(errors, f"{label} 原文保全模式缺少 source_segment_ids")
                source_segment_ids = []
            unknown_segments = [str(item) for item in source_segment_ids if str(item) not in segment_chars]
            if unknown_segments:
                add_unique(errors, f"{label} 引用未知源段：{', '.join(unknown_segments)}")
            source_chars = sum(segment_chars.get(str(item), 0) for item in source_segment_ids)
        else:
            source_chars = sum(chapter_chars.get(str(item), 0) for item in chapter_ids)
        soft_limit = round(soft_rate * float(duration) / 90)
        hard_limit = round(hard_rate * float(duration) / 90)
        if source_chars > hard_limit:
            add_unique(errors, f"{label} 源文本 {source_chars} 字超过硬上限 {hard_limit} 字，必须拆集")
        elif source_chars > soft_limit:
            add_unique(warnings, f"{label} 源文本 {source_chars} 字超过软上限 {soft_limit} 字，应优先拆集")

        unknown_events = [str(item) for item in event_ids if str(item) not in ledger_entries]
        if unknown_events:
            add_unique(errors, f"{label} 引用未登记事件：{', '.join(unknown_events)}")
        assignment_mismatches: list[str] = []
        for item in event_ids:
            entry = ledger_entries.get(str(item))
            if not entry:
                continue
            assignment = entry.get("episode_assignment", {})
            assigned_number = assignment.get("global_episode_number") if isinstance(assignment, dict) else None
            if assigned_number != number:
                assignment_mismatches.append(str(item))
        if assignment_mismatches:
            add_unique(errors, f"{label} 事件账本分配不一致：{', '.join(assignment_mismatches)}")

        capacity = row.get("episode_capacity")
        if not isinstance(capacity, dict):
            add_unique(errors, f"{label} 缺少 episode_capacity，旧规划不能通过容量 Gate")
            capacity = {}
        if capacity.get("source_char_count") != source_chars:
            add_unique(errors, f"{label} episode_capacity.source_char_count 必须为 {source_chars}")
        if capacity.get("source_event_count") != len(event_ids):
            add_unique(errors, f"{label} episode_capacity.source_event_count 必须为 {len(event_ids)}")
        if capacity.get("source_char_soft_limit") != soft_limit:
            add_unique(errors, f"{label} episode_capacity.source_char_soft_limit 必须为 {soft_limit}")
        if capacity.get("source_char_hard_limit") != hard_limit:
            add_unique(errors, f"{label} episode_capacity.source_char_hard_limit 必须为 {hard_limit}")
        estimated_seconds = capacity.get("estimated_screen_seconds")
        if not isinstance(estimated_seconds, (int, float)) or estimated_seconds <= 0:
            add_unique(errors, f"{label} 缺少有效 estimated_screen_seconds")
        elif estimated_seconds > float(duration):
            add_unique(errors, f"{label} 事件估时 {estimated_seconds} 秒超过目标片长 {duration} 秒")
        if preserving_mode:
            spoken_chars = capacity.get("spoken_char_count")
            spoken_seconds = capacity.get("spoken_duration_seconds")
            action_seconds = capacity.get("action_visual_seconds")
            pause_seconds = capacity.get("pause_and_transition_seconds")
            if not isinstance(spoken_chars, int) or spoken_chars < 0:
                add_unique(errors, f"{label} 缺少有效 spoken_char_count")
            minimum_spoken_seconds = (spoken_chars / 3.5) if isinstance(spoken_chars, int) and spoken_chars >= 0 else 0
            if not isinstance(spoken_seconds, (int, float)) or spoken_seconds < minimum_spoken_seconds:
                add_unique(errors, f"{label} spoken_duration_seconds 不得低于自然配音时长 {minimum_spoken_seconds:.1f} 秒")
            if not isinstance(action_seconds, (int, float)) or action_seconds < 0:
                add_unique(errors, f"{label} 缺少有效 action_visual_seconds")
            if not isinstance(pause_seconds, (int, float)) or pause_seconds < 0:
                add_unique(errors, f"{label} 缺少有效 pause_and_transition_seconds")
            if all(isinstance(value, (int, float)) for value in (spoken_seconds, action_seconds, pause_seconds)):
                component_total = float(spoken_seconds) + float(action_seconds) + float(pause_seconds)
                if component_total > float(duration):
                    add_unique(errors, f"{label} 配音+动作+停顿共 {component_total:g} 秒，超过目标片长 {duration} 秒")
                if isinstance(estimated_seconds, (int, float)) and estimated_seconds < component_total:
                    add_unique(errors, f"{label} estimated_screen_seconds 不得低于分项时长 {component_total:g} 秒")
        beat_count = capacity.get("effective_beat_count")
        max_beats = max(1, math.ceil(float(duration) / MIN_SECONDS_PER_EFFECTIVE_BEAT))
        if not isinstance(beat_count, int) or beat_count <= 0:
            add_unique(errors, f"{label} 缺少有效 effective_beat_count")
        elif beat_count > max_beats:
            add_unique(errors, f"{label} 有效节拍 {beat_count} 个超过 {duration} 秒容量上限 {max_beats} 个")
        if capacity.get("mapped_event_count") != len(event_ids):
            add_unique(errors, f"{label} mapped_event_count 必须覆盖全部 {len(event_ids)} 个事件")
        unmapped = capacity.get("unmapped_event_ids")
        if not isinstance(unmapped, list) or unmapped:
            add_unique(errors, f"{label} unmapped_event_ids 必须为空数组")
        if not isinstance(capacity.get("compression_actions"), list):
            add_unique(errors, f"{label} compression_actions 必须是数组")
        if capacity.get("capacity_status") != "pass":
            add_unique(errors, f"{label} capacity_status 必须为 pass")
        report_rows.append({
            "episode_number": number,
            "duration_seconds": duration,
            "source_char_count": source_chars,
            "soft_limit": soft_limit,
            "hard_limit": hard_limit,
            "source_event_count": len(event_ids),
            "source_segment_count": len(source_segment_ids) if isinstance(source_segment_ids, list) else 0,
        })

    episodes_dir = series_root / "episodes"
    for brief_path in sorted(episodes_dir.glob("episode_*.json")):
        data = read_json(brief_path)
        if not isinstance(data, dict):
            add_unique(errors, f"{brief_path.name} 顶层不是对象")
            continue
        number = episode_number(data)
        label = brief_path.name
        source_events = {str(item) for item in data.get("source_event_ids", [])}
        adaptation = data.get("adaptation_brief", {})
        scene_beats = adaptation.get("scene_beats") if isinstance(adaptation, dict) else None
        if not isinstance(scene_beats, list) or not scene_beats:
            add_unique(errors, f"{label} 缺少带事件映射的 scene_beats")
            continue
        mapped: set[str] = set()
        total_seconds = 0.0
        for index_no, beat in enumerate(scene_beats, start=1):
            if not isinstance(beat, dict):
                add_unique(errors, f"{label} scene_beat {index_no} 不是对象")
                continue
            beat_events = beat.get("source_event_ids")
            seconds = beat.get("duration_seconds")
            if not isinstance(beat_events, list) or not beat_events:
                add_unique(errors, f"{label} scene_beat {index_no} 缺少 source_event_ids")
            else:
                mapped.update(str(item) for item in beat_events)
            if not isinstance(seconds, (int, float)) or seconds <= 0:
                add_unique(errors, f"{label} scene_beat {index_no} 缺少有效 duration_seconds")
            else:
                total_seconds += float(seconds)
        missing = sorted(source_events - mapped)
        foreign = sorted(mapped - source_events)
        if missing:
            add_unique(errors, f"{label} 存在未映射事件：{', '.join(missing)}")
        if foreign:
            add_unique(errors, f"{label} 分场引用本集之外事件：{', '.join(foreign)}")
        duration = data.get("target_duration_seconds", default_duration)
        if isinstance(duration, (int, float)) and abs(total_seconds - float(duration)) > 5:
            add_unique(errors, f"{label} 分场总时长 {total_seconds:g} 秒与目标 {duration} 秒相差超过 5 秒")
        if isinstance(number, int) and number not in plan_by_number:
            add_unique(errors, f"{label} 在 series_plan 中不存在")

    return {
        "ok": not errors,
        "series_root": str(series_root),
        "episode_count": len(episode_rows),
        "thresholds": {
            "adaptation_mode": "source_preserving_segmentation" if preserving_mode else "standard_adaptation",
            "source_char_soft_limit_per_90s": soft_rate,
            "source_char_hard_limit_per_90s": hard_rate,
            "min_seconds_per_effective_beat": MIN_SECONDS_PER_EFFECTIVE_BEAT,
        },
        "episodes": report_rows,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证小说改编分集容量")
    parser.add_argument("--series-root", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate(Path(args.series_root).expanduser().resolve())
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"容量验证通过：{result['episode_count']} 集")
        for warning in result["warnings"]:
            print(f"警告：{warning}")
    else:
        print("容量验证失败：", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
        for warning in result["warnings"]:
            print(f"- 警告：{warning}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
