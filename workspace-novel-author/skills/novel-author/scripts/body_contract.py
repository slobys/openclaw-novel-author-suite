#!/usr/bin/env python3
"""Canonical chapter-body normalization shared by all local gates.

The Novel Engine hashes UTF-8 text after normalizing line endings and removing
leading/trailing whitespace. Keeping this contract in one module prevents a
trailing newline or Windows CRLF from changing the body identity locally.
"""

import hashlib
from pathlib import Path


def canonical_body_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def canonical_body_bytes(path: Path) -> bytes:
    return canonical_body_text(path).encode("utf-8")


def canonical_body_sha256(path: Path) -> str:
    return hashlib.sha256(canonical_body_bytes(path)).hexdigest()
