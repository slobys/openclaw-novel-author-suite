#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from body_contract import canonical_body_bytes


def main():
    ap = argparse.ArgumentParser(description="Count deterministic Han-character chapter length")
    ap.add_argument("chapter_file")
    ap.add_argument("--hard-min", type=int, default=2000)
    ap.add_argument("--target-min", type=int, default=2600, help="Preferred target, not a revision trigger")
    ap.add_argument("--target-max", type=int, default=3200, help="Preferred upper bound, not a hard failure")
    ap.add_argument("--receipt")
    args = ap.parse_args()
    if min(args.hard_min, args.target_min, args.target_max) < 0:
        raise SystemExit("length thresholds must be non-negative")
    if args.target_min > args.target_max:
        raise SystemExit("target-min cannot exceed target-max")

    p = Path(args.chapter_file)
    body_bytes = canonical_body_bytes(p)
    text = body_bytes.decode("utf-8")
    text = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.M)
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    han = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text)
    non_ws = re.sub(r"\s+", "", text)
    result = {
        "file": str(p),
        "bodySha256": hashlib.sha256(body_bytes).hexdigest(),
        "hanChars": len(han),
        "nonWhitespaceChars": len(non_ws),
        "hardMinimumHanChars": args.hard_min,
        "targetMinHanChars": args.target_min,
        "targetMaxHanChars": args.target_max,
    }
    result["hardGatePass"] = result["hanChars"] >= args.hard_min
    result["targetRangePass"] = args.hard_min <= result["hanChars"] <= args.target_max
    result["preferredTargetReached"] = result["hanChars"] >= args.target_min
    result["overPreferredMax"] = result["hanChars"] > args.target_max
    if not result["hardGatePass"]:
        result["lengthDecision"] = "revise_once"
    elif result["overPreferredMax"]:
        result["lengthDecision"] = "accept_over_preferred_max"
    else:
        result["lengthDecision"] = "accept"
    if args.receipt:
        out = Path(args.receipt)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["hardGatePass"] else 2


if __name__ == "__main__":
    sys.exit(main())
