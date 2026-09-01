#!/usr/bin/env python3
"""Materialize tool-limited Writer/Reviewer session returns in the parent workspace.

Leaf isolated sessions are not trusted to write files or call Novel Engine tools.
They return one strict JSON envelope. The parent session saves that response to a
temporary UTF-8 file, supplies the real child session ID, and runs this script.
The script canonicalizes the body, computes its SHA-256, binds the audit/review
to the real session, and atomically writes the evidence files.
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from body_contract import canonical_body_sha256
from runtime_io import atomic_write_json, atomic_write_text, utc_now


WRITER_SCHEMA = "novel-writer-return-v1"
REVIEW_SCHEMA = "novel-review-return-v1"
ROLES = {"continuity-auditor", "reader-editor"}


def fail(message):
    raise SystemExit(message)


def load_envelope(path):
    raw = Path(path).read_text(encoding="utf-8").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n([\s\S]*?)\n```", raw, flags=re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"session return is not one valid JSON object: {exc}")
    if not isinstance(value, dict):
        fail("session return must be a JSON object")
    return value


def canonical_text(value):
    if not isinstance(value, str):
        fail("body must be a string")
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        fail("body must not be empty")
    return normalized


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_chapter(envelope, expected):
    if envelope.get("chapterNo") != expected:
        fail(f"chapterNo mismatch: expected {expected}, got {envelope.get('chapterNo')!r}")


def require_optional_binding(envelope, key, expected):
    supplied = envelope.get(key)
    if supplied not in {None, ""} and supplied != expected:
        fail(f"{key} mismatch")


def materialize_writer(args):
    envelope = load_envelope(args.input)
    if envelope.get("schemaVersion") != WRITER_SCHEMA:
        fail(f"schemaVersion must be {WRITER_SCHEMA}")
    require_chapter(envelope, args.chapter)

    session_id = args.writer_session_id.strip()
    if not session_id:
        fail("writer-session-id must not be empty")
    require_optional_binding(envelope, "writerSessionId", session_id)

    title = envelope.get("title")
    if not isinstance(title, str) or not title.strip():
        fail("title must be a non-empty string")
    title = title.strip()
    if len(title) > 200:
        fail("title is too long")
    if re.search(r"第\s*[0-9一二三四五六七八九十百千]+\s*章", title):
        fail("title must not contain a chapter-number prefix")

    plan = envelope.get("plan")
    audit = envelope.get("audit")
    if not isinstance(plan, dict):
        fail("plan must be a JSON object")
    if not isinstance(audit, dict):
        fail("audit must be a JSON object")

    body = canonical_text(envelope.get("body"))
    body_sha256 = sha256_text(body)
    require_optional_binding(envelope, "bodySha256", body_sha256)
    require_optional_binding(audit, "bodySha256", body_sha256)
    require_optional_binding(audit, "writerSessionId", session_id)
    if audit.get("chapterNo") not in {None, args.chapter}:
        fail("audit.chapterNo mismatch")

    output_dir = Path(args.output_dir)
    body_path = output_dir / "chapter.md"
    plan_path = output_dir / "plan.json"
    audit_path = output_dir / "writer-audit.json"
    receipt_path = Path(args.receipt) if args.receipt else output_dir / "writer-materialize-receipt.json"

    normalized_plan = dict(plan)
    normalized_plan["chapterNo"] = args.chapter
    normalized_plan["title"] = title
    normalized_audit = dict(audit)
    normalized_audit["chapterNo"] = args.chapter
    normalized_audit["bodySha256"] = body_sha256
    normalized_audit["writerSessionId"] = session_id

    atomic_write_text(body_path, body + "\n", backup=False)
    atomic_write_json(plan_path, normalized_plan, backup=False)
    atomic_write_json(audit_path, normalized_audit, backup=False)

    receipt = {
        "materializeVersion": "v1.0",
        "schemaVersion": WRITER_SCHEMA,
        "createdAt": utc_now(),
        "chapterNo": args.chapter,
        "title": title,
        "writerSessionId": session_id,
        "bodyFile": str(body_path),
        "bodySha256": canonical_body_sha256(body_path),
        "planFile": str(plan_path),
        "auditFile": str(audit_path),
        "sourceReturnFile": str(Path(args.input)),
        "materializePass": True,
    }
    atomic_write_json(receipt_path, receipt, backup=False)
    print(json.dumps(receipt, ensure_ascii=False))


def materialize_reviewer(args):
    envelope = load_envelope(args.input)
    if envelope.get("schemaVersion") != REVIEW_SCHEMA:
        fail(f"schemaVersion must be {REVIEW_SCHEMA}")
    require_chapter(envelope, args.chapter)
    if args.role not in ROLES:
        fail(f"unsupported reviewer role: {args.role}")
    if envelope.get("reviewerRole") != args.role:
        fail("reviewerRole mismatch")

    session_id = args.reviewer_session_id.strip()
    if not session_id:
        fail("reviewer-session-id must not be empty")
    require_optional_binding(envelope, "reviewerSessionId", session_id)

    body_sha256 = canonical_body_sha256(Path(args.body_file))
    require_optional_binding(envelope, "bodySha256", body_sha256)
    checks = envelope.get("checks")
    issues = envelope.get("issues", [])
    conclusion = str(envelope.get("conclusion", "")).strip().lower()
    if not isinstance(checks, dict):
        fail("checks must be a JSON object")
    if not isinstance(issues, list):
        fail("issues must be an array")
    if conclusion not in {"pass", "revise", "block"}:
        fail("conclusion must be pass, revise or block")

    review = {
        "reviewerRole": args.role,
        "reviewerSessionId": session_id,
        "bodySha256": body_sha256,
        "conclusion": conclusion,
        "checks": checks,
        "issues": issues,
        "summary": str(envelope.get("summary", "")),
        "sourceReturnFile": str(Path(args.input)),
        "materializedAt": utc_now(),
    }
    atomic_write_json(Path(args.output), review, backup=False)
    print(json.dumps(review, ensure_ascii=False))


def build_parser():
    parser = argparse.ArgumentParser(description="Materialize an isolated session JSON return")
    sub = parser.add_subparsers(dest="command", required=True)

    writer = sub.add_parser("writer")
    writer.add_argument("--input", required=True)
    writer.add_argument("--output-dir", required=True)
    writer.add_argument("--chapter", type=int, required=True)
    writer.add_argument("--writer-session-id", required=True)
    writer.add_argument("--receipt")
    writer.set_defaults(func=materialize_writer)

    reviewer = sub.add_parser("reviewer")
    reviewer.add_argument("--input", required=True)
    reviewer.add_argument("--output", required=True)
    reviewer.add_argument("--body-file", required=True)
    reviewer.add_argument("--chapter", type=int, required=True)
    reviewer.add_argument("--role", required=True)
    reviewer.add_argument("--reviewer-session-id", required=True)
    reviewer.set_defaults(func=materialize_reviewer)
    return parser


def main():
    args = build_parser().parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
