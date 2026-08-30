#!/usr/bin/env python3
"""Validate exact source coverage and optional episode assignment."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(root: Path, require_assignment: bool) -> dict:
    errors: list[str] = []
    index_path = root / "chapters" / "chapter_index.json"
    manifest_path = root / "segments" / "source_segments.json"
    if not index_path.is_file() or not manifest_path.is_file():
        return {"ok": False, "errors": ["缺少 chapter_index.json 或 source_segments.json"]}
    index = read_json(index_path)
    manifest = read_json(manifest_path)
    if not isinstance(index, dict) or not isinstance(manifest, dict):
        return {"ok": False, "errors": ["索引或分段清单顶层不是对象"]}
    rows = manifest.get("segments", [])
    if not isinstance(rows, list) or not rows:
        return {"ok": False, "errors": ["分段清单为空"]}

    by_chapter: dict[str, list[dict]] = defaultdict(list)
    seen_ids: set[str] = set()
    global_orders: list[int] = []
    total_segment_chars = 0
    for row in rows:
        if not isinstance(row, dict):
            errors.append("分段清单存在非对象")
            continue
        segment_id = str(row.get("segment_id", ""))
        if not segment_id or segment_id in seen_ids:
            errors.append(f"分段 ID 缺失或重复：{segment_id}")
        seen_ids.add(segment_id)
        chapter_id = str(row.get("chapter_id", ""))
        by_chapter[chapter_id].append(row)
        if isinstance(row.get("global_order"), int):
            global_orders.append(row["global_order"])
        else:
            errors.append(f"{segment_id} 缺少 global_order")
        if row.get("preservation_required") is not True:
            errors.append(f"{segment_id} preservation_required 必须为 true")

    if global_orders != list(range(1, len(rows) + 1)):
        errors.append("全局分段顺序不连续或已乱序")

    chapter_rows = index.get("chapters", [])
    total_source_chars = 0
    for chapter in chapter_rows:
        chapter_id = str(chapter.get("chapter_id"))
        source_path = root / str(chapter.get("relative_path"))
        source_text = source_path.read_text(encoding="utf-8")
        total_source_chars += len(source_text)
        cursor = 0
        for row in sorted(by_chapter.get(chapter_id, []), key=lambda item: item.get("source_char_start", -1)):
            segment_id = str(row.get("segment_id"))
            start = row.get("source_char_start")
            end = row.get("source_char_end")
            if not isinstance(start, int) or not isinstance(end, int) or start != cursor or end <= start:
                errors.append(f"{segment_id} 与章节 {chapter_id} 存在缺口、重叠或非法范围")
                continue
            expected = source_text[start:end]
            segment_path = root / str(row.get("relative_path", ""))
            if not segment_path.is_file():
                errors.append(f"{segment_id} 分段文件不存在")
                cursor = end
                continue
            actual = segment_path.read_text(encoding="utf-8")
            if actual != expected:
                errors.append(f"{segment_id} 分段文本与原文不一致")
            if row.get("char_count") != len(expected):
                errors.append(f"{segment_id} char_count 不一致")
            if row.get("source_sha256") != sha256_text(expected):
                errors.append(f"{segment_id} SHA256 不一致")
            total_segment_chars += len(expected)
            cursor = end
        if cursor != len(source_text):
            errors.append(f"章节 {chapter_id} 未被完整覆盖：{cursor}/{len(source_text)}")

    if manifest.get("source_char_count") != total_source_chars:
        errors.append(f"manifest.source_char_count 必须为实际原文字符数 {total_source_chars}")
    if total_segment_chars != total_source_chars:
        errors.append(f"分段覆盖字符数 {total_segment_chars} 与实际原文 {total_source_chars} 不一致")

    episode_segment_ids: list[str] = []
    if require_assignment:
        plan_path = root / "plan" / "series_plan.json"
        if not plan_path.is_file():
            errors.append("要求分集映射但缺少 series_plan.json")
        else:
            plan = read_json(plan_path)
            for episode in plan.get("episodes", []) if isinstance(plan, dict) else []:
                ids = episode.get("source_segment_ids") if isinstance(episode, dict) else None
                if not isinstance(ids, list) or not ids:
                    errors.append("分集缺少连续 source_segment_ids")
                else:
                    episode_segment_ids.extend(str(item) for item in ids)
            expected_ids = [str(row.get("segment_id")) for row in rows]
            if episode_segment_ids != expected_ids:
                missing = sorted(set(expected_ids) - set(episode_segment_ids))
                duplicates = sorted({item for item in episode_segment_ids if episode_segment_ids.count(item) > 1})
                errors.append(f"源段分集映射不是完整顺序覆盖；缺失={missing[:10]}，重复={duplicates[:10]}")

        briefs: list[tuple[int, dict, Path]] = []
        for brief_path in sorted((root / "episodes").glob("episode_*.json")):
            brief = read_json(brief_path)
            if not isinstance(brief, dict):
                errors.append(f"{brief_path.name} 顶层不是对象")
                continue
            number = brief.get("episode_number")
            if not isinstance(number, int):
                errors.append(f"{brief_path.name} 缺少 episode_number")
                continue
            briefs.append((number, brief, brief_path))
        previous_end_state: object | None = None
        previous_end_hash: str | None = None
        allowed_modes = {
            "spoken_dialogue", "voiceover", "visual_action", "environment_visual",
            "expression_or_relationship", "prop_or_text_insert"
        }
        for number, brief, brief_path in sorted(briefs, key=lambda item: item[0]):
            label = brief_path.name
            brief_segment_ids = brief.get("source_segment_ids")
            if not isinstance(brief_segment_ids, list) or not brief_segment_ids:
                errors.append(f"{label} 缺少 source_segment_ids")
                brief_segment_ids = []
            mappings = brief.get("representation_map")
            if not isinstance(mappings, list) or not mappings:
                errors.append(f"{label} 缺少 representation_map")
                mappings = []
            mapped_ids: list[str] = []
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    errors.append(f"{label} representation_map 存在非对象")
                    continue
                segment_id = str(mapping.get("segment_id", ""))
                mode = mapping.get("representation_mode")
                if segment_id:
                    mapped_ids.append(segment_id)
                if mode not in allowed_modes:
                    errors.append(f"{label} 的 {segment_id} 呈现方式无效：{mode}")
                if mapping.get("omitted") is True:
                    errors.append(f"{label} 的 {segment_id} 不得标记 omitted")
            if mapped_ids != [str(item) for item in brief_segment_ids]:
                errors.append(f"{label} representation_map 必须按顺序逐段覆盖 source_segment_ids")

            handoff = brief.get("boundary_handoff")
            if not isinstance(handoff, dict):
                errors.append(f"{label} 缺少 boundary_handoff")
                continue
            start_state = handoff.get("start_state")
            end_state = handoff.get("end_state")
            if not isinstance(start_state, dict) or not isinstance(end_state, dict):
                errors.append(f"{label} boundary_handoff 必须包含 start_state 与 end_state")
                continue
            if previous_end_state is not None and start_state != previous_end_state:
                errors.append(f"{label} start_state 与上一集 end_state 不一致")
            if previous_end_hash is not None and handoff.get("previous_end_state_sha256") != previous_end_hash:
                errors.append(f"{label} previous_end_state_sha256 与上一集不一致")
            computed_end_hash = canonical_sha256(end_state)
            if handoff.get("end_state_sha256") != computed_end_hash:
                errors.append(f"{label} end_state_sha256 校验失败")
            previous_end_state = end_state
            previous_end_hash = computed_end_hash

    return {
        "ok": not errors,
        "series_root": str(root),
        "chapter_count": len(chapter_rows),
        "segment_count": len(rows),
        "source_char_count": total_source_chars,
        "covered_char_count": total_segment_chars,
        "require_assignment": require_assignment,
        "errors": errors
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="验证原文保全分段")
    parser.add_argument("--series-root", required=True)
    parser.add_argument("--require-assignment", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate(Path(args.series_root).expanduser().resolve(), args.require_assignment)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"原文保全验证通过：{result['chapter_count']}章，{result['segment_count']}段，{result['covered_char_count']}字")
    else:
        print("原文保全验证失败：", file=sys.stderr)
        for error in result["errors"]:
            print(f"- {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
