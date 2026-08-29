#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from body_contract import canonical_body_bytes

GATE_VERSION = "v5.3.2"
HARD_MIN = 2000
TARGET_MIN = 2600
TARGET_MAX = 3200
REQUIRED_CHECKS = [
    "facts",
    "timeline",
    "space",
    "motivation",
    "knowledge",
    "worldRules",
    "resources",
    "causality",
    "foreshadowing",
    "originality",
    "voice",
    "sceneDynamics",
    "promiseFairness",
    "relationshipContinuity",
    "emotionCurve",
    "fatigueRisk",
    "oppositionPressure",
]
PASS_CHECK_STATUSES = {"pass", "passed", "ok", "clear", "not_applicable"}


def body_metrics(path: Path):
    raw = canonical_body_bytes(path)
    text = raw.decode("utf-8")
    cleaned = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.M)
    cleaned = re.sub(r"```.*?```", "", cleaned, flags=re.S)
    han = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", cleaned)
    non_ws = re.sub(r"\s+", "", cleaned)
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "hanChars": len(han),
        "nonWhitespaceChars": len(non_ws),
    }


def audit_conclusion(audit):
    for key in ("conclusion", "result", "status", "decision"):
        value = audit.get(key)
        if isinstance(value, str):
            return value.strip().lower()
    return None


def collect_issues(audit):
    issues = audit.get("issues", [])
    if not isinstance(issues, list):
        return []
    return [x for x in issues if isinstance(x, dict)]


def collect_checks(audit):
    source = audit.get("checks", audit.get("categories"))
    if isinstance(source, dict):
        return source
    if isinstance(source, list):
        output = {}
        for item in source:
            if isinstance(item, dict) and isinstance(item.get("category"), str):
                output[item["category"]] = item
        return output
    return None


def check_status(value):
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        for key in ("status", "result", "conclusion"):
            if isinstance(value.get(key), str):
                return value[key].strip().lower()
    return None


def find_body_hash(audit):
    candidates = [
        audit.get("bodySha256"),
        audit.get("body_sha256"),
        audit.get("chapterSha256"),
        audit.get("chapter_sha256"),
    ]
    gate = audit.get("gate")
    if isinstance(gate, dict):
        candidates += [gate.get("bodySha256"), gate.get("body_sha256")]
    for value in candidates:
        if isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value.strip()):
            return value.strip().lower()
    return None


