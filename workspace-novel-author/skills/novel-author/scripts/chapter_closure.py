#!/usr/bin/env python3
"""Durable Agent-side outbox and integrity gate for post-commit closure."""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime_io import atomic_write_json, file_lock

DEFAULT_OPERATIONS = [
    "causal_events",
    "foreshadowing",
    "promise_payoff",
    "relationship_graph",
    "opposition_clocks",
    "chapter_signature",
    "dynamic_state",
    "memory_index",
]
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")


def now():
    return datetime.now(timezone.utc).isoformat()


def load(path: Path):
    if not path.is_file():
        raise SystemExit(f"closure manifest not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"closure manifest is corrupt: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("operations"), dict):
        raise SystemExit("invalid closure manifest schema")
    return data


def validate_hash(value, label):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise SystemExit(f"{label} must be a 64-character sha256")
    return value.lower()


def mutate(args, callback):
    path = Path(args.manifest)
    with file_lock(path):
        data = load(path)
        actual = int(data.get("revision", 0))
        if actual != args.expect_revision:
            raise SystemExit(
                f"revision conflict: expected {args.expect_revision}, actual {actual}; reload before retry"
            )
        callback(data)
        data["revision"] = actual + 1
        data["updatedAt"] = now()
        atomic_write_json(path, data)
    return data


def cmd_init(args):
    path = Path(args.manifest)
    operations = args.operation or DEFAULT_OPERATIONS
    if len(set(operations)) != len(operations):
        raise SystemExit("duplicate closure operation")
    body_sha = validate_hash(args.body_sha256, "--body-sha256")
    with file_lock(path):
        if path.exists():
            raise SystemExit(f"closure manifest already exists: {path}")
        data = {
            "schemaVersion": 1,
            "revision": 1,
            "projectId": args.project,
            "chapterNo": args.chapter,
            "requestId": args.request_id,
            "bodySha256": body_sha,
            "engineCommit": {
                "confirmed": False,
                "evidence": None,
                "bodySha256": None,
            },
            "operations": {
                operation: {"status": "pending", "evidence": None, "reason": None}
                for operation in operations
            },
            "createdAt": now(),
            "updatedAt": now(),
        }
        atomic_write_json(path, data, backup=False)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_confirm_commit(args):
    def apply(data):
        engine_sha = validate_hash(args.engine_body_sha256, "--engine-body-sha256")
        if engine_sha != data.get("bodySha256"):
            raise SystemExit("engine commit body sha256 does not match closure body sha256")
        data["engineCommit"] = {
            "confirmed": True,
            "evidence": args.evidence,
            "bodySha256": engine_sha,
            "confirmedAt": now(),
        }

    data = mutate(args, apply)
    print(json.dumps(data["engineCommit"], ensure_ascii=False, indent=2))


def cmd_mark(args):
    def apply(data):
        if args.operation not in data["operations"]:
            raise SystemExit(f"unknown closure operation: {args.operation}")
        if args.status == "completed" and not args.evidence:
            raise SystemExit("completed operation requires --evidence")
        if args.status == "skipped" and not args.reason:
            raise SystemExit("skipped operation requires --reason")
        data["operations"][args.operation] = {
            "status": args.status,
            "evidence": args.evidence,
            "reason": args.reason,
            "updatedAt": now(),
        }

    data = mutate(args, apply)
    print(json.dumps(data["operations"][args.operation], ensure_ascii=False, indent=2))


def cmd_show(args):
    print(json.dumps(load(Path(args.manifest)), ensure_ascii=False, indent=2))


def cmd_verify(args):
    manifest_path = Path(args.manifest)
    gate_path = Path(args.gate_receipt)
    data = load(manifest_path)
    try:
        gate_bytes = gate_path.read_bytes()
        gate = json.loads(gate_bytes.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid gate receipt: {exc}")

    reasons = []
    if gate.get("gatePass") is not True:
        reasons.append("PRECOMMIT_GATE_NOT_PASS")
    if gate.get("bodySha256") != data.get("bodySha256"):
        reasons.append("GATE_BODY_HASH_MISMATCH")
    commit = data.get("engineCommit", {})
    if commit.get("confirmed") is not True:
        reasons.append("ENGINE_COMMIT_NOT_CONFIRMED")
    if commit.get("bodySha256") != data.get("bodySha256"):
        reasons.append("ENGINE_BODY_HASH_MISMATCH")

    incomplete = []
    for operation, record in data["operations"].items():
        status = record.get("status")
        if status == "completed" and record.get("evidence"):
            continue
        if status == "skipped" and record.get("reason"):
            continue
        incomplete.append(operation)
    if incomplete:
        reasons.append("CLOSURE_OPERATIONS_INCOMPLETE:" + ",".join(sorted(incomplete)))

    receipt = {
        "closureGateVersion": "v1.0",
        "createdAt": now(),
        "projectId": data.get("projectId"),
        "chapterNo": data.get("chapterNo"),
        "requestId": data.get("requestId"),
        "bodySha256": data.get("bodySha256"),
        "manifestSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "gateReceiptSha256": hashlib.sha256(gate_bytes).hexdigest(),
        "closurePass": not reasons,
        "reasons": reasons,
    }
    if args.receipt:
        atomic_write_json(Path(args.receipt), receipt)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt["closurePass"] else 2


def add_mutation_args(parser):
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expect-revision", type=int, required=True)


def main():
    parser = argparse.ArgumentParser(description="Durable post-commit closure outbox")
    sub = parser.add_subparsers(dest="cmd", required=True)

    command = sub.add_parser("init")
    command.add_argument("--manifest", required=True)
    command.add_argument("--project", required=True)
    command.add_argument("--chapter", type=int, required=True)
    command.add_argument("--request-id", required=True)
    command.add_argument("--body-sha256", required=True)
    command.add_argument("--operation", action="append")
    command.set_defaults(func=cmd_init)

    command = sub.add_parser("confirm-commit")
    add_mutation_args(command)
    command.add_argument("--engine-body-sha256", required=True)
    command.add_argument("--evidence", required=True)
    command.set_defaults(func=cmd_confirm_commit)

    command = sub.add_parser("mark")
    add_mutation_args(command)
    command.add_argument("--operation", required=True)
    command.add_argument("--status", choices=["completed", "skipped"], required=True)
    command.add_argument("--evidence")
    command.add_argument("--reason")
    command.set_defaults(func=cmd_mark)

    command = sub.add_parser("show")
    command.add_argument("--manifest", required=True)
    command.set_defaults(func=cmd_show)

    command = sub.add_parser("verify")
    command.add_argument("--manifest", required=True)
    command.add_argument("--gate-receipt", required=True)
    command.add_argument("--receipt")
    command.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    result = args.func(args)
    if isinstance(result, int):
        return result
    return 0


if __name__ == "__main__":
    sys.exit(main())
