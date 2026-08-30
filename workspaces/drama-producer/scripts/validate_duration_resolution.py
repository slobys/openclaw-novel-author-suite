#!/usr/bin/env python3
"""Ensure timing follows drama-producer's resolved duration, not upstream padding."""

import argparse
import json
import sys
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="校验系列参考时长解析")
    parser.add_argument("--resolution", required=True, type=Path)
    parser.add_argument("--timing-plan", required=True, type=Path)
    args = parser.parse_args()
    try:
        resolution = read(args.resolution)
        timing = read(args.timing_plan)
        errors = []
        resolved = resolution.get("resolved_duration_seconds")
        if not isinstance(resolved, (int, float)) or resolved <= 0:
            errors.append("resolved_duration_seconds 必须为正数")
        if resolution.get("upstream_duration_is_advisory") is not True:
            errors.append("必须明确 upstream_duration_is_advisory=true")
        if resolution.get("duration_authority") != "drama-producer":
            errors.append("duration_authority 必须为 drama-producer")
        if resolution.get("no_padding_to_match_reference") is not True:
            errors.append("必须明确 no_padding_to_match_reference=true")
        if not resolution.get("decision_basis"):
            errors.append("缺少 decision_basis")
        total = timing.get("total_duration_seconds")
        if isinstance(resolved, (int, float)) and total != resolved:
            errors.append(f"timing_plan总时长 {total!r} 不等于 resolved_duration_seconds {resolved!r}")
        if errors:
            raise ValueError("实际时长 Gate 失败:\n- " + "\n- ".join(errors))
        print(json.dumps({"ok": True, "gate": "duration_resolution", "resolved_duration_seconds": resolved, "upstream_reference_seconds": resolution.get("upstream_reference_seconds")}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
