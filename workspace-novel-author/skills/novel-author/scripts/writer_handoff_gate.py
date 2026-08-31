#!/usr/bin/env python3
"""Validate an isolated Writer's file-based chapter handoff without another model pass."""

import argparse
import json
import re
import sys
from pathlib import Path

from body_contract import canonical_body_sha256, canonical_body_text
from runtime_io import atomic_write_json


AUDIT_CATEGORIES = [
    "facts", "timeline", "space", "motivation", "knowledge", "worldRules",
    "resources", "causality", "foreshadowing", "originality", "voice",
    "sceneDynamics", "promiseFairness", "relationshipContinuity", "emotionCurve",
    "fatigueRisk", "oppositionPressure",
]
BLOCKING_SEVERITIES = {"error", "block", "fatal"}


def status_of(value):
    if isinstance(value, str):
        return value.strip().lower()
    if isinstance(value, dict):
        return str(value.get("status", "")).strip().lower()
    return ""


def main():
    parser = argparse.ArgumentParser(description="Validate isolated Writer chapter and audit handoff")
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--writer-session-id", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--audit-file", required=True)
    parser.add_argument("--hard-min", type=int, default=2000)
    parser.add_argument("--receipt")
    args = parser.parse_args()

    body_path = Path(args.body_file)
    audit_path = Path(args.audit_file)
    reasons = []
    if not body_path.is_file():
        raise SystemExit(f"body file not found: {body_path}")
    if not audit_path.is_file():
        raise SystemExit(f"writer audit file not found: {audit_path}")
    writer_session_id = args.writer_session_id.strip()
    if not writer_session_id:
        raise SystemExit("writer-session-id must not be empty")

    body = canonical_body_text(body_path)
    body_sha256 = canonical_body_sha256(body_path)
    han_chars = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", body))
    try:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid writer audit json: {exc}")
    if not isinstance(audit, dict):
        raise SystemExit("writer audit must be a JSON object")

    if han_chars < args.hard_min:
        reasons.append(f"WRITER_BODY_BELOW_HARD_MIN:{han_chars}<{args.hard_min}")
    if audit.get("chapterNo") not in {None, args.chapter}:
        reasons.append("WRITER_AUDIT_CHAPTER_MISMATCH")
    if audit.get("bodySha256") != body_sha256:
        reasons.append("WRITER_AUDIT_BODY_HASH_MISMATCH")
    if str(audit.get("decision", audit.get("conclusion", ""))).lower() != "pass":
        reasons.append("WRITER_AUDIT_DECISION_NOT_PASS")

    checks = audit.get("checks")
    if not isinstance(checks, dict):
        reasons.append("WRITER_AUDIT_CHECKS_INVALID")
        checks = {}
    missing = [name for name in AUDIT_CATEGORIES if name not in checks]
    if missing:
        reasons.append("WRITER_AUDIT_CHECKS_MISSING:" + ",".join(missing))
    not_pass = [name for name in AUDIT_CATEGORIES if name in checks and status_of(checks[name]) != "pass"]
    if not_pass:
        reasons.append("WRITER_AUDIT_CHECKS_NOT_PASS:" + ",".join(not_pass))

    issues = audit.get("issues", [])
    if not isinstance(issues, list):
        reasons.append("WRITER_AUDIT_ISSUES_INVALID")
        issues = []
    blocking = [
        issue for issue in issues
        if isinstance(issue, dict) and str(issue.get("severity", "")).lower() in BLOCKING_SEVERITIES
    ]
    if blocking:
        reasons.append(f"WRITER_AUDIT_BLOCKING_ISSUES:{len(blocking)}")

    receipt = {
        "handoffVersion": "v1.0",
        "chapterNo": args.chapter,
        "writerSessionId": writer_session_id,
        "bodyFile": str(body_path),
        "bodySha256": body_sha256,
        "hanChars": han_chars,
        "hardMinimumHanChars": args.hard_min,
        "auditFile": str(audit_path),
        "auditCategories": AUDIT_CATEGORIES,
        "handoffPass": not reasons,
        "reasons": reasons,
    }
    if args.receipt:
        atomic_write_json(Path(args.receipt), receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["handoffPass"] else 2


if __name__ == "__main__":
    sys.exit(main())
