#!/usr/bin/env python3
"""Validate async video progress-card lifecycle fields in project.json."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def session_exists(
    owner: str,
    episode_token: str,
    episode_number: object,
    *,
    require_closed: bool = False,
) -> tuple[bool, str | None]:
    parts = owner.split(":", 2)
    if len(parts) != 3 or parts[0] != "agent" or not parts[1]:
        return False, "progress_card_owner_session_key must be a full agent session key"
    try:
        result = subprocess.run(
            ["openclaw", "sessions", "--agent", parts[1], "--json", "--limit", "all"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"cannot inspect durable session store: {exc}"
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit {result.returncode}"
        return False, f"cannot inspect durable session store: {detail}"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False, "durable session store returned invalid JSON"
    sessions = payload.get("sessions") if isinstance(payload, dict) else None
    if not isinstance(sessions, list):
        return False, "durable session store has no sessions array"
    match = next((item for item in sessions if isinstance(item, dict) and item.get("key") == owner), None)
    if match is None:
        return False, "progress_card_owner_session_key does not exist in the durable session store"
    if match.get("visibility") != "shared":
        return False, "progress-card owner session must be shared/visible"
    label = str(match.get("label") or "")
    episode_label = f"第{episode_number}集" if episode_number not in (None, "") else ""
    if episode_token not in owner and (not episode_label or episode_label not in label):
        return False, f"progress-card owner must identify the current episode ({episode_token})"
    store_path = payload.get("path") if isinstance(payload, dict) else None
    if not isinstance(store_path, str) or not store_path.strip():
        return False, "durable session store path is unavailable"
    try:
        connection = sqlite3.connect(f"file:{Path(store_path).resolve()}?mode=ro", uri=True)
        try:
            card = connection.execute(
                "SELECT steps_json FROM session_progress_cards WHERE session_key = ? LIMIT 1",
                (owner,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return False, f"cannot inspect progress-card ownership: {exc}"
    if card is None:
        return False, "progress-card owner session exists but does not own a progress card"
    if require_closed and card[0]:
        try:
            steps = json.loads(card[0])
        except json.JSONDecodeError:
            return False, "progress-card steps are invalid JSON"
        if isinstance(steps, list) and any(
            isinstance(step, dict) and step.get("status") in {"pending", "in_progress"}
            for step in steps
        ):
            return False, "final progress card still has pending or in_progress steps"
    return True, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("pre-dispatch", "final"))
    args = parser.parse_args()

    try:
        project = json.loads(args.project.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read project JSON: {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    owner = project.get("progress_card_owner_session_key")
    if not nonempty(owner):
        errors.append("progress_card_owner_session_key must be nonempty")

    if args.phase == "pre-dispatch":
        project_id = project.get("project_id")
        if not nonempty(project_id):
            errors.append("project_id must be nonempty")
        elif nonempty(owner):
            canonical_hook_session = f"agent:drama-producer:hook:drama:episode:{project_id}"
            callback_session = project.get("callback_session_key")
            if callback_session != canonical_hook_session:
                errors.append(
                    "callback_session_key must use the episode-specific "
                    f"hook session {canonical_hook_session}"
                )
            if owner in (canonical_hook_session, "agent:drama-producer:main"):
                errors.append(
                    "progress_card_owner_session_key must use a separate visible "
                    "episode production session, not the internal hook or shared main session"
                )
            episode_token = str(project_id).rsplit("_", 1)[-1]
            for field in ("progress_card_mirror_session_key", "callback_handoff_session_key"):
                value = project.get(field)
                if nonempty(value) and value != owner:
                    errors.append(f"{field} must match progress_card_owner_session_key")
            exists, owner_error = session_exists(owner, episode_token, project.get("episode_number"))
            if not exists and owner_error:
                errors.append(owner_error)
        if not nonempty(project.get("progress_waiting_step")):
            errors.append("progress_waiting_step must be nonempty")
        if project.get("progress_state") != "awaiting_callback":
            errors.append("progress_state must equal awaiting_callback")
    else:
        project_id = project.get("project_id")
        if nonempty(project_id) and nonempty(owner):
            episode_token = str(project_id).rsplit("_", 1)[-1]
            exists, owner_error = session_exists(
                owner,
                episode_token,
                project.get("episode_number"),
                require_closed=True,
            )
            if not exists and owner_error:
                errors.append(owner_error)
        if project.get("status") != "final_video_ready":
            errors.append("status must equal final_video_ready")
        if project.get("video_generation_status") != "completed":
            errors.append("video_generation_status must equal completed")
        if project.get("video_compose_status") != "completed":
            errors.append("video_compose_status must equal completed")
        if project.get("progress_state") != "completed":
            errors.append("progress_state must equal completed")
        if not nonempty(project.get("progress_closed_at")):
            errors.append("progress_closed_at must be nonempty")
        if project.get("progress_card_closed") is not True:
            errors.append("progress_card_closed must equal true")
        if project.get("progress_waiting_step") not in (None, ""):
            errors.append("progress_waiting_step must be cleared")

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: progress lifecycle {args.phase} gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
