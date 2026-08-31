#!/usr/bin/env python3
"""Validate Portable Hard-Lock scene prompts and compare them with a sealed manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

BANNER = "【PORTABLE HARD LOCK｜独立可用｜禁止删减】"
REQUIRED_HEADINGS = (
    "【STYLE LOCK｜固定原文】",
    "【SCENE DNA｜固定原文】",
    "【SPATIAL LOCK｜固定原文】",
    "【CONTINUITY LOCK｜固定原文】",
)
REQUIRED_DYNAMIC = (
    "【CURRENT ASSET】",
    "【WORLD RELATIONSHIPS FOR THIS VIEW】",
    "【CAMERA SETUP】",
    "【VISIBLE / OCCLUDED LANDMARKS】",
    "【REFERENCE INPUTS｜需实际上传】",
    "【MOVING SUBJECT / TRANSITION】",
    "【TARGETED RESTRICTIONS】",
)
ALL_SECTION_RE = re.compile(r"(?m)^【[^\n】]+】\s*$")
LOCK_ID_RE = re.compile(r"(?m)^LOCK_ID:\s*([^\s]+)\s*$")


def read_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).expanduser().read_text(encoding="utf-8")


def extract_section(text: str, heading: str) -> str | None:
    start = text.find(heading)
    if start < 0:
        return None
    content_start = start + len(heading)
    match = ALL_SECTION_RE.search(text, content_start)
    end = match.start() if match else len(text)
    return text[content_start:end].strip()


def canonical_from_manifest(data: dict[str, Any]) -> dict[str, str]:
    canonical = data.get("canonical_prompt_lock", {})
    if not isinstance(canonical, dict):
        return {}
    return {
        REQUIRED_HEADINGS[0]: str(canonical.get("style_lock_text", "")).strip(),
        REQUIRED_HEADINGS[1]: str(canonical.get("scene_dna_lock_text", "")).strip(),
        REQUIRED_HEADINGS[2]: str(canonical.get("spatial_lock_text", "")).strip(),
        REQUIRED_HEADINGS[3]: str(canonical.get("continuity_lock_text", "")).strip(),
    }


def canonical_hash(expected: dict[str, str]) -> str:
    payload = {
        "style_lock_text": expected.get(REQUIRED_HEADINGS[0], ""),
        "scene_dna_lock_text": expected.get(REQUIRED_HEADINGS[1], ""),
        "spatial_lock_text": expected.get(REQUIRED_HEADINGS[2], ""),
        "continuity_lock_text": expected.get(REQUIRED_HEADINGS[3], ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def lint(
    text: str,
    manifest: dict[str, Any] | None = None,
    strict_hardlock: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    stripped = text.lstrip("\ufeff\n\r\t ")

    if not stripped.startswith(BANNER):
        msg = f"prompt must begin with hard-lock banner: {BANNER}"
        (errors if strict_hardlock else warnings).append(msg)

    banner_count = text.count(BANNER)
    if banner_count != 1:
        errors.append(f"hard-lock banner must appear exactly once; found {banner_count}")

    lock_match = LOCK_ID_RE.search(text)
    if not lock_match:
        errors.append("missing LOCK_ID line")
    elif not lock_match.group(1).strip():
        errors.append("empty LOCK_ID")

    positions: list[int] = []
    for heading in REQUIRED_HEADINGS:
        count = text.count(heading)
        if count != 1:
            errors.append(f"required lock heading must appear exactly once: {heading}; found {count}")
            continue
        pos = text.find(heading)
        positions.append(pos)
        body = extract_section(text, heading)
        if not body:
            errors.append(f"empty lock block: {heading}")
        elif len(body) < 30:
            warnings.append(f"lock block is unusually short: {heading}")

    if len(positions) == len(REQUIRED_HEADINGS) and positions != sorted(positions):
        errors.append("four lock blocks are not in the required order")

    for heading in REQUIRED_DYNAMIC:
        count = text.count(heading)
        if count != 1:
            errors.append(f"required dynamic section must appear exactly once: {heading}; found {count}")
        elif not extract_section(text, heading):
            errors.append(f"empty dynamic section: {heading}")

    unresolved_patterns = (
        r"(?:请)?参考上一张",
        r"(?:请)?以上一张[^\n]{0,80}作为参考",
        r"沿用上(?:一张|图|文)",
        r"继承上(?:一张|图|文)",
        r"同上",
        r"如上所述",
        r"按前文",
    )
    unresolved = [pattern for pattern in unresolved_patterns if re.search(pattern, text)]
    reference_body = extract_section(text, "【REFERENCE INPUTS｜需实际上传】") or ""
    attachment_words = ("实际上传", "必须上传", "建议上传", "attach", "attached", "若未")
    if unresolved and not any(word in reference_body for word in attachment_words):
        errors.append("contains prior-context shorthand without an explicit actual-upload instruction")
    elif unresolved:
        warnings.append("contains previous-context wording; make sure the named image is actually attached")

    symbolic_refs = re.findall(r"\b(?:AST|CV|TR|SUB|STA|ELV|RM|PT|LV|SH|V|M|L|F|E|C|S|B|P|K|R)-?\d{1,3}[A-C]?\b", text, re.I)
    if symbolic_refs and not any(word in reference_body for word in attachment_words):
        errors.append("asset IDs are mentioned but REFERENCE INPUTS does not require actual image upload")

    if re.search(r"(?m)^连续性锁定[:：]", text) and REQUIRED_HEADINGS[3] not in text:
        errors.append("loose '连续性锁定' prose cannot replace the exact CONTINUITY LOCK heading")

    current_body = extract_section(text, "【CURRENT ASSET】") or ""
    moving_body = extract_section(text, "【MOVING SUBJECT / TRANSITION】") or ""
    if re.search(r"(?:TR\d|过渡阶段|门槛|楼梯平台)", current_body + moving_body, re.I):
        required_terms = ("来源", "目标", "连接器")
        combined = (extract_section(text, "【WORLD RELATIONSHIPS FOR THIS VIEW】") or "") + moving_body
        missing_terms = [term for term in required_terms if term not in combined]
        if missing_terms:
            errors.append(f"transition prompt lacks room/connector continuity terms: {missing_terms}")

    if manifest is not None:
        expected = canonical_from_manifest(manifest)
        canonical = manifest.get("canonical_prompt_lock", {})
        if not isinstance(canonical, dict):
            errors.append("manifest canonical_prompt_lock is invalid")
        else:
            if strict_hardlock and not canonical.get("sealed"):
                errors.append("strict hard-lock validation requires a sealed manifest")
            for heading, expected_text in expected.items():
                actual = extract_section(text, heading)
                if not expected_text:
                    errors.append(f"manifest lock is empty: {heading}")
                elif actual != expected_text:
                    errors.append(f"lock text differs from manifest: {heading}")
            stored_lock_id = str(canonical.get("lock_id") or "").strip()
            expected_lock_id = canonical_hash(expected)
            actual_lock_id = lock_match.group(1).strip() if lock_match else ""
            if stored_lock_id and stored_lock_id != expected_lock_id:
                errors.append(
                    f"manifest lock_id does not match canonical payload: stored={stored_lock_id}, expected={expected_lock_id}"
                )
            if stored_lock_id and actual_lock_id != stored_lock_id:
                errors.append(
                    f"prompt LOCK_ID differs from manifest: prompt={actual_lock_id!r}, manifest={stored_lock_id!r}"
                )

    if len(text.strip()) < 700:
        warnings.append("prompt is short for a portable hard-lock multi-view scene prompt")
    if "same physical" not in text.lower() and "同一个真实" not in text:
        warnings.append("prompt lacks an explicit same-physical-location statement")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="UTF-8 prompt text file, or - for stdin")
    parser.add_argument("--manifest", help="optional scene.json for exact lock comparison")
    parser.add_argument("--strict-hardlock", action="store_true", help="enforce banner-first and sealed-manifest rules")
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    args = parser.parse_args()

    try:
        text = read_text(args.prompt)
        manifest = None
        if args.manifest:
            manifest = json.loads(Path(args.manifest).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    errors, warnings = lint(text, manifest, strict_hardlock=args.strict_hardlock)
    if args.json:
        print(json.dumps({"errors": errors, "warnings": warnings, "ok": not errors}, ensure_ascii=False, indent=2))
    else:
        for item in warnings:
            print(f"WARNING: {item}")
        for item in errors:
            print(f"ERROR: {item}")
        print(f"Prompt lint: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
