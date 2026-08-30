# DeepWhite Video Job Schema 1.1（V2 Dispatcher）

本版本在原 `1.0` 的基础上增加确定性的 Scene Asset Binding 字段。Webhook event 保持不变，便于现有 n8n 工作流迁移。

---

## 1. Job 必填结构

```json
{
  "schema_version": "1.1",
  "event": "openclaw_video_generation_requested",
  "project_id": "DEMO",
  "video_job_id": "demo_video_20260827_001",
  "source_asset_job_id": "demo_assets_20260827_001",
  "source_scene_asset_plan_id": "demo_s01e001_scene_assets_v001",
  "defaults": {
    "model": "doubao-seedance-2-0-mini-260615",
    "resolution": "720p",
    "ratio": "16:9",
    "generate_audio": true,
    "watermark": false,
    "max_generation_attempts": 2,
    "provider_max_wait_minutes": 180
  },
  "clips": []
}
```

`source_scene_asset_plan_id` 推荐必填，用于追踪本批视频来自哪一版 Scene Asset Plan。

---

## 2. clips[] 必填字段

```json
{
  "clip_id": "VP008",
  "scene_id": "SC03",
  "location_id": "LOC-MARKET",
  "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
  "location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
  "background_reference_mode": "location_asset",
  "prompt": "不要出现BGM，不要出现字幕……",
  "duration": 8,
  "reference_asset_ids": [
    "AST-CH-LIN-MANCHANG",
    "AST-LOC-MARKET-SALT-STALL-DAY"
  ],
  "filename": "DEMO_VP008_v01.mp4"
}
```

必填：

```text
clip_id
scene_id
location_id
sub_location_id
location_asset_id
background_reference_mode
prompt
duration
reference_asset_ids
filename
```

可选：

```text
shot_ids
scene_keyframe_asset_id
model
resolution
ratio
generate_audio
watermark
max_generation_attempts
provider_max_wait_minutes
metadata
```

---

## 3. background_reference_mode

只允许：

```text
location_asset
scene_keyframe
```

### location_asset

`reference_asset_ids` 必须直接包含 `location_asset_id`。

### scene_keyframe

必须存在：

```text
scene_keyframe_asset_id
```

且：

- 关键帧存在于 actual asset manifest；
- 关键帧出现在 `reference_asset_ids`；
- 关键帧 metadata 能追溯到当前 `location_asset_id`。

推荐关键帧 metadata：

```json
{
  "source_location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
  "scene_id": "SC03",
  "review_status": "approved"
}
```

也兼容血缘字段：

```text
base_location_asset_id
location_asset_id
```

若状态明确为 `rejected`、`failed`、`blocked`，禁止使用。

---

## 4. 场景绑定规则

对于每条 clip：

```text
handoff = scene_asset_handoff.scene_bindings[clip.scene_id]
```

必须：

```text
clip.location_id == handoff.location_id
clip.sub_location_id == handoff.sub_location_id
clip.location_asset_id == handoff.primary_location_asset_id
```

不得用自然语言地点近似匹配。

---

## 5. 通用验证规则

- `project_id`、`video_job_id`、`source_asset_job_id`、`clip_id` 只使用字母、数字、下划线、短横线。
- `clips` 数量：1–100。
- `clip_id` 不可重复。
- `filename` 不可重复。
- `duration` 为 4–15 的整数。
- `prompt` 非空、最多 2200 字符。
- `prompt` 必须以 `不要出现BGM，不要出现字幕` 开头。
- `reference_asset_ids` 为 1–9 个唯一资产 ID。
- 所有 `reference_asset_ids` 必须存在于 `actual_asset_manifest.json`。
- `location_asset_id` 必须存在于 actual asset manifest，即使 scene_keyframe 模式不直接把它发给视频模型。
- 同一 `project_id + video_job_id` 不可对应不同内容。

---

## 6. 示例：直接场景资产模式

```json
{
  "clip_id": "VP001",
  "scene_id": "SC01",
  "location_id": "LOC-LIN-HOME",
  "sub_location_id": "SUBLOC-LIN-HOME-LIVINGROOM",
  "location_asset_id": "AST-LOC-LIN-HOME-LIVINGROOM-DAY",
  "background_reference_mode": "location_asset",
  "prompt": "不要出现BGM，不要出现字幕。林满仓坐在木桌旁……",
  "duration": 8,
  "reference_asset_ids": [
    "AST-CH-LIN-MANCHANG",
    "AST-LOC-LIN-HOME-LIVINGROOM-DAY"
  ],
  "filename": "DEMO_VP001_v01.mp4"
}
```

---

## 7. 示例：场次关键帧模式

```json
{
  "clip_id": "VP009",
  "scene_id": "SC03",
  "location_id": "LOC-MARKET",
  "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
  "location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
  "background_reference_mode": "scene_keyframe",
  "scene_keyframe_asset_id": "AST-KF-SC03-001",
  "prompt": "不要出现BGM，不要出现字幕。林满仓在盐摊前停住，神色一沉……",
  "duration": 8,
  "reference_asset_ids": [
    "AST-KF-SC03-001"
  ],
  "filename": "DEMO_VP009_v01.mp4"
}
```
