#!/usr/bin/env python3
"""Validate that series episode durations are advisory for drama-producer."""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="校验分集时长交接语义")
    parser.add_argument("--series-root", required=True, type=Path)
    args = parser.parse_args()
    episodes = sorted((args.series_root / "episodes").glob("episode_*.json"))
    if not episodes:
        print("未找到 episodes/episode_*.json", file=sys.stderr)
        return 2
    errors = []
    for path in episodes:
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: 无法读取: {exc}")
            continue
        reference = row.get("duration_reference_seconds")
        target = row.get("target_duration_seconds")
        if not isinstance(reference, (int, float)) or reference <= 0:
            errors.append(f"{path.name}: duration_reference_seconds 必须为正数")
        if isinstance(target, (int, float)) and reference != target:
            errors.append(f"{path.name}: duration_reference_seconds 必须复制规划 target_duration_seconds")
        if row.get("duration_policy") != "downstream_resolved_by_effective_beats":
            errors.append(f"{path.name}: duration_policy 不正确")
        if row.get("duration_authority") != "drama-producer":
            errors.append(f"{path.name}: duration_authority 必须为 drama-producer")
    if errors:
        print("时长交接 Gate 失败:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, "episode_count": len(episodes), "duration_policy": "downstream_resolved_by_effective_beats"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
