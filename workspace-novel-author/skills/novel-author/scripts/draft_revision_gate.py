#!/usr/bin/env python3
"""Prove that the one allowed automatic length revision changed the draft."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from body_contract import canonical_body_bytes


def main():
    ap = argparse.ArgumentParser(description="Block unchanged or repeated automatic draft revisions")
    ap.add_argument("--before-receipt", required=True)
    ap.add_argument("--after-file", required=True)
    ap.add_argument("--attempt", type=int, required=True)
    ap.add_argument("--max-auto-revisions", type=int, default=1)
    ap.add_argument("--hard-min", type=int, default=2000)
    ap.add_argument("--receipt")
    args = ap.parse_args()

    before = json.loads(Path(args.before_receipt).read_text(encoding="utf-8"))
    before_sha = str(before.get("bodySha256", "")).lower()
    before_han = before.get("hanChars")
    raw = canonical_body_bytes(Path(args.after_file))
    text = raw.decode("utf-8")
    after_sha = hashlib.sha256(raw).hexdigest()
    after_han = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))

    reasons = []
    if args.attempt < 1 or args.attempt > args.max_auto_revisions:
        reasons.append("AUTO_REVISION_LIMIT_EXCEEDED")
    if not re.fullmatch(r"[0-9a-f]{64}", before_sha):
        reasons.append("BEFORE_BODY_HASH_MISSING")
    elif before_sha == after_sha:
        reasons.append("DRAFT_BODY_UNCHANGED")
    if not isinstance(before_han, int):
        reasons.append("BEFORE_HAN_COUNT_MISSING")
    if after_han < args.hard_min:
        reasons.append("DRAFT_STILL_BELOW_HARD_MINIMUM")

    result = {
        "draftRevisionGateVersion": "v1.0",
        "attempt": args.attempt,
        "maxAutoRevisions": args.max_auto_revisions,
        "beforeBodySha256": before_sha,
        "afterBodySha256": after_sha,
        "beforeHanChars": before_han,
        "afterHanChars": after_han,
        "hanDelta": after_han - before_han if isinstance(before_han, int) else None,
        "hardMinimumHanChars": args.hard_min,
        "draftChanged": before_sha != after_sha,
        "revisionPass": not reasons,
        "reasons": reasons,
    }
    if args.receipt:
        out = Path(args.receipt)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["revisionPass"] else 2


if __name__ == "__main__":
    sys.exit(main())
