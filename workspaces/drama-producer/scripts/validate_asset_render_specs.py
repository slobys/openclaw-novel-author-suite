#!/usr/bin/env python3
"""Validate per-asset aspect ratio and one-subject/one-view declarations."""

import argparse
import json
import sys
from pathlib import Path


EXPECTED_RATIOS = {
    "character": "9:16",
    "creature": "9:16",
    "location": "16:9",
    "environment": "16:9",
    "prop": "9:16",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="校验资产单图规格")
    parser.add_argument("--job", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.job.read_text(encoding="utf-8"))
        assets = payload.get("assets")
        if not isinstance(assets, list) or not assets:
            raise ValueError("assets 必须是非空数组")
        errors = []
        for index, asset in enumerate(assets):
            asset_id = asset.get("asset_id") or f"assets[{index}]"
            kind = asset.get("asset_kind")
            role = asset.get("asset_role")
            if kind in EXPECTED_RATIOS:
                expected = EXPECTED_RATIOS[kind]
                if asset.get("aspect_ratio") != expected:
                    errors.append(f"{asset_id}: {kind} 必须使用 {expected}")
                if role != "video_reference":
                    errors.append(f"{asset_id}: 生产资产 asset_role 必须为 video_reference")
                if asset.get("layout_type") != "single_view_clean":
                    errors.append(f"{asset_id}: layout_type 必须为 single_view_clean")
                if not asset.get("angle_id"):
                    errors.append(f"{asset_id}: 缺少 angle_id")
                if asset.get("contains_multiple_independent_assets") is not False:
                    errors.append(f"{asset_id}: 必须明确不含多个独立资产")
            elif role == "video_reference":
                errors.append(f"{asset_id}: video_reference 使用了未知 asset_kind={kind!r}")
        if errors:
            raise ValueError("资产单图规格 Gate 失败:\n- " + "\n- ".join(errors))
        print(json.dumps({"ok": True, "gate": "asset_render_specs", "asset_count": len(assets)}, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
