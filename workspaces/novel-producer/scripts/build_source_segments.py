#!/usr/bin/env python3
"""Split chapter files into exact, ordered, lossless source segments."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def candidate_boundaries(text: str) -> list[int]:
    points = {match.end() for match in re.finditer(r"\n[ \t]*\n", text)}
    points.update(match.end() for match in re.finditer(r"[。！？!?；;](?:[”’\"']?)", text))
    points.add(len(text))
    return sorted(point for point in points if point > 0)


def split_ranges(text: str, target: int, minimum: int, maximum: int) -> list[tuple[int, int]]:
    boundaries = candidate_boundaries(text)
    ranges: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        remaining = len(text) - start
        if remaining <= maximum:
            ranges.append((start, len(text)))
            break
        lower = min(len(text), start + minimum)
        upper = min(len(text), start + maximum)
        choices = [
            point for point in boundaries
            if lower <= point <= upper and (len(text) - point == 0 or len(text) - point >= minimum)
        ]
        if choices:
            preferred = min(choices, key=lambda point: (abs(point - (start + target)), point))
            end = preferred
        else:
            later = next((point for point in boundaries if point > start), len(text))
            end = min(later, upper)
        if end <= start:
            end = min(len(text), start + maximum)
        ranges.append((start, end))
        start = end
    return ranges


def main() -> int:
    parser = argparse.ArgumentParser(description="建立无损小说原文分段")
    parser.add_argument("--series-root", required=True)
    parser.add_argument("--target-chars", type=int, default=350)
    parser.add_argument("--min-chars", type=int, default=200)
    parser.add_argument("--max-chars", type=int, default=500)
    args = parser.parse_args()
    if not 1 <= args.min_chars <= args.target_chars <= args.max_chars:
        raise SystemExit("必须满足 1 <= min-chars <= target-chars <= max-chars")

    root = Path(args.series_root).expanduser().resolve()
    index_path = root / "chapters" / "chapter_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    out_dir = root / "segments" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    segments: list[dict] = []
    global_order = 0
    total_chars = 0
    for chapter in index.get("chapters", []):
        chapter_id = str(chapter["chapter_id"])
        source_path = root / str(chapter["relative_path"])
        text = source_path.read_text(encoding="utf-8")
        total_chars += len(text)
        ranges = split_ranges(text, args.target_chars, args.min_chars, args.max_chars)
        for local_order, (start, end) in enumerate(ranges, start=1):
            global_order += 1
            segment_id = f"SEG-{chapter_id}-{local_order:03d}"
            segment_text = text[start:end]
            relative_path = f"segments/raw/{segment_id}.txt"
            (root / relative_path).write_text(segment_text, encoding="utf-8")
            segments.append({
                "segment_id": segment_id,
                "global_order": global_order,
                "chapter_id": chapter_id,
                "chapter_order": chapter.get("order"),
                "chapter_segment_order": local_order,
                "source_char_start": start,
                "source_char_end": end,
                "char_count": len(segment_text),
                "source_sha256": sha256_text(segment_text),
                "relative_path": relative_path,
                "preservation_required": True,
                "assignment_status": "unassigned",
                "representation_status": "unassigned"
            })

    manifest = {
        "schema_version": "1.0",
        "series_id": index.get("series_id"),
        "adaptation_mode": "source_preserving_segmentation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_chapter_count": index.get("chapter_count"),
        "source_char_count": total_chars,
        "segment_count": len(segments),
        "segmentation_policy": {
            "target_chars": args.target_chars,
            "min_chars": args.min_chars,
            "max_chars": args.max_chars,
            "boundary_priority": ["paragraph", "sentence", "hard_limit"]
        },
        "segments": segments
    }
    manifest_path = root / "segments" / "source_segments.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "chapter_count": index.get("chapter_count"),
        "segment_count": len(segments),
        "source_char_count": total_chars,
        "manifest": str(manifest_path)
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
