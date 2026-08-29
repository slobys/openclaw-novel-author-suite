#!/usr/bin/env python3
"""Dependency-free primitives for Agent-side orchestration files."""

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class LockTimeout(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def file_lock(target: Path, timeout_seconds=10.0, stale_seconds=120.0):
    """Acquire an atomic sibling lock file and release it on exit."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(target.name + ".lock")
    deadline = time.monotonic() + timeout_seconds
    lock_token = uuid.uuid4().hex
    payload = json.dumps({"pid": os.getpid(), "token": lock_token, "createdAt": utc_now()})

    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > stale_seconds:
                    lock_path.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise LockTimeout(f"lock timeout: {lock_path}")
            time.sleep(0.05)

    try:
        yield
    finally:
        try:
            owner = json.loads(lock_path.read_text(encoding="utf-8"))
            if owner.get("token") == lock_token:
                lock_path.unlink()
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass


def atomic_write_text(path: Path, text: str, backup=True):
    """Atomically replace UTF-8 text and retain one last valid JSON backup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if backup and path.exists():
        previous = path.read_text(encoding="utf-8")
        try:
            json.loads(previous)
        except json.JSONDecodeError:
            previous = None
        if previous is not None:
            _replace_text(path.with_name(path.name + ".bak"), previous)

    _replace_text(path, text)


def atomic_write_json(path: Path, data, backup=True):
    atomic_write_text(
        Path(path),
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        backup=backup,
    )


def _replace_text(path: Path, text: str):
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
