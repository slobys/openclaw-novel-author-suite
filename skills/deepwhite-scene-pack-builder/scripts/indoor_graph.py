#!/usr/bin/env python3
"""Validate indoor multi-room/multi-floor topology for DeepWhite scene manifests."""
from __future__ import annotations

from collections import deque
from typing import Any

INTERIOR_MODES = {"INTERIOR_SINGLE_ROOM", "INTERIOR_MULTI_ROOM", "INTERIOR_MULTI_LEVEL", "MIXED_EXT_INT"}
MULTI_MODES = {"INTERIOR_MULTI_ROOM", "INTERIOR_MULTI_LEVEL", "MIXED_EXT_INT"}
VERTICAL_KINDS = {"STAIR", "ELEVATOR", "RAMP", "LADDER"}
SAME_LEVEL_KINDS = {"DOOR", "OPENING", "SLIDING_DOOR", "ARCHWAY", "CORRIDOR", "THRESHOLD", "EXTERIOR_DOOR"}
ALLOWED_KINDS = VERTICAL_KINDS | SAME_LEVEL_KINDS


def _issue(msg: str, strict: bool, errors: list[str], warnings: list[str]) -> None:
    (errors if strict else warnings).append(msg)


def _vec(value: Any, n: int) -> bool:
    return isinstance(value, list) and len(value) == n and all(isinstance(x, (int, float)) for x in value)


