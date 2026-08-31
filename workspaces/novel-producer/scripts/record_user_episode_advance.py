#!/usr/bin/env python3
"""Close the previous episode's user-review UI state before advancing.

This command records the user's advance instruction even when the final-video
gate is missing.  It reports whether dispatching the next episode is allowed,
but never dispatches anything itself.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_manifest(queue_item: dict[str, Any], project_root: Path, project: dict[str, Any]) -> Path | None:
    candidates: list[Path] = []
    queue_value = queue_item.get("final_video_manifest")
    if queue_value:
        candidates.append(Path(queue_value))
    project_value = project.get("final_video_manifest")
    if project_value:
        value = Path(project_value)
        candidates.append(value if value.is_absolute() else project_root / value)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def final_video_gate(
    queue_item: dict[str, Any], project_root: Path, project: dict[str, Any]
) -> tuple[bool, list[str], dict[str, Any]]:
    errors: list[str] = []
    evidence: dict[str, Any] = {}
    manifest_path = resolve_manifest(queue_item, project_root, project)
    if manifest_path is None:
        return False, ["final_video_manifest.json is missing"], evidence

    manifest = load_json(manifest_path)
    evidence["manifest"] = str(manifest_path)
    if manifest.get("status") != "completed":
        errors.append("final video manifest status is not completed")
    if manifest.get("project_id") != queue_item.get("episode_project_id"):
        errors.append("final video manifest project_id mismatch")

    output_value = queue_item.get("final_video_path") or project.get("final_video_path")
    if output_value:
        output_path = Path(output_value)
    else:
        relative = manifest.get("relative_path")
        output_path = manifest_path.parent / relative if relative else Path()
    evidence["final_video"] = str(output_path)
    if not output_path.is_file():
        errors.append("final MP4 is missing")
        return False, errors, evidence

    actual_size = output_path.stat().st_size
    expected_size = manifest.get("file_size")
    if expected_size is not None and actual_size != int(expected_size):
        errors.append("final MP4 file size mismatch")
    actual_sha = sha256_file(output_path)
    expected_sha = manifest.get("sha256") or queue_item.get("final_video_sha256")
    if not expected_sha or actual_sha != expected_sha:
        errors.append("final MP4 SHA256 mismatch")

    width = int(manifest.get("width") or 0)
    height = int(manifest.get("height") or 0)
    if width <= 0 or height <= 0:
        errors.append("final MP4 dimensions are missing")
    expected_ratio = queue_item.get("aspect_ratio")
    if expected_ratio and width > 0 and height > 0:
        left, right = (int(part) for part in expected_ratio.split(":"))
        if abs(width / height - left / right) > 0.01:
            errors.append("final MP4 aspect ratio mismatch")
    if float(manifest.get("duration_seconds") or 0) <= 0:
        errors.append("final MP4 duration is missing")

    evidence.update(
        {
            "size_bytes": actual_size,
            "sha256": actual_sha,
            "width": width,
            "height": height,
            "duration_seconds": manifest.get("duration_seconds"),
        }
    )
    return not errors, errors, evidence


def select_completed_queue_item(series_root: Path, episode_number: int) -> Path | None:
    """Return the most recently series-committed revision for an episode."""
    done_dir = series_root / "queue" / "done"
    base_stem = f"episode_{episode_number:03d}"
    candidates: list[tuple[str, Path]] = []
    for path in done_dir.glob(f"{base_stem}*.json"):
        if path.stem != base_stem and not path.stem.startswith(f"{base_stem}_"):
            continue
        queue_item = load_json(path)
        if queue_item.get("episode_number") != episode_number:
            continue
        project_id = queue_item.get("episode_project_id")
        if not project_id:
            continue
        commit_path = done_dir / f".{project_id}.series_commit.json"
        if not commit_path.is_file():
            continue
        commit = load_json(commit_path)
        if commit.get("episode_project_id") != project_id or commit.get("episode_number") != episode_number:
            continue
        candidates.append((str(commit.get("committed_at") or ""), path))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--series-root", type=Path, required=True)
    parser.add_argument("--previous-episode", type=int, required=True)
    parser.add_argument("--next-episode", type=int, required=True)
    parser.add_argument("--user-utterance", required=True)
    parser.add_argument(
        "--drama-projects-root",
        type=Path,
        default=Path(
            os.environ.get(
                "DRAMA_PRODUCER_PROJECTS_ROOT",
                Path(os.environ.get("OPENCLAW_STATE_DIR", Path.home() / ".openclaw"))
                / "workspace-drama-producer"
                / "projects",
            )
        ).expanduser(),
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.next_episode <= args.previous_episode:
        raise SystemExit("next episode must be greater than previous episode")

    queue_item_path = select_completed_queue_item(args.series_root, args.previous_episode)
    if queue_item_path is None:
        result = {
            "recorded": False,
            "advance_allowed": False,
            "ui_close_required": True,
            "errors": [
                f"previous episode has no series-committed queue/done item: "
                f"episode_{args.previous_episode:03d}"
            ],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    queue_item = load_json(queue_item_path)
    project_id = queue_item.get("episode_project_id")
    if not project_id:
        raise SystemExit("queue/done item has no episode_project_id")
    project_root = args.drama_projects_root / project_id
    project_path = project_root / "project.json"
    if not project_path.is_file():
        raise SystemExit(f"downstream project is missing: {project_path}")
    project = load_json(project_path)

    gate_passed, gate_errors, evidence = final_video_gate(queue_item, project_root, project)
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    owner = project.get("progress_card_owner_session_key")
    result = {
        "recorded": bool(args.apply),
        "previous_episode": args.previous_episode,
        "next_episode": args.next_episode,
        "episode_project_id": project_id,
        "queue_item_path": str(queue_item_path),
        "progress_card_owner_session_key": owner,
        "ui_close_required": bool(owner),
        "final_video_gate": "pass" if gate_passed else "fail",
        "advance_allowed": gate_passed,
        "errors": gate_errors,
        "evidence": evidence,
    }

    if args.apply:
        project.update(
            {
                "user_review_accepted": True,
                "user_advanced_to_episode": args.next_episode,
                "user_advance_instruction": args.user_utterance,
                "user_advance_recorded_at": now,
                "progress_waiting_step": None,
                "progress_card_closed": True,
                "progress_closed_at": project.get("progress_closed_at") or now,
                "progress_state": "completed" if gate_passed else "review_closed_pending_final_video_gate",
            }
        )
        atomic_write_json(project_path, project)

        ledger_path = args.series_root / "review" / "user_episode_advances.json"
        ledger = load_json(ledger_path) if ledger_path.is_file() else {"schema_version": "1.0", "advances": []}
        entry = {
            "previous_episode": args.previous_episode,
            "next_episode": args.next_episode,
            "episode_project_id": project_id,
            "user_utterance": args.user_utterance,
            "recorded_at": now,
            "final_video_gate": result["final_video_gate"],
            "advance_allowed": gate_passed,
            "gate_errors": gate_errors,
            "evidence": evidence,
        }
        advances = ledger.setdefault("advances", [])
        key = (args.previous_episode, args.next_episode, args.user_utterance)
        if not any((item.get("previous_episode"), item.get("next_episode"), item.get("user_utterance")) == key for item in advances):
            advances.append(entry)
        atomic_write_json(ledger_path, ledger)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if gate_passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
