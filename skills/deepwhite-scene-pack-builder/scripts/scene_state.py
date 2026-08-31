#!/usr/bin/env python3
"""Manage and validate DeepWhite scene-pack manifests using only stdlib."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from indoor_graph import validate_indoor_graph

VALID_STATUS = {"draft", "pending", "blocked", "ready", "locked", "failed", "skipped"}
REVISION_KINDS = {"geometry", "style", "camera", "subject", "prompt"}
PORTABLE_SCHEMA_VERSIONS = {"2.3", "2.5", "3.2.0"}
SUPPORTED_SCHEMA_VERSIONS = {"2.0", "2.1", "2.2", *PORTABLE_SCHEMA_VERSIONS}
CANONICAL_KEYS_V22 = (
    "style_lock_text", "scene_dna_lock_text",
    "spatial_lock_text", "continuity_lock_text",
)
CANONICAL_KEYS_LEGACY = (
    "style_text", "frame_text", "scene_fingerprint_text",
    "topology_text", "light_text", "restriction_text",
)


def canonical_keys(canonical: dict[str, Any]) -> tuple[str, ...]:
    """Prefer the portable four-lock schema, while accepting v2.0/v2.1 manifests."""
    if any(key in canonical for key in CANONICAL_KEYS_V22):
        return CANONICAL_KEYS_V22
    return CANONICAL_KEYS_LEGACY
GEOMETRY_TYPES = {"layout", "floorplan", "zone-map", "blockout", "elevation", "section"}
CAMERA_TYPES = {"master", "proof", "view", "shot", "contact-sheet"}
SUBJECT_TYPES = {"subject", "route", "shot"}


def manifest_path(value: str | Path) -> Path:
    p = Path(value).expanduser().resolve()
    return p / "scene.json" if p.is_dir() else p


def load_manifest(value: str | Path) -> tuple[Path, dict[str, Any]]:
    p = manifest_path(value)
    if not p.exists():
        raise FileNotFoundError(f"manifest not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("manifest root must be a JSON object")
    return p, data


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def issue(msg: str, strict: bool, errors: list[str], warnings: list[str]) -> None:
    (errors if strict else warnings).append(msg)


def validate(data: dict[str, Any], strict: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required = (
        "schema_version", "scene_id", "scene_name", "revisions", "brief",
        "style_lock", "canonical_prompt_lock", "world_frame", "environment_lock",
        "landmarks", "cameras", "assets",
    )
    for key in required:
        if key not in data:
            errors.append(f"missing required key: {key}")

    if str(data.get("schema_version")) not in SUPPORTED_SCHEMA_VERSIONS:
        warnings.append(f"unexpected schema_version: {data.get('schema_version')!r}")

    scene_id = data.get("scene_id")
    if not isinstance(scene_id, str) or not scene_id.strip():
        errors.append("scene_id must be a non-empty string")

    brief = data.get("brief", {})
    if not isinstance(brief, dict):
        errors.append("brief must be an object")
    elif str(data.get("schema_version")) in PORTABLE_SCHEMA_VERSIONS:
        if brief.get("output_mode") != "PORTABLE_HARD_LOCK":
            errors.append("schema 2.3+ requires brief.output_mode=PORTABLE_HARD_LOCK")
        required_blocks = brief.get("required_prompt_blocks", [])
        expected_blocks = {
            "PORTABLE HARD LOCK BANNER", "STYLE LOCK", "SCENE DNA", "SPATIAL LOCK", "CONTINUITY LOCK"
        }
        if not isinstance(required_blocks, list) or not expected_blocks.issubset(set(required_blocks)):
            errors.append("schema 2.3+ required_prompt_blocks is incomplete")

    revisions = data.get("revisions", {})
    if isinstance(revisions, dict):
        for key in REVISION_KINDS:
            if not isinstance(revisions.get(key), int) or revisions.get(key, 0) < 1:
                errors.append(f"revisions.{key} must be an integer >= 1")
    else:
        errors.append("revisions must be an object")

    canonical = data.get("canonical_prompt_lock", {})
    if not isinstance(canonical, dict):
        errors.append("canonical_prompt_lock must be an object")
    else:
        keys = canonical_keys(canonical)
        for key in keys:
            if not isinstance(canonical.get(key), str) or not canonical.get(key, "").strip():
                issue(f"canonical_prompt_lock.{key} is empty", strict, errors, warnings)
        if keys == CANONICAL_KEYS_LEGACY and str(data.get("schema_version")) in {"2.2", *PORTABLE_SCHEMA_VERSIONS}:
            warnings.append("schema 2.2+ should use portable four-lock canonical fields")
        if str(data.get("schema_version")) in PORTABLE_SCHEMA_VERSIONS and canonical.get("compiler_schema") != "DW-PHL-1":
            errors.append("schema 2.3+ requires canonical_prompt_lock.compiler_schema=DW-PHL-1")
        if canonical.get("sealed") and not canonical.get("lock_id"):
            errors.append("sealed canonical_prompt_lock requires lock_id")
        elif canonical.get("sealed") and canonical.get("lock_id"):
            expected_lock_id = canonical_hash(data)
            if str(canonical.get("lock_id")) != expected_lock_id:
                errors.append(
                    f"sealed lock_id does not match canonical payload: stored={canonical.get('lock_id')}, expected={expected_lock_id}"
                )

    world = data.get("world_frame", {})
    if isinstance(world, dict):
        if world.get("z_axis") != "up":
            warnings.append("world_frame.z_axis should normally be 'up'")
        if not world.get("origin"):
            issue("world_frame.origin is empty", strict, errors, warnings)
    else:
        errors.append("world_frame must be an object")

    env = data.get("environment_lock", {})
    if isinstance(env, dict):
        sun = env.get("sun", {})
        if not isinstance(sun, dict) or not isinstance(sun.get("azimuth_world_deg"), (int, float)) or not isinstance(sun.get("elevation_deg"), (int, float)):
            errors.append("environment_lock.sun requires numeric azimuth_world_deg and elevation_deg")
        elif not 0 <= float(sun["elevation_deg"]) <= 90:
            errors.append("sun elevation_deg must be between 0 and 90")
    else:
        errors.append("environment_lock must be an object")

    landmarks = data.get("landmarks", [])
    landmark_ids: set[str] = set()
    if not isinstance(landmarks, list):
        errors.append("landmarks must be an array")
        landmarks = []
    if len(landmarks) < 3:
        issue("landmarks should contain at least 3 entries before sealing", strict, errors, warnings)
    elif len(landmarks) < 5:
        warnings.append("most scene packs benefit from 5-8 landmarks")
    for i, landmark in enumerate(landmarks):
        if not isinstance(landmark, dict):
            errors.append(f"landmarks[{i}] must be an object")
            continue
        lid = landmark.get("id")
        if not isinstance(lid, str) or not lid:
            errors.append(f"landmarks[{i}].id is required")
        elif lid in landmark_ids:
            errors.append(f"duplicate landmark id: {lid}")
        else:
            landmark_ids.add(lid)
        pos = landmark.get("position_m")
        if not isinstance(pos, list) or len(pos) != 3 or not all(isinstance(v, (int, float)) for v in pos):
            errors.append(f"landmark {lid or i} position_m must be [x,y,z] numbers")
        dims = landmark.get("dimensions_m")
        if not isinstance(dims, list) or len(dims) != 3 or not all(isinstance(v, (int, float)) for v in dims):
            errors.append(f"landmark {lid or i} dimensions_m must be [w,d,h] numbers")
        fps = landmark.get("fingerprints", [])
        nonempty = [x for x in fps if isinstance(x, str) and x.strip()] if isinstance(fps, list) else []
        if len(nonempty) < 2:
            issue(f"landmark {lid or i} has fewer than 2 identity fingerprints", strict, errors, warnings)

    cameras = data.get("cameras", [])
    camera_ids: set[str] = set()
    if not isinstance(cameras, list):
        errors.append("cameras must be an array")
        cameras = []
    for i, camera in enumerate(cameras):
        if not isinstance(camera, dict):
            errors.append(f"cameras[{i}] must be an object")
            continue
        cid = camera.get("id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"cameras[{i}].id is required")
        elif cid in camera_ids:
            errors.append(f"duplicate camera id: {cid}")
        else:
            camera_ids.add(cid)
        visible = camera.get("visible_landmarks", [])
        if isinstance(visible, list):
            unknown = [x for x in visible if x not in landmark_ids]
            if unknown:
                errors.append(f"camera {cid or i} references unknown landmarks: {unknown}")
        else:
            errors.append(f"camera {cid or i}.visible_landmarks must be an array")

    view_cameras = [c for c in cameras if isinstance(c, dict) and str(c.get("id", "")).startswith("V")]
    for previous, current in zip(view_cameras, view_cameras[1:]):
        shared = set(previous.get("visible_landmarks", [])) & set(current.get("visible_landmarks", []))
        if len(shared) < 2:
            warnings.append(f"{previous.get('id')} -> {current.get('id')} shares fewer than 2 landmarks: {sorted(shared)}")

    assets = data.get("assets", [])
    asset_ids: set[str] = set()
    if not isinstance(assets, list) or not assets:
        errors.append("assets must be a non-empty array")
        assets = []
    for i, asset in enumerate(assets):
        if not isinstance(asset, dict):
            errors.append(f"assets[{i}] must be an object")
            continue
        aid = asset.get("id")
        if not isinstance(aid, str) or not aid:
            errors.append(f"assets[{i}].id is required")
        elif aid in asset_ids:
            errors.append(f"duplicate asset id: {aid}")
        else:
            asset_ids.add(aid)
        if asset.get("status") not in VALID_STATUS:
            errors.append(f"asset {aid or i} has invalid status: {asset.get('status')!r}")

    for asset in assets:
        if not isinstance(asset, dict):
            continue
        aid = asset.get("id")
        for dep in asset.get("depends_on", []):
            if dep not in asset_ids:
                errors.append(f"asset {aid} depends on unknown asset {dep}")
        for ref in asset.get("references", []):
            if ref not in asset_ids and ref not in landmark_ids:
                warnings.append(f"asset {aid} references unknown item {ref}")

    current = data.get("current_asset")
    if current and current not in asset_ids:
        errors.append(f"current_asset not found in assets: {current}")

    indoor_errors, indoor_warnings = validate_indoor_graph(data, strict=strict)
    errors.extend(indoor_errors)
    warnings.extend(indoor_warnings)
    return errors, warnings


def canonical_hash(data: dict[str, Any]) -> str:
    canonical = data.get("canonical_prompt_lock", {})
    keys = canonical_keys(canonical)
    payload = {key: canonical.get(key, "") for key in keys}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def refresh_readiness(data: dict[str, Any]) -> None:
    assets = data.get("assets", [])
    status_by_id = {a.get("id"): a.get("status") for a in assets if isinstance(a, dict)}
    for asset in assets:
        if not isinstance(asset, dict) or asset.get("status") in {"locked", "failed", "skipped"}:
            continue
        deps = asset.get("depends_on", [])
        asset["status"] = "ready" if deps and all(status_by_id.get(dep) == "locked" for dep in deps) else ("pending" if not deps else "blocked")
    ready = [a for a in assets if isinstance(a, dict) and a.get("status") in {"pending", "ready"}]
    data["current_asset"] = ready[0].get("id") if ready else None


def cmd_init(args: argparse.Namespace) -> int:
    script_root = Path(__file__).resolve().parent.parent
    template = script_root / "assets" / "scene-manifest.template.json"
    if not template.exists():
        print(f"ERROR: template not found: {template}", file=sys.stderr)
        return 2
    scene_dir = Path(args.root).expanduser().resolve() / args.scene_id
    manifest = scene_dir / "scene.json"
    if manifest.exists() and not args.force:
        print(f"ERROR: manifest already exists: {manifest}; use --force to replace", file=sys.stderr)
        return 2
    scene_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(template.read_text(encoding="utf-8"))
    template_scene_id = str(data.get("scene_id") or "SC001")

    def replace_scene_id(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace(template_scene_id, args.scene_id)
        if isinstance(value, list):
            return [replace_scene_id(item) for item in value]
        if isinstance(value, dict):
            return {key: replace_scene_id(item) for key, item in value.items()}
        return value

    data = replace_scene_id(data)
    data["scene_id"] = args.scene_id
    data["scene_name"] = args.name
    atomic_write(manifest, data)
    (scene_dir / "prompts").mkdir(exist_ok=True)
    audit = scene_dir / "audit-log.md"
    if not audit.exists() or args.force:
        audit.write_text(f"# Audit log — {args.scene_id}\n", encoding="utf-8")
    print(manifest)
    return 0


def print_validation(errors: list[str], warnings: list[str]) -> None:
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"Validation: {len(errors)} error(s), {len(warnings)} warning(s)")


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        _, data = load_manifest(args.manifest)
        errors, warnings = validate(data, strict=args.strict)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_validation(errors, warnings)
    return 1 if errors else 0


def cmd_seal(args: argparse.Namespace) -> int:
    try:
        path, data = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    errors, warnings = validate(data, strict=True)
    print_validation(errors, warnings)
    if errors:
        return 1
    canonical = data.setdefault("canonical_prompt_lock", {})
    canonical["lock_id"] = canonical_hash(data)
    canonical["sealed"] = True
    data["status"] = "active"
    atomic_write(path, data)
    print(json.dumps({"sealed": True, "lock_id": canonical["lock_id"]}, ensure_ascii=False))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        _, data = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    refresh_readiness(data)
    result = {
        "scene_id": data.get("scene_id"),
        "scene_name": data.get("scene_name"),
        "status": data.get("status"),
        "revisions": data.get("revisions"),
        "lock_id": data.get("canonical_prompt_lock", {}).get("lock_id"),
        "current_asset": data.get("current_asset"),
        "assets": [{"id": a.get("id"), "type": a.get("type"), "status": a.get("status"), "depends_on": a.get("depends_on", [])} for a in data.get("assets", []) if isinstance(a, dict)],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    try:
        path, data = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    refresh_readiness(data)
    atomic_write(path, data)
    current = data.get("current_asset")
    asset = next((a for a in data.get("assets", []) if isinstance(a, dict) and a.get("id") == current), None)
    if not asset:
        print(json.dumps({"current_asset": None, "message": "no ready asset"}, ensure_ascii=False))
        return 0
    print(json.dumps(asset, ensure_ascii=False, indent=2))
    return 0


def cmd_lock(args: argparse.Namespace) -> int:
    try:
        path, data = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    asset = next((a for a in data.get("assets", []) if isinstance(a, dict) and a.get("id") == args.asset_id), None)
    if asset is None:
        print(f"ERROR: unknown asset: {args.asset_id}", file=sys.stderr)
        return 2
    status_by_id = {a.get("id"): a.get("status") for a in data.get("assets", []) if isinstance(a, dict)}
    unmet = [dep for dep in asset.get("depends_on", []) if status_by_id.get(dep) != "locked"]
    if unmet and not args.force:
        print(f"ERROR: cannot lock {args.asset_id}; unmet dependencies: {unmet}", file=sys.stderr)
        return 2
    asset["status"] = "locked"
    record: dict[str, Any] = {"asset_id": args.asset_id}
    if args.file:
        record["file"] = args.file
    if args.note:
        record["note"] = args.note
    accepted = data.setdefault("accepted_assets", [])
    accepted[:] = [x for x in accepted if not (isinstance(x, dict) and x.get("asset_id") == args.asset_id)]
    accepted.append(record)
    refresh_readiness(data)
    atomic_write(path, data)
    print(json.dumps({"locked": args.asset_id, "next": data.get("current_asset")}, ensure_ascii=False))
    return 0


def cmd_retry(args: argparse.Namespace) -> int:
    try:
        path, data = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    asset = next((a for a in data.get("assets", []) if isinstance(a, dict) and a.get("id") == args.asset_id), None)
    if asset is None:
        print(f"ERROR: unknown asset: {args.asset_id}", file=sys.stderr)
        return 2
    status_by_id = {a.get("id"): a.get("status") for a in data.get("assets", []) if isinstance(a, dict)}
    deps = asset.get("depends_on", [])
    asset["status"] = "ready" if all(status_by_id.get(dep) == "locked" for dep in deps) else ("pending" if not deps else "blocked")
    data["current_asset"] = args.asset_id if asset["status"] in {"ready", "pending"} else None
    atomic_write(path, data)
    print(json.dumps({"retry": args.asset_id, "status": asset["status"], "current": data.get("current_asset")}, ensure_ascii=False))
    return 0


def invalidate(data: dict[str, Any], kind: str) -> list[str]:
    assets = [a for a in data.get("assets", []) if isinstance(a, dict)]
    invalidated: list[str] = []
    for asset in assets:
        atype = str(asset.get("type", ""))
        should = False
        if kind == "geometry":
            should = True
        elif kind == "style":
            should = atype not in GEOMETRY_TYPES
        elif kind == "camera":
            should = atype in CAMERA_TYPES
        elif kind == "subject":
            should = atype in SUBJECT_TYPES
        elif kind == "prompt":
            should = False
        if should:
            asset["status"] = "pending" if not asset.get("depends_on") else "blocked"
            invalidated.append(str(asset.get("id")))
    if kind != "prompt":
        accepted = data.get("accepted_assets", [])
        data["accepted_assets"] = [x for x in accepted if isinstance(x, dict) and x.get("asset_id") not in set(invalidated)]
    return invalidated


def cmd_revise(args: argparse.Namespace) -> int:
    try:
        path, data = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    revisions = data.setdefault("revisions", {k: 1 for k in REVISION_KINDS})
    revisions[args.kind] = int(revisions.get(args.kind, 0)) + 1
    invalidated = invalidate(data, args.kind)
    if args.kind in {"geometry", "style", "camera", "subject"}:
        canonical = data.setdefault("canonical_prompt_lock", {})
        canonical["sealed"] = False
        canonical["lock_id"] = ""
        data["status"] = "draft"
    refresh_readiness(data)
    atomic_write(path, data)
    print(json.dumps({"revision": args.kind, "value": revisions[args.kind], "invalidated": invalidated, "next": data.get("current_asset")}, ensure_ascii=False))
    return 0


def cmd_fail(args: argparse.Namespace) -> int:
    try:
        path, data = load_manifest(args.manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    asset = next((a for a in data.get("assets", []) if isinstance(a, dict) and a.get("id") == args.asset_id), None)
    if asset is None:
        print(f"ERROR: unknown asset: {args.asset_id}", file=sys.stderr)
        return 2
    asset["status"] = "failed"
    data.setdefault("audit_history", []).append({"asset_id": args.asset_id, "result": "failed", "reason": args.reason})
    refresh_readiness(data)
    atomic_write(path, data)
    print(json.dumps({"failed": args.asset_id, "reason": args.reason, "next": data.get("current_asset")}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a draft scene manifest")
    p.add_argument("--root", default="scene-packs")
    p.add_argument("--scene-id", required=True)
    p.add_argument("--name", default="")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="validate a scene manifest; use --strict before production")
    p.add_argument("manifest")
    p.add_argument("--strict", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("seal", help="strictly validate and seal the canonical prompt lock")
    p.add_argument("manifest")
    p.set_defaults(func=cmd_seal)

    p = sub.add_parser("status", help="show scene and asset status")
    p.add_argument("manifest")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("next", help="show the next dependency-ready asset")
    p.add_argument("manifest")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("lock", help="accept and lock an asset")
    p.add_argument("manifest")
    p.add_argument("asset_id")
    p.add_argument("--file")
    p.add_argument("--note")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_lock)

    p = sub.add_parser("retry", help="make an asset ready for regeneration")
    p.add_argument("manifest")
    p.add_argument("asset_id")
    p.set_defaults(func=cmd_retry)

    p = sub.add_parser("revise", help="increment a revision and invalidate only affected assets")
    p.add_argument("manifest")
    p.add_argument("kind", choices=sorted(REVISION_KINDS))
    p.set_defaults(func=cmd_revise)

    p = sub.add_parser("fail", help="mark an asset failed and record the reason")
    p.add_argument("manifest")
    p.add_argument("asset_id")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_fail)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
