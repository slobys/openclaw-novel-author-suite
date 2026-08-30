#!/usr/bin/env python3
"""Fail when a public release contains private runtime data or machine-specific paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".py", ".mjs", ".js", ".sh", ".ini", ".example"}
SKIP_PARTS = {".git", ".openclaw", "__pycache__"}
FORBIDDEN_NAMES = {"MEMORY.md", "DREAMS.md", "openclaw.json", "sessions.json"}
FORBIDDEN_DIRS = {"memory", "projects", "output", ".learnings", ".novel-runtime", "sessions"}
FORBIDDEN_TEXT = (
    "/home/" + "naiyou",
    "/vol1/" + "1000",
    "192." + "168.",
    "comedy_" + "game_01",
    "my_novel_" + "2026",
)
SECRET_RE = re.compile(r"(?i)(api[_-]?key|webhook[_-]?secret|authorization)\s*[:=]\s*['\"]?[A-Za-z0-9_./+-]{20,}")


def main() -> int:
    errors: list[str] = []
    skill_dirs = sorted(path for path in (ROOT / "skills").iterdir() if path.is_dir())
    if len(skill_dirs) != 9:
        errors.append(f"expected 9 public skills, found {len(skill_dirs)}")
    for skill in skill_dirs:
        if not (skill / "SKILL.md").is_file():
            errors.append(f"missing SKILL.md: {skill.relative_to(ROOT)}")

    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.is_dir() and path.name in FORBIDDEN_DIRS:
            errors.append(f"private runtime directory included: {relative}")
            continue
        if not path.is_file():
            continue
        if path.name in FORBIDDEN_NAMES or path.suffix in {".pyc", ".pyo"} or ".bak" in path.name:
            errors.append(f"private or generated file included: {relative}")
            continue
        if path == Path(__file__).resolve():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README.md", "VERSION", ".env.example"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"unexpected binary file: {relative}")
            continue
        for token in FORBIDDEN_TEXT:
            if token in text:
                errors.append(f"machine-specific/private token in {relative}: {token}")
        if path.name != ".env.example" and SECRET_RE.search(text):
            errors.append(f"possible committed secret in {relative}")

    if errors:
        print("public release check failed:")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    print("public release check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