def main():
    ap = argparse.ArgumentParser(description="Deterministic chapter precommit gate")
    ap.add_argument("chapter_file")
    ap.add_argument("audit_json")
    ap.add_argument("--payload-receipt", required=True)
    ap.add_argument("--quality-receipt", required=True)
    ap.add_argument("--receipt")
    ap.add_argument("--hard-min", type=int, default=HARD_MIN)
    ap.add_argument("--target-min", type=int, default=TARGET_MIN)
    ap.add_argument("--target-max", type=int, default=TARGET_MAX)
    args = ap.parse_args()

    chapter = Path(args.chapter_file)
    audit_path = Path(args.audit_json)
    reasons = []

    if not chapter.is_file():
        raise SystemExit(f"chapter file not found: {chapter}")
    if not audit_path.is_file():
        raise SystemExit(f"audit file not found: {audit_path}")

    metrics = body_metrics(chapter)
    payload_path = Path(args.payload_receipt)
    if not payload_path.is_file():
        raise SystemExit(f"payload receipt not found: {payload_path}")
    payload_bytes = payload_path.read_bytes()
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid payload receipt json: {exc}")
    if not isinstance(payload, dict):
        raise SystemExit("payload receipt must be an object")
    quality_path = Path(args.quality_receipt)
    if not quality_path.is_file():
        raise SystemExit(f"quality receipt not found: {quality_path}")
    quality_bytes = quality_path.read_bytes()
    try:
        quality = json.loads(quality_bytes.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid quality receipt json: {exc}")
    if not isinstance(quality, dict):
        raise SystemExit("quality receipt must be an object")

    audit_bytes = audit_path.read_bytes()
    try:
        audit = json.loads(audit_bytes.decode("utf-8"))
    except Exception as exc:
        raise SystemExit(f"invalid audit json: {exc}")
    if not isinstance(audit, dict):
        raise SystemExit("audit json must be an object")

    conclusion = audit_conclusion(audit)
    raw_issues = audit.get("issues")
    issues = collect_issues(audit)
    checks = collect_checks(audit)
    blocking = []
    for issue in issues:
        sev = str(issue.get("severity", "")).strip().lower()
        if sev in {"error", "block", "blocking", "fatal"}:
            blocking.append(issue)

    if metrics["hanChars"] < args.hard_min:
        reasons.append(f"CHAPTER_LENGTH_BELOW_MINIMUM:{metrics['hanChars']}<{args.hard_min}")
    if payload.get("payloadPass") is not True:
        reasons.append("CHAPTER_PAYLOAD_GATE_NOT_PASS")
    if quality.get("qualityPass") is not True:
        reasons.append("QUALITY_GATE_NOT_PASS")
    if quality.get("chapterNo") is not None and quality.get("chapterNo") != payload.get("chapterNo"):
        reasons.append("QUALITY_GATE_CHAPTER_NUMBER_MISMATCH")
    if quality.get("bodySha256") != metrics["sha256"]:
        reasons.append("QUALITY_GATE_BODY_HASH_MISMATCH")
    if payload.get("bodySha256") != metrics["sha256"]:
        reasons.append("CHAPTER_PAYLOAD_BODY_HASH_MISMATCH")
    if conclusion != "pass":
        reasons.append(f"PRECOMMIT_AUDIT_NOT_PASS:{conclusion!r}")
    if not isinstance(raw_issues, list) or len(issues) != len(raw_issues):
        reasons.append("PRECOMMIT_AUDIT_ISSUES_INVALID")
    if blocking:
        reasons.append(f"PRECOMMIT_AUDIT_HAS_BLOCKING_ISSUES:{len(blocking)}")
    if checks is None:
        reasons.append("PRECOMMIT_AUDIT_CHECKS_MISSING_OR_INVALID")
    else:
        missing_checks = [name for name in REQUIRED_CHECKS if name not in checks]
        if missing_checks:
            reasons.append("PRECOMMIT_AUDIT_CHECKS_MISSING:" + ",".join(missing_checks))
        failed_checks = [
            name
            for name in REQUIRED_CHECKS
            if name in checks and check_status(checks[name]) not in PASS_CHECK_STATUSES
        ]
        if failed_checks:
            reasons.append("PRECOMMIT_AUDIT_CHECKS_NOT_PASS:" + ",".join(failed_checks))

    expected_hash = find_body_hash(audit)
    if expected_hash is None:
        reasons.append("PRECOMMIT_BODY_HASH_MISSING")
    elif expected_hash != metrics["sha256"]:
        reasons.append("PRECOMMIT_BODY_HASH_MISMATCH")

    receipt = {
        "gateVersion": GATE_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "chapterFile": str(chapter),
        "auditFile": str(audit_path),
        "payloadReceiptFile": str(payload_path),
        "qualityReceiptFile": str(quality_path),
        "bodySha256": metrics["sha256"],
        "auditSha256": hashlib.sha256(audit_bytes).hexdigest(),
        "payloadReceiptSha256": hashlib.sha256(payload_bytes).hexdigest(),
        "qualityReceiptSha256": hashlib.sha256(quality_bytes).hexdigest(),
        "chapterNo": payload.get("chapterNo"),
        "pureTitle": payload.get("pureTitle"),
        "hanChars": metrics["hanChars"],
        "nonWhitespaceChars": metrics["nonWhitespaceChars"],
        "hardMinimumHanChars": args.hard_min,
        "targetMinHanChars": args.target_min,
        "targetMaxHanChars": args.target_max,
        "targetRangePass": args.hard_min <= metrics["hanChars"] <= args.target_max,
        "preferredTargetReached": metrics["hanChars"] >= args.target_min,
        "overPreferredMax": metrics["hanChars"] > args.target_max,
        "auditConclusion": conclusion,
        "blockingIssueCount": len(blocking),
        "requiredCheckCount": len(REQUIRED_CHECKS),
        "presentRequiredCheckCount": (
            sum(1 for name in REQUIRED_CHECKS if name in checks) if checks is not None else 0
        ),
        "auditBodyHashPresent": expected_hash is not None,
        "gatePass": not reasons,
        "reasons": reasons,
    }

    if args.receipt:
        out = Path(args.receipt)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["gatePass"] else 2


if __name__ == "__main__":
    sys.exit(main())
