# Scene Asset Binding Gate v1.0

本规则把 `deepwhite-scene-asset-planner` 的场景规划结果变成 Shotlist 的硬绑定。目标是保证剧情切场以后，分镜和视频不会继续引用上一场背景图。

## 1. 权威输入

AUTO 生产必须读取：

```text
handoffs/scene_asset_handoff.json
assets/actual_asset_manifest.json
script/scene_index.json
```

`scene_asset_handoff.json` 必须满足：

```text
gate_passed == true
scene_bindings 非空
```

每个固定空间 Scene 的权威关系是：

```text
scene_id
→ location_id
→ sub_location_id
→ primary_location_asset_id
```

下游不得从剧本文字、文件名或图片相似度重新猜地点。

AUTO coverage 的分母来自 `script/scene_index.json`。移动 Scene 额外读取 `allowed_location_asset_ids[]` 和有序 `route_anchors[]`。Shot/clip 可选择 allowed asset，但必须携带与该资产精确对应的 `route_anchor_id`。

## 2. 复用资产必须进入 actual_asset_manifest

Scene Asset Planner 会把本集场景分为：

```text
required_generation_asset_ids
verified_reuse_asset_ids
```

n8n 当前批次通常只返回新生成资产。因此 Shotlist Builder 在进入绑定 Gate 前必须把 `verified_reuse_asset_ids` 从系列 `asset_registry.json` / `series_assets/` 规范副本解析出来，合并进：

```text
assets/actual_asset_manifest.json
```

推荐条目：

```json
{
  "asset_id": "AST-LOC-LIN-HOME-LIVINGROOM-DAY",
  "category": "location",
  "status": "verified",
  "source_kind": "series_reuse",
  "filename": "AST-LOC-LIN-HOME-LIVINGROOM-DAY.png",
  "source_path": "/.../series_assets/AST-LOC-LIN-HOME-LIVINGROOM-DAY/...png"
}
```

当前 n8n 新生成资产使用：

```text
source_kind = n8n_generated
status = approved
```

任何需要引用的 location asset 如果不在 enriched manifest 中，Gate 必须失败。

## 3. Shot 继承规则

每个 Shot 必须写入：

```json
{
  "shot_id": "SH008",
  "scene_id": "SC03",
  "location_id": "LOC-MARKET",
  "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
  "location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY"
}
```

固定空间 Scene 的后四项必须与：

```text
scene_asset_handoff.scene_bindings[scene_id]
```

逐字段完全一致。

移动 Scene 的 `scene_id/location_id/sub_location_id` 逐字段一致，`location_asset_id` 必须在 allowed 集合内，并与 `route_anchor_id` 指向的资产一致。

禁止：

- 因为另一个场景图“更好看”而替换；
- 用同一大地点的另一子场景代替；
- 一个 Shot 同时绑定两个 primary location assets；
- 把多个地点硬切写进同一个 Shot/clip；
- 只在 prompt 里写地点文字，却不给机器字段。

## 4. Prompt Group / Clip 规则

一个视频提示词组可以包含多个 Shot，但必须满足：

```text
所有 shot.scene_id 相同
所有 shot.location_asset_id 相同
所有 shot.route_anchor_id 相同（有路线时）
```

因此：

```text
SC01 → SC02
```

一定切新 prompt group，即使两段合计少于 15 秒。

同一 Scene 内可以自由换景别、机位、人物位置，只要没有改变 Scene Asset Handoff 的地点身份。

## 5. Scene Keyframe 模式

默认：

```text
background_reference_mode = location_asset
```

如果后续存在审核通过的场次关键帧，可以改为：

```text
background_reference_mode = scene_keyframe
scene_keyframe_asset_id = AST-KF-SC03-001
```

关键帧 metadata 必须包含可追溯字段之一：

```text
source_location_asset_id
base_location_asset_id
location_asset_id
```

且其值必须等于当前 `location_asset_id`。

关键帧不得改变地点身份。

## 6. Gate 通过条件

必须全部满足：

```text
scene_asset_handoff.gate_passed == true
authoritative_scene_index_used == true
scene_coverage_ratio == 1.0
shot_binding_ratio == 1.0
prompt_binding_ratio == 1.0
missing_location_assets == []
duplicate_shot_assignments == []
unassigned_shots == []
```

失败时禁止生成最终 dispatcher-ready manifest。