def validate_indoor_graph(data: dict[str, Any], strict: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    mode = str(data.get("scene_mode") or data.get("complexity") or "")
    if mode not in INTERIOR_MODES:
        return errors, warnings

    levels = data.get("levels", [])
    zones = data.get("zones", [])
    connectors = data.get("connectors", [])
    routes = data.get("transition_routes", [])

    if not isinstance(levels, list) or not levels:
        errors.append("interior scene requires non-empty levels")
        levels = []
    if not isinstance(zones, list) or not zones:
        errors.append("interior scene requires non-empty zones")
        zones = []
    if mode in MULTI_MODES and (not isinstance(connectors, list) or not connectors):
        errors.append(f"{mode} requires non-empty connectors")
        connectors = []

    level_ids: set[str] = set()
    level_index: dict[str, int] = {}
    for i, level in enumerate(levels):
        if not isinstance(level, dict):
            errors.append(f"levels[{i}] must be an object")
            continue
        lid = str(level.get("id") or "")
        if not lid:
            errors.append(f"levels[{i}].id is required")
        elif lid in level_ids:
            errors.append(f"duplicate level id: {lid}")
        else:
            level_ids.add(lid)
            level_index[lid] = int(level.get("index", i + 1))
        if not isinstance(level.get("elevation_m"), (int, float)):
            errors.append(f"level {lid or i} requires numeric elevation_m")
        if not isinstance(level.get("clear_height_m"), (int, float)) or float(level.get("clear_height_m", 0)) <= 0:
            errors.append(f"level {lid or i} requires clear_height_m > 0")

    zone_ids: set[str] = set()
    zone_level: dict[str, str] = {}
    for i, zone in enumerate(zones):
        if not isinstance(zone, dict):
            errors.append(f"zones[{i}] must be an object")
            continue
        zid = str(zone.get("id") or "")
        lid = str(zone.get("level_id") or "")
        if not zid:
            errors.append(f"zones[{i}].id is required")
        elif zid in zone_ids:
            errors.append(f"duplicate zone id: {zid}")
        else:
            zone_ids.add(zid)
            zone_level[zid] = lid
        if lid not in level_ids:
            errors.append(f"zone {zid or i} references unknown level_id: {lid!r}")
        if not _vec(zone.get("origin_m"), 3):
            errors.append(f"zone {zid or i} origin_m must be [x,y,z]")
        if not _vec(zone.get("dimensions_m"), 3) or any(float(x) <= 0 for x in zone.get("dimensions_m", [0,0,0])):
            errors.append(f"zone {zid or i} dimensions_m must contain positive [w,d,h]")
        fps = [x for x in zone.get("fingerprints", []) if isinstance(x, str) and x.strip()]
        if len(fps) < 2:
            _issue(f"zone {zid or i} has fewer than 2 identity fingerprints", strict, errors, warnings)

    connector_ids: set[str] = set()
    adjacency: dict[str, set[str]] = {z: set() for z in zone_ids}
    edge_by_connector: dict[str, tuple[str, str]] = {}
    vertical_count = 0
    for i, con in enumerate(connectors):
        if not isinstance(con, dict):
            errors.append(f"connectors[{i}] must be an object")
            continue
        cid = str(con.get("id") or "")
        kind = str(con.get("kind") or "").upper()
        src = str(con.get("from_zone") or "")
        dst = str(con.get("to_zone") or "")
        if not cid:
            errors.append(f"connectors[{i}].id is required")
        elif cid in connector_ids:
            errors.append(f"duplicate connector id: {cid}")
        else:
            connector_ids.add(cid)
        if kind not in ALLOWED_KINDS:
            errors.append(f"connector {cid or i} has unsupported kind: {kind!r}")
        if src not in zone_ids or dst not in zone_ids or src == dst:
            errors.append(f"connector {cid or i} must link two distinct known zones: {src!r} -> {dst!r}")
            continue
        adjacency[src].add(dst)
        adjacency[dst].add(src)
        edge_by_connector[cid] = (src, dst)
        src_level, dst_level = zone_level.get(src), zone_level.get(dst)
        if kind in SAME_LEVEL_KINDS and src_level != dst_level:
            errors.append(f"same-level connector {cid} crosses levels: {src_level} -> {dst_level}")
        if kind in VERTICAL_KINDS:
            vertical_count += 1
            if src_level == dst_level:
                errors.append(f"vertical connector {cid} must connect different levels")
            vertical = con.get("vertical", {})
            if not isinstance(vertical, dict) or not vertical.get("configuration") or not vertical.get("ascent_direction"):
                _issue(f"vertical connector {cid} lacks configuration/ascent_direction", strict, errors, warnings)
        if not _vec(con.get("position_m"), 3):
            errors.append(f"connector {cid or i} position_m must be [x,y,z]")
        dims = con.get("dimensions_m")
        if not _vec(dims, 3) or any(float(x) <= 0 for x in (dims or [0,0,0])):
            errors.append(f"connector {cid or i} dimensions_m must contain positive [w,d,h]")
        fps = [x for x in con.get("fingerprints", []) if isinstance(x, str) and x.strip()]
        if len(fps) < 2:
            _issue(f"connector {cid or i} has fewer than 2 identity fingerprints", strict, errors, warnings)

    if mode == "INTERIOR_MULTI_LEVEL" and vertical_count == 0:
        errors.append("INTERIOR_MULTI_LEVEL requires at least one vertical connector")

    primary = str(data.get("building", {}).get("primary_zone") or (next(iter(zone_ids)) if zone_ids else ""))
    if primary and primary not in zone_ids:
        errors.append(f"building.primary_zone is unknown: {primary}")
    if primary in zone_ids:
        seen = {primary}
        q = deque([primary])
        while q:
            cur = q.popleft()
            for nxt in adjacency.get(cur, set()):
                if nxt not in seen:
                    seen.add(nxt); q.append(nxt)
        disconnected = sorted(zone_ids - seen)
        if disconnected:
            _issue(f"room graph has zones disconnected from {primary}: {disconnected}", strict, errors, warnings)

    if not isinstance(routes, list):
        errors.append("transition_routes must be an array")
        routes = []
    for i, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f"transition_routes[{i}] must be an object")
            continue
        rid = str(route.get("id") or i)
        zs = route.get("zone_sequence", [])
        cs = route.get("connector_sequence", [])
        if not isinstance(zs, list) or not isinstance(cs, list) or len(zs) != len(cs) + 1:
            errors.append(f"route {rid} requires len(zone_sequence)=len(connector_sequence)+1")
            continue
        for z in zs:
            if z not in zone_ids:
                errors.append(f"route {rid} references unknown zone {z}")
        for idx, cid in enumerate(cs):
            if cid not in edge_by_connector:
                errors.append(f"route {rid} references unknown connector {cid}")
                continue
            expected = {zs[idx], zs[idx+1]}
            if set(edge_by_connector[cid]) != expected:
                errors.append(f"route {rid} uses {cid} for wrong zone pair: expected {sorted(expected)}, actual {sorted(edge_by_connector[cid])}")

    # Required authority assets by mode
    asset_ids = {str(a.get("id")) for a in data.get("assets", []) if isinstance(a, dict)}
    asset_types = {str(a.get("type")) for a in data.get("assets", []) if isinstance(a, dict)}
    if not any(a.startswith("F") for a in asset_ids) and "floorplan" not in asset_types:
        _issue("interior scene should include at least one Fxx floor-plan authority", strict, errors, warnings)
    if mode in MULTI_MODES and "C01" not in asset_ids and "connectivity" not in asset_types:
        _issue(f"{mode} should include C01 room-connectivity authority", strict, errors, warnings)
    if mode == "INTERIOR_MULTI_LEVEL" and "S01" not in asset_ids and "section" not in asset_types:
        _issue("INTERIOR_MULTI_LEVEL should include S01 vertical section authority", strict, errors, warnings)

    # Portable spatial lock should name critical topology IDs.
    spatial = str(data.get("canonical_prompt_lock", {}).get("spatial_lock_text") or "")
    if spatial:
        missing_ids = [x for x in sorted(zone_ids | connector_ids) if x not in spatial]
        if missing_ids:
            _issue(f"SPATIAL LOCK omits indoor topology IDs: {missing_ids}", strict, errors, warnings)

    return errors, warnings
