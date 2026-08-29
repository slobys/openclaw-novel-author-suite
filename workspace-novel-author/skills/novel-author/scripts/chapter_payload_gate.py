#!/usr/bin/env python3
"""Validate chapter number, pure title and body separation before commit."""

import argparse
import json
import re
import sys
from pathlib import Path

from runtime_io import atomic_write_json
from body_contract import canonical_body_sha256, canonical_body_text


CHAPTER_PREFIX = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:第\s*[0-9零〇一二三四五六七八九十百千两]+\s*章|chapter\s+\d+)",
    flags=re.I,
)


def main():
    parser = argparse.ArgumentParser(description="Chapter payload title/body contract gate")
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--receipt")
    args = parser.parse_args()

    body_path = Path(args.body_file)
    if not body_path.is_file():
        raise SystemExit(f"body file not found: {body_path}")
    body = canonical_body_text(body_path)
    title = args.title.strip()
    first_nonempty = next((line.strip() for line in body.splitlines() if line.strip()), "")
    reasons = []

    if args.chapter < 1:
        reasons.append("CHAPTER_NUMBER_INVALID")
    if not title:
        reasons.append("TITLE_EMPTY")
    if title.startswith("#") or CHAPTER_PREFIX.match(title):
        reasons.append("TITLE_CONTAINS_CHAPTER_PREFIX")
    if first_nonempty.startswith("#") or CHAPTER_PREFIX.match(first_nonempty):
        reasons.append("BODY_CONTAINS_CHAPTER_HEADING")

    receipt = {
        "payloadGateVersion": "v1.0",
        "chapterNo": args.chapter,
        "pureTitle": title,
        "canonicalDisplayTitle": f"第{args.chapter}章 {title}" if title else None,
        "bodyFile": str(body_path),
        "bodySha256": canonical_body_sha256(body_path),
        "payloadPass": not reasons,
        "reasons": reasons,
    }
    if args.receipt:
        output = Path(args.receipt)
        atomic_write_json(output, receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["payloadPass"] else 2


if __name__ == "__main__":
    sys.exit(main())
