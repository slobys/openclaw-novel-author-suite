#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from runtime_io import LockTimeout, atomic_write_json, file_lock

STATES = [
    "pending",
    "preparing",
    "drafting",
    "length_gate",
    "auditing",
    "quality_gate",
    "precommit_gate",
    "committing",
    "closing",
    "integrity_gate",
    "committed",
]
NEXT_STATE = {current: following for current, following in zip(STATES, STATES[1:])}
EXCEPTION_STATES = {"failed", "blocked", "reconciling", "cancelling", "cancelled"}
TERMINAL_STATES = {"committed", "cancelled"}
SCHEMA_VERSION = 4


def now():
    return datetime.now(timezone.utc).isoformat()


def safe(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value)).strip("-") or "unknown"


def job_path(root: Path, job_id: str):
    return root / f"{safe(job_id)}.json"


def load_path(path: Path):
    if not path.exists():
        raise SystemExit(f"job not found: {path.stem}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"job json is corrupt: {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("chapters"), dict):
        raise SystemExit(f"invalid job schema: {path}")
    data.setdefault("schemaVersion", 1)
    data.setdefault("revision", 0)
    for chapter in data["chapters"].values():
        chapter.setdefault("failureCounts", {})
        chapter.setdefault("lastSafeState", chapter.get("state", "pending"))
        chapter.setdefault("taskRegistry", [])
    return data


def load(root: Path, job_id: str):
    path = job_path(root, job_id)
    return path, load_path(path)


def save(path: Path, data, expected_revision=None):
    current_revision = int(data.get("revision", 0))
    if expected_revision is not None and current_revision != expected_revision:
        raise SystemExit(
            f"revision conflict: expected {expected_revision}, actual {current_revision}; reload job before retry"
        )
    data["schemaVersion"] = SCHEMA_VERSION
    data["revision"] = current_revision + 1
    data["updatedAt"] = now()
    atomic_write_json(path, data)


def overall(job):
    states = [chapter["state"] for chapter in job["chapters"].values()]
    if any(state == "cancelling" for state in states):
        return "cancelling"
    if states and all(state in TERMINAL_STATES for state in states):
        return "cancelled" if any(state == "cancelled" for state in states) else "completed"
    if states and all(state == "committed" for state in states):
        return "completed"
    if any(state in {"failed", "blocked", "reconciling"} for state in states):
        return "needs_attention"
    return "running"


def current_chapter(job):
    for chapter_no in sorted(int(key) for key in job["chapters"]):
        if job["chapters"][str(chapter_no)]["state"] not in TERMINAL_STATES:
            return chapter_no
    return None


def chapter_record(data, chapter_no):
    key = str(chapter_no)
    if key not in data["chapters"]:
        raise SystemExit(f"chapter not in job: {chapter_no}")
    active = current_chapter(data)
    if active is not None and active != chapter_no:
        raise SystemExit(
            f"strict serial violation: chapter {active} must be committed before chapter {chapter_no}"
        )
    return data["chapters"][key]


def read_json_evidence(path_value, label):
    path = Path(path_value)
    if not path.is_file():
        raise SystemExit(f"{label} evidence file not found: {path}")
    raw = path.read_bytes()
    try:
        evidence = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid {label} evidence json: {exc}")
    if not isinstance(evidence, dict):
        raise SystemExit(f"{label} evidence must be a JSON object")
    return path, raw, evidence


def validate_transition_evidence(chapter, chapter_no, new_state, evidence_value):
    if not evidence_value or not evidence_value.strip():
        raise SystemExit("every state transition requires --evidence")

    record = {"state": new_state, "evidence": evidence_value, "at": now()}
    if new_state == "precommit_gate":
        path, raw, evidence = read_json_evidence(evidence_value, "quality gate")
        if evidence.get("qualityPass") is not True:
            raise SystemExit("cannot enter precommit_gate: qualityPass is not true")
        if evidence.get("chapterNo") is not None and evidence.get("chapterNo") != chapter_no:
            raise SystemExit("cannot enter precommit_gate: quality receipt chapter number mismatch")
        body_sha = evidence.get("bodySha256")
        if not isinstance(body_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", body_sha):
            raise SystemExit("cannot enter precommit_gate: invalid bodySha256 in quality receipt")
        chapter["qualityEvidence"] = {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bodySha256": body_sha.lower(),
        }
    elif new_state == "committing":
        path, raw, evidence = read_json_evidence(evidence_value, "precommit gate")
        if evidence.get("gatePass") is not True:
            raise SystemExit("cannot enter committing: gatePass is not true")
        body_sha = evidence.get("bodySha256")
        if not isinstance(body_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", body_sha):
            raise SystemExit("cannot enter committing: invalid bodySha256 in gate receipt")
        quality_sha = chapter.get("qualityEvidence", {}).get("bodySha256")
        if quality_sha and quality_sha != body_sha.lower():
            raise SystemExit("cannot enter committing: gate body hash differs from quality gate")
        chapter["gateEvidence"] = {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bodySha256": body_sha.lower(),
        }
    elif new_state == "closing":
        path, raw, evidence = read_json_evidence(evidence_value, "engine commit")
        expected_sha = chapter.get("gateEvidence", {}).get("bodySha256")
        if evidence.get("confirmed") is not True:
            raise SystemExit("cannot enter closing: engine commit is not confirmed")
        if evidence.get("chapterNo") != chapter_no:
            raise SystemExit("cannot enter closing: engine chapter number mismatch")
        if evidence.get("requestId") != chapter.get("requestId"):
            raise SystemExit("cannot enter closing: engine requestId mismatch")
        if evidence.get("bodySha256") != expected_sha:
            raise SystemExit("cannot enter closing: engine body hash mismatch")
        chapter["engineCommitEvidence"] = {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bodySha256": expected_sha,
        }
    elif new_state == "committed":
        path, raw, evidence = read_json_evidence(evidence_value, "closure gate")
        expected_sha = chapter.get("gateEvidence", {}).get("bodySha256")
        if evidence.get("closurePass") is not True:
            raise SystemExit("cannot enter committed: closurePass is not true")
        if evidence.get("chapterNo") != chapter_no:
            raise SystemExit("cannot enter committed: closure chapter number mismatch")
        if evidence.get("requestId") != chapter.get("requestId"):
            raise SystemExit("cannot enter committed: closure requestId mismatch")
        if evidence.get("bodySha256") != expected_sha:
            raise SystemExit("cannot enter committed: closure body hash mismatch")
        chapter["closureEvidence"] = {
            "path": str(path),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bodySha256": expected_sha,
        }
    return record


def require_revision(args, data):
    actual = int(data.get("revision", 0))
    if args.expect_revision != actual:
        raise SystemExit(
            f"revision conflict: expected {args.expect_revision}, actual {actual}; reload job before retry"
        )


def mutate(args, callback):
    root = Path(args.dir)
    path = job_path(root, args.job)
    with file_lock(path):
        data = load_path(path)
        require_revision(args, data)
        if data.get("status") in {"cancelling", "cancelled"}:
            raise SystemExit(f"job is {data.get('status')}; no stage transition, retry or new task is allowed")
        callback(data)
        data["status"] = overall(data)
        save(path, data, expected_revision=args.expect_revision)
        return data


def cmd_create(args):
    if args.end < args.start:
        raise SystemExit("--end must be >= --start")
    root = Path(args.dir)
    root.mkdir(parents=True, exist_ok=True)
    project_lock = root / f".project-{safe(args.project)}"
    with file_lock(project_lock):
        for existing in root.glob("*.json"):
            candidate = load_path(existing)
            if candidate.get("projectId") == args.project and candidate.get("status") not in {"completed", "cancelled"}:
                raise SystemExit(
                    f"active job already exists for project {args.project}: {candidate.get('jobId')}"
                )

        job_id = args.job_id or (
            f"job-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
            f"{safe(args.project)}-{args.start}-{args.end}"
        )
        path = job_path(root, job_id)
        if path.exists():
            raise SystemExit(f"job already exists: {job_id}")
        chapters = {
            str(number): {
                "state": "pending",
                "lastSafeState": "pending",
                "attempts": 0,
                "requestId": f"{job_id}-ch{number}",
                "lastError": None,
                "failureCounts": {},
                "taskRegistry": [],
                "updatedAt": now(),
            }
            for number in range(args.start, args.end + 1)
        }
        data = {
            "schemaVersion": SCHEMA_VERSION,
            "revision": 0,
            "jobId": job_id,
            "projectId": args.project,
            "startChapter": args.start,
            "endChapter": args.end,
            "status": "running",
            "createdAt": now(),
            "updatedAt": now(),
            "chapters": chapters,
            "note": "Local orchestration only; novel-engine remains authoritative.",
        }
        save(path, data, expected_revision=0)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_set(args):
    def apply(data):
        chapter = chapter_record(data, args.chapter)
        old = chapter["state"]
        new = args.state
        if new not in STATES:
            raise SystemExit(f"invalid state: {new}")
        if old == "committed":
            raise SystemExit("committed is terminal; no further state mutation is allowed")
        if old in EXCEPTION_STATES:
            raise SystemExit(f"use resume/unblock/reconcile for state {old}")
        expected = NEXT_STATE.get(old)
        if new != expected:
            raise SystemExit(f"invalid transition {old}->{new}; expected {expected}")
        transition = validate_transition_evidence(chapter, args.chapter, new, args.evidence)
        if old == "pending" and new == "preparing":
            chapter["attempts"] = int(chapter.get("attempts", 0)) + 1
        chapter["state"] = new
        chapter["lastSafeState"] = new
        chapter["lastError"] = None
        chapter["updatedAt"] = now()
        chapter.setdefault("transitionHistory", []).append(transition)

    data = mutate(args, apply)
    print(json.dumps(data["chapters"][str(args.chapter)], ensure_ascii=False, indent=2))


def cmd_fail(args):
    def apply(data):
        chapter = chapter_record(data, args.chapter)
        if chapter["state"] == "committed":
            raise SystemExit("cannot fail a committed chapter")
        if chapter["state"] in EXCEPTION_STATES:
            raise SystemExit(f"cannot fail from {chapter['state']}; use its dedicated recovery command")
        code = safe(args.error_code).upper()
        counts = chapter.setdefault("failureCounts", {})
        counts[code] = int(counts.get(code, 0)) + 1
        chapter["lastSafeState"] = (
            "precommit_gate" if chapter["state"] == "committing" else chapter.get("state", "pending")
        )
        chapter["state"] = "blocked" if counts[code] >= args.max_same_error else "failed"
        chapter["lastError"] = {
            "code": code,
            "message": args.error,
            "count": counts[code],
            "retryAllowed": counts[code] < args.max_same_error,
            "at": now(),
        }
        chapter["updatedAt"] = now()

    data = mutate(args, apply)
    print(json.dumps(data["chapters"][str(args.chapter)], ensure_ascii=False, indent=2))


def cmd_resume(args):
    def apply(data):
        chapter = chapter_record(data, args.chapter)
        if chapter["state"] != "failed":
            raise SystemExit("resume only applies to failed state")
        target = chapter.get("lastSafeState") or "pending"
        if target == "committing":
            target = "precommit_gate"
        chapter["state"] = target
        chapter["lastError"] = None
        chapter["updatedAt"] = now()

    data = mutate(args, apply)
    print(json.dumps(data["chapters"][str(args.chapter)], ensure_ascii=False, indent=2))


def cmd_unblock(args):
    def apply(data):
        chapter = chapter_record(data, args.chapter)
        if chapter["state"] != "blocked":
            raise SystemExit("unblock only applies to blocked state")
        target = chapter.get("lastSafeState") or "pending"
        if target == "committing":
            target = "precommit_gate"
        chapter["state"] = target
        chapter["lastError"] = None
        chapter["operatorResolution"] = {"reason": args.reason, "at": now()}
        chapter["updatedAt"] = now()

    data = mutate(args, apply)
    print(json.dumps(data["chapters"][str(args.chapter)], ensure_ascii=False, indent=2))


def cmd_uncertain(args):
    def apply(data):
        chapter = chapter_record(data, args.chapter)
        if chapter["state"] != "committing":
            raise SystemExit("uncertain delivery can only be recorded from committing")
        chapter["state"] = "reconciling"
        chapter["lastSafeState"] = "precommit_gate"
        chapter["lastError"] = {
            "code": "COMMIT_DELIVERY_UNCERTAIN",
            "message": args.error,
            "retryAllowed": False,
            "at": now(),
        }
        chapter["updatedAt"] = now()

    data = mutate(args, apply)
    print(json.dumps(data["chapters"][str(args.chapter)], ensure_ascii=False, indent=2))


def cmd_reconcile(args):
    def apply(data):
        chapter = chapter_record(data, args.chapter)
        if chapter["state"] != "reconciling":
            raise SystemExit("reconcile only applies to reconciling state")
        if args.engine_status == "committed":
            transition = validate_transition_evidence(chapter, args.chapter, "closing", args.evidence)
            chapter["state"] = "closing"
            chapter.setdefault("transitionHistory", []).append(transition)
        elif args.engine_status == "absent":
            chapter["state"] = "precommit_gate"
        else:
            chapter["lastError"] = {
                "code": "COMMIT_STATUS_STILL_UNKNOWN",
                "message": args.evidence,
                "retryAllowed": False,
                "at": now(),
            }
            chapter["updatedAt"] = now()
            return
        chapter["lastSafeState"] = chapter["state"]
        chapter["lastError"] = None
        chapter["reconciliation"] = {
            "engineStatus": args.engine_status,
            "evidence": args.evidence,
            "at": now(),
        }
        chapter["updatedAt"] = now()

    data = mutate(args, apply)
    print(json.dumps(data["chapters"][str(args.chapter)], ensure_ascii=False, indent=2))


def cmd_register_task(args):
    if not any([args.task_id, args.run_id, args.session_key]):
        raise SystemExit("register-task requires --task-id, --run-id or --session-key")

    def apply(data):
        chapter = chapter_record(data, args.chapter)
        registry = chapter.setdefault("taskRegistry", [])
        match = next(
            (
                item for item in registry
                if (args.task_id and item.get("taskId") == args.task_id)
                or (args.run_id and item.get("runId") == args.run_id)
                or (args.session_key and item.get("sessionKey") == args.session_key)
            ),
            None,
        )
        if match is None:
            match = {"role": args.role, "registeredAt": now()}
            registry.append(match)
        match.update({
            "role": args.role,
            "taskId": args.task_id or match.get("taskId"),
            "runId": args.run_id or match.get("runId"),
            "sessionKey": args.session_key or match.get("sessionKey"),
            "status": "accepted",
            "updatedAt": now(),
        })
        chapter["updatedAt"] = now()

    data = mutate(args, apply)
    print(json.dumps(data["chapters"][str(args.chapter)]["taskRegistry"], ensure_ascii=False, indent=2))


def cancellation_targets(data):
    task_ids = []
    run_ids = []
    session_keys = []
    for chapter in data.get("chapters", {}).values():
        for item in chapter.get("taskRegistry", []):
            if item.get("taskId"):
                task_ids.append(item["taskId"])
            if item.get("runId"):
                run_ids.append(item["runId"])
            if item.get("sessionKey"):
                session_keys.append(item["sessionKey"])
    return {
        "taskIds": sorted(set(task_ids)),
        "runIds": sorted(set(run_ids)),
        "sessionKeys": sorted(set(session_keys)),
    }


def cmd_cancel(args):
    root = Path(args.dir)
    path = job_path(root, args.job)
    with file_lock(path):
        data = load_path(path)
        if data.get("status") == "completed":
            raise SystemExit("completed job cannot be cancelled")
        if data.get("status") not in {"cancelling", "cancelled"}:
            requested_at = now()
            for chapter in data["chapters"].values():
                if chapter.get("state") not in TERMINAL_STATES:
                    chapter["stateBeforeCancel"] = chapter.get("state")
                    chapter["state"] = "cancelling"
                    chapter["lastError"] = None
                    chapter["updatedAt"] = requested_at
            data["status"] = "cancelling"
            data["cancellation"] = {
                "reason": args.reason,
                "requestedAt": requested_at,
                "completedAt": None,
                "retryAllowed": False,
            }
            save(path, data, expected_revision=int(data.get("revision", 0)))
        output = {
            "jobId": data.get("jobId"),
            "projectId": data.get("projectId"),
            "status": data.get("status"),
            "revision": data.get("revision"),
            "cancellation": data.get("cancellation"),
            "cancelTargets": cancellation_targets(data),
            "nextAction": "Call subagents action=cancel for every active taskId, then run confirm-cancel. Do not spawn, retry or resume.",
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_confirm_cancel(args):
    root = Path(args.dir)
    path = job_path(root, args.job)
    with file_lock(path):
        data = load_path(path)
        if data.get("status") == "completed":
            raise SystemExit("completed job cannot be cancelled")
        if data.get("status") == "cancelled":
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return
        if data.get("status") != "cancelling":
            raise SystemExit("confirm-cancel requires a prior cancel request")
        completed_at = now()
        for chapter in data["chapters"].values():
            if chapter.get("state") != "committed":
                chapter["state"] = "cancelled"
                chapter["updatedAt"] = completed_at
        data["status"] = "cancelled"
        cancellation = data.setdefault("cancellation", {})
        cancellation["completedAt"] = completed_at
        cancellation["evidence"] = args.evidence
        cancellation["retryAllowed"] = False
        save(path, data, expected_revision=int(data.get("revision", 0)))
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_guard(args):
    _, data = load(Path(args.dir), args.job)
    chapter = data.get("chapters", {}).get(str(args.chapter)) if args.chapter else None
    blocked = data.get("status") in {"cancelling", "cancelled"} or (
        chapter is not None and chapter.get("state") in {"cancelling", "cancelled"}
    )
    result = {
        "jobId": data.get("jobId"),
        "projectId": data.get("projectId"),
        "chapter": args.chapter,
        "jobStatus": data.get("status"),
        "chapterState": chapter.get("state") if chapter else None,
        "allowed": not blocked,
        "rule": "A cancelled or cancelling job may not spawn, retry, resume, audit, commit or process completion events.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 3 if blocked else 0


def cmd_show(args):
    _, data = load(Path(args.dir), args.job)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_active(args):
    root = Path(args.dir)
    output = []
    if root.exists():
        for path in sorted(root.glob("*.json")):
            try:
                data = load_path(path)
            except SystemExit:
                continue
            if args.project and data.get("projectId") != args.project:
                continue
            if data.get("status") not in {"completed", "cancelled"}:
                output.append(
                    {
                        "jobId": data.get("jobId"),
                        "projectId": data.get("projectId"),
                        "status": data.get("status"),
                        "revision": data.get("revision"),
                        "startChapter": data.get("startChapter"),
                        "endChapter": data.get("endChapter"),
                        "updatedAt": data.get("updatedAt"),
                    }
                )
    print(json.dumps(output, ensure_ascii=False, indent=2))


def add_mutation_args(parser):
    parser.add_argument("--job", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--expect-revision", type=int, required=True)


def main():
    parser = argparse.ArgumentParser(description="Strict local orchestration state for novel jobs")
    parser.add_argument("--dir", default=".novel-runtime/jobs")
    sub = parser.add_subparsers(dest="cmd", required=True)

    command = sub.add_parser("create")
    command.add_argument("--project", required=True)
    command.add_argument("--start", type=int, required=True)
    command.add_argument("--end", type=int, required=True)
    command.add_argument("--job-id")
    command.set_defaults(func=cmd_create)

    command = sub.add_parser("set")
    add_mutation_args(command)
    command.add_argument("--state", required=True)
    command.add_argument("--evidence", required=True)
    command.set_defaults(func=cmd_set)

    command = sub.add_parser("fail")
    add_mutation_args(command)
    command.add_argument("--error-code", required=True)
    command.add_argument("--error", required=True)
    command.add_argument("--max-same-error", type=int, default=2)
    command.set_defaults(func=cmd_fail)

    command = sub.add_parser("resume")
    add_mutation_args(command)
    command.set_defaults(func=cmd_resume)

    command = sub.add_parser("unblock")
    add_mutation_args(command)
    command.add_argument("--reason", required=True)
    command.set_defaults(func=cmd_unblock)

    command = sub.add_parser("uncertain")
    add_mutation_args(command)
    command.add_argument("--error", required=True)
    command.set_defaults(func=cmd_uncertain)

    command = sub.add_parser("reconcile")
    add_mutation_args(command)
    command.add_argument("--engine-status", choices=["committed", "absent", "unknown"], required=True)
    command.add_argument("--evidence", required=True)
    command.set_defaults(func=cmd_reconcile)

    command = sub.add_parser("register-task")
    add_mutation_args(command)
    command.add_argument("--role", choices=["writer", "continuity-auditor", "reader-editor"], required=True)
    command.add_argument("--task-id")
    command.add_argument("--run-id")
    command.add_argument("--session-key")
    command.set_defaults(func=cmd_register_task)

    command = sub.add_parser("cancel")
    command.add_argument("--job", required=True)
    command.add_argument("--reason", default="user_requested_stop")
    command.set_defaults(func=cmd_cancel)

    command = sub.add_parser("confirm-cancel")
    command.add_argument("--job", required=True)
    command.add_argument("--evidence", required=True)
    command.set_defaults(func=cmd_confirm_cancel)

    command = sub.add_parser("guard")
    command.add_argument("--job", required=True)
    command.add_argument("--chapter", type=int)
    command.set_defaults(func=cmd_guard)

    command = sub.add_parser("show")
    command.add_argument("--job", required=True)
    command.set_defaults(func=cmd_show)

    command = sub.add_parser("active")
    command.add_argument("--project")
    command.set_defaults(func=cmd_active)

    args = parser.parse_args()
    try:
        result = args.func(args)
        if isinstance(result, int):
            return result
    except LockTimeout as exc:
        raise SystemExit(str(exc))


if __name__ == "__main__":
    sys.exit(main())
