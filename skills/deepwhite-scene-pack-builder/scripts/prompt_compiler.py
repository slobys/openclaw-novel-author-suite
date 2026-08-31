#!/usr/bin/env python3
"""Compile a deterministic Portable Hard-Lock prompt from a scene manifest and asset spec."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BANNER = "【PORTABLE HARD LOCK｜独立可用｜禁止删减】"
LOCK_HEADINGS = (
    ("style_lock_text", "【STYLE LOCK｜固定原文】"),
    ("scene_dna_lock_text", "【SCENE DNA｜固定原文】"),
    ("spatial_lock_text", "【SPATIAL LOCK｜固定原文】"),
    ("continuity_lock_text", "【CONTINUITY LOCK｜固定原文】"),
)


def load_json(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def list_text(value: Any, empty: str = "无") -> str:
    if isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
        return "；".join(values) if values else empty
    text = str(value or "").strip()
    return text or empty


def canonical_payload(manifest: dict[str, Any]) -> dict[str, str]:
    canonical = manifest.get("canonical_prompt_lock")
    if not isinstance(canonical, dict):
        raise ValueError("manifest.canonical_prompt_lock must be an object")
    payload: dict[str, str] = {}
    missing: list[str] = []
    for key, _heading in LOCK_HEADINGS:
        text = str(canonical.get(key, "")).strip()
        if not text:
            missing.append(key)
        payload[key] = text
    if missing:
        raise ValueError("empty canonical lock field(s): " + ", ".join(missing))
    return payload


def payload_hash(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def compile_zone_context(value: Any) -> str:
    if not isinstance(value, dict) or not any(str(v).strip() for v in value.values() if not isinstance(v, list)) and not value.get("legal_topology_path"):
        return ""
    path = value.get("legal_topology_path", [])
    path_text = " → ".join(str(x) for x in path) if isinstance(path, list) and path else "未指定"
    return "\n".join([
        f"当前楼层：{str(value.get('current_level') or '未指定').strip()}",
        f"当前区域：{str(value.get('current_zone') or '未指定').strip()}",
        f"来源区域：{str(value.get('source_zone') or '不适用').strip()}",
        f"目标区域：{str(value.get('destination_zone') or '不适用').strip()}",
        f"活动连接器：{str(value.get('active_connector') or '不适用').strip()}",
        f"合法拓扑路径：{path_text}",
        f"摄影机位于连接器哪一侧：{str(value.get('camera_side_of_connector') or '不适用').strip()}",
        f"参考覆盖等级：{str(value.get('reference_coverage') or '未评估').strip()}",
    ])


def compile_transition(value: Any) -> str:
    if not isinstance(value, dict) or not value.get("enabled"):
        return ""
    return "\n".join([
        f"过渡ID：{str(value.get('transition_id') or '未指定').strip()}",
        f"过渡阶段：{str(value.get('phase') or '未指定').strip()}",
        f"上一镜头结束状态：{str(value.get('previous_end_state') or '未指定').strip()}",
        f"当前镜头开始状态：{str(value.get('current_start_state') or '未指定').strip()}",
        f"当前镜头结束状态：{str(value.get('current_end_state') or '未指定').strip()}",
        f"门洞/楼梯身份锁：{str(value.get('portal_or_stair_identity') or '未指定').strip()}",
        f"必须持续可辨认：{list_text(value.get('must_remain_visible'))}",
    ])


def compile_references(refs: Any) -> str:
    if not isinstance(refs, list) or not refs:
        return (
            "本资产没有可用的前序参考图。仅依据上方四个固定锁块生成；"
            "不得假装已经看过任何未实际上传的图片。"
        )
    lines: list[str] = []
    for index, ref in enumerate(refs, start=1):
        if not isinstance(ref, dict):
            raise ValueError(f"references[{index - 1}] must be an object")
        rid = str(ref.get("id") or f"R{index}").strip()
        aid = str(ref.get("asset_id") or "未指定参考资产").strip()
        requirement = str(ref.get("upload_requirement") or "must").strip().lower()
        label = "必须实际上传" if requirement in {"must", "required", "必须"} else "建议实际上传"
        role = str(ref.get("role") or "未指定控制职责").strip()
        do_not_copy = str(ref.get("do_not_copy") or "不得覆盖当前资产的机位与任务").strip()
        lines.append(f"{rid}：{label}的 {aid} 图片——只控制{role}；{do_not_copy}。")
    lines.append("若上述任一图片没有在本次请求中实际上传，不得声称已经看到它；改为依据四锁生成。")
    return "\n".join(lines)


def compile_prompt(manifest: dict[str, Any], asset: dict[str, Any], allow_unsealed: bool = False) -> str:
    payload = canonical_payload(manifest)
    canonical = manifest.get("canonical_prompt_lock", {})
    sealed = bool(canonical.get("sealed"))
    if not sealed and not allow_unsealed:
        raise ValueError("canonical prompt lock is not sealed; run scene_state.py seal or use --allow-unsealed")

    computed_lock_id = payload_hash(payload)
    stored_lock_id = str(canonical.get("lock_id") or "").strip()
    if sealed and stored_lock_id and stored_lock_id != computed_lock_id:
        raise ValueError(
            f"stored lock_id {stored_lock_id} does not match canonical payload hash {computed_lock_id}; reseal manifest"
        )
    lock_id = stored_lock_id or (computed_lock_id if sealed else "UNSAVED")

    asset_id = str(asset.get("asset_id") or "").strip()
    asset_name = str(asset.get("asset_name") or "").strip()
    task = str(asset.get("task") or "").strip()
    if not asset_id or not asset_name or not task:
        raise ValueError("asset_id, asset_name and task are required")

    purpose = str(asset.get("purpose") or "continuous scene asset / AI drama storyboard").strip()
    world_relationships = str(asset.get("world_relationships") or "严格遵循 SPATIAL LOCK；本资产不新增或移动固定地标。").strip()
    zone_context = compile_zone_context(asset.get("zone_context"))
    if zone_context:
        world_relationships += "\n\n当前楼层、房间与连接器上下文：\n" + zone_context

    camera = asset.get("camera", {})
    if not isinstance(camera, dict):
        raise ValueError("camera must be an object")
    visibility = asset.get("visibility", {})
    if not isinstance(visibility, dict):
        raise ValueError("visibility must be an object")

    restrictions = list_text(asset.get("targeted_restrictions"), "不得改变四锁中的任何固定事实")
    moving = str(asset.get("moving_subject_transition") or "无移动主体；保持环境空镜。").strip()
    transition = compile_transition(asset.get("transition_continuity"))
    if transition:
        moving += "\n\n跨房间/跨楼层连续性：\n" + transition

    sections: list[str] = [BANNER, f"LOCK_ID: {lock_id}"]
    for key, heading in LOCK_HEADINGS:
        sections.extend([heading, payload[key]])

    sections.extend([
        "【CURRENT ASSET】",
        f"资产ID：{asset_id}\n资产名称：{asset_name}\n任务：{task}\n预期用途：{purpose}",
        "【WORLD RELATIONSHIPS FOR THIS VIEW】",
        world_relationships,
        "【CAMERA SETUP】",
        "\n".join([
            f"摄影机位置：{str(camera.get('position') or '未指定').strip()}",
            f"看向目标 / 朝向：{str(camera.get('direction') or '未指定').strip()}",
            f"摄影机高度：{str(camera.get('height') or '未指定').strip()}",
            f"景别 / 视场角：{str(camera.get('shot_fov') or '未指定').strip()}",
            f"焦段 / 透视：{str(camera.get('lens_perspective') or '自然透视，禁止鱼眼畸变').strip()}",
            f"动作轴侧：{str(camera.get('action_axis_side') or '不适用').strip()}",
        ]),
        "【VISIBLE / OCCLUDED LANDMARKS】",
        "\n".join([
            f"必须可见：{list_text(visibility.get('must_visible'))}",
            f"允许自然遮挡：{list_text(visibility.get('may_occlude'))}",
            f"与上一张已通过视角共享：{list_text(visibility.get('shared_with_previous'))}",
        ]),
        "【REFERENCE INPUTS｜需实际上传】",
        compile_references(asset.get("references")),
        "【MOVING SUBJECT / TRANSITION】",
        moving,
        "【TARGETED RESTRICTIONS】",
        restrictions,
        (
            "This is the exact same physical location viewed from the specified camera. "
            "Preserve the frozen four-lock payload, world geometry, scale and identity fingerprints. "
            "Allow physically correct perspective, parallax and occlusion. "
            "Do not redesign the scene or copy another view's screen composition."
        ),
    ])
    return "\n\n".join(sections).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="scene.json path")
    parser.add_argument("--asset", required=True, help="asset prompt spec JSON path")
    parser.add_argument("--output", help="write prompt to this path; otherwise stdout")
    parser.add_argument("--allow-unsealed", action="store_true", help="allow draft manifest and use LOCK_ID UNSAVED")
    args = parser.parse_args()

    try:
        manifest = load_json(args.manifest)
        asset = load_json(args.asset)
        prompt = compile_prompt(manifest, asset, allow_unsealed=args.allow_unsealed)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.output:
        path = Path(args.output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt, encoding="utf-8")
        print(path)
    else:
        sys.stdout.write(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
