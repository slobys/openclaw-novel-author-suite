#!/usr/bin/env python3
"""Minimal scene asset queue manager for deepwhite-scene-pack-builder v3.2.0."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VALID_PROMPT = {"NOT_STARTED", "GENERATED", "REVISED"}
VALID_IMAGE = {"NOT_GENERATED", "GENERATED"}
VALID_REVIEW = {"UNREVIEWED", "APPROVED", "FAILED", "SUPERSEDED", "SKIPPED"}


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Manifest not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON: {exc}")
    if not isinstance(data.get("assets"), list):
        raise SystemExit("Manifest must contain an assets list")
    return data


def save_manifest(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve(data: dict[str, Any], target: str) -> dict[str, Any]:
    exact = []
    target_lower = target.lower()
    for asset in data["assets"]:
        keys = {
            str(asset.get("asset_id", "")).lower(),
            str(asset.get("series_id", "")).lower(),
            str(asset.get("code", "")).lower(),
            str(asset.get("title", "")).lower(),
        }
        if target_lower in keys:
            exact.append(asset)
    if not exact:
        partial = [a for a in data["assets"] if target_lower in str(a.get("title", "")).lower()]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            raise SystemExit("ASSET_AMBIGUOUS: " + ", ".join(a.get("asset_id", "?") for a in partial))
        raise SystemExit(f"ASSET_NOT_FOUND: {target}")
    if len(exact) > 1:
        raise SystemExit("ASSET_AMBIGUOUS: " + ", ".join(a.get("asset_id", "?") for a in exact))
    return exact[0]


def display_status(asset: dict[str, Any]) -> str:
    review = asset.get("review_status", "UNREVIEWED")
    if review in {"APPROVED", "FAILED", "SUPERSEDED", "SKIPPED"}:
        return review
    if asset.get("image_status") == "GENERATED":
        return "IMAGE_READY"
    if asset.get("prompt_status") in {"GENERATED", "REVISED"}:
        return "PROMPT_READY"
    return "PLANNED"


def cmd_list(data: dict[str, Any], filter_name: str | None) -> None:
    assets = data["assets"]
    if filter_name == "pending":
        assets = [a for a in assets if a.get("prompt_status") == "NOT_STARTED"]
    elif filter_name == "failed":
        assets = [a for a in assets if a.get("review_status") == "FAILED"]
    elif filter_name == "review":
        assets = [a for a in assets if a.get("image_status") == "GENERATED" and a.get("review_status") == "UNREVIEWED"]
    elif filter_name == "approved":
        assets = [a for a in assets if a.get("review_status") == "APPROVED"]

    print("order\tcode\tasset_id\ttitle\tstatus\tcurrent")
    for a in sorted(assets, key=lambda x: int(x.get("order", 0))):
        print(f"{a.get('order')}\t{a.get('code')}\t{a.get('asset_id')}\t{a.get('title','')}\t{display_status(a)}\t{bool(a.get('current'))}")


def dependencies_met(data: dict[str, Any], asset: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = []
    for dep in asset.get("dependencies", []):
        try:
            dep_asset = resolve(data, dep)
        except SystemExit:
            missing.append(f"{dep}(not found)")
            continue
        if dep_asset.get("review_status") != "APPROVED":
            missing.append(dep_asset.get("series_id", dep))
    return not missing, missing


def cmd_next(data: dict[str, Any]) -> None:
    assets = sorted(data["assets"], key=lambda x: int(x.get("order", 0)))
    failed = [a for a in assets if a.get("review_status") == "FAILED"]
    if failed:
        a = failed[0]
        print(f"RETRY_REQUIRED\t{a.get('asset_id')}\t{a.get('failure_reason') or ''}")
        return
    for a in assets:
        if a.get("review_status") in {"APPROVED", "SUPERSEDED", "SKIPPED"}:
            continue
        ok, missing = dependencies_met(data, a)
        if ok:
            print(a.get("asset_id"))
            return
    remaining = [a for a in assets if a.get("review_status") not in {"APPROVED", "SUPERSEDED", "SKIPPED"}]
    if remaining:
        print("ASSET_BLOCKED_BY_DEPENDENCY")
    else:
        print("ASSET_QUEUE_COMPLETE")


def cmd_set_status(data: dict[str, Any], target: str, prompt: str | None, image: str | None, review: str | None, reason: str | None) -> None:
    asset = resolve(data, target)
    if prompt:
        if prompt not in VALID_PROMPT:
            raise SystemExit(f"Invalid prompt status: {prompt}")
        asset["prompt_status"] = prompt
    if image:
        if image not in VALID_IMAGE:
            raise SystemExit(f"Invalid image status: {image}")
        asset["image_status"] = image
    if review:
        if review not in VALID_REVIEW:
            raise SystemExit(f"Invalid review status: {review}")
        asset["review_status"] = review
    if reason is not None:
        asset["failure_reason"] = reason
    print(asset.get("asset_id"))


def cmd_jump(data: dict[str, Any], target: str) -> None:
    asset = resolve(data, target)
    for a in data["assets"]:
        a["current"] = False
    asset["current"] = True
    data["current_asset_series_id"] = asset.get("series_id")
    print(asset.get("asset_id"))


def cmd_retry(data: dict[str, Any], target: str, reason: str | None) -> None:
    old = resolve(data, target)
    old["review_status"] = "SUPERSEDED"
    old["current"] = False
    version = int(old.get("version", 1)) + 1
    new = dict(old)
    new["version"] = version
    new["asset_id"] = f"{old['series_id']}-v{version:03d}"
    new["prompt_status"] = "NOT_STARTED"
    new["image_status"] = "NOT_GENERATED"
    new["review_status"] = "UNREVIEWED"
    new["failure_reason"] = reason
    new["current"] = True
    data["assets"].append(new)
    data["current_asset_series_id"] = new["series_id"]
    print(new["asset_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--filter", choices=["pending", "failed", "review", "approved"])
    sub.add_parser("next")

    p_get = sub.add_parser("get")
    p_get.add_argument("target")

    p_jump = sub.add_parser("jump")
    p_jump.add_argument("target")

    p_status = sub.add_parser("set-status")
    p_status.add_argument("target")
    p_status.add_argument("--prompt", choices=sorted(VALID_PROMPT))
    p_status.add_argument("--image", choices=sorted(VALID_IMAGE))
    p_status.add_argument("--review", choices=sorted(VALID_REVIEW))
    p_status.add_argument("--reason")

    p_retry = sub.add_parser("retry")
    p_retry.add_argument("target")
    p_retry.add_argument("--reason")

    args = parser.parse_args()
    data = load_manifest(args.manifest)

    if args.cmd == "list":
        cmd_list(data, args.filter)
    elif args.cmd == "next":
        cmd_next(data)
    elif args.cmd == "get":
        print(json.dumps(resolve(data, args.target), ensure_ascii=False, indent=2))
    elif args.cmd == "jump":
        cmd_jump(data, args.target)
        save_manifest(args.manifest, data)
    elif args.cmd == "set-status":
        cmd_set_status(data, args.target, args.prompt, args.image, args.review, args.reason)
        save_manifest(args.manifest, data)
    elif args.cmd == "retry":
        cmd_retry(data, args.target, args.reason)
        save_manifest(args.manifest, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
