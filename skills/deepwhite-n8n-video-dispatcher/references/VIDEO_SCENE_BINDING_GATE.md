# Video Scene Binding Gate

## 目标

阻止这类错误进入 n8n：

```text
SC05 剧情已经到了集市盐摊
↓
视频任务仍引用上一场的林家堂屋图
```

该 Gate 是确定性验证，不靠模型主观判断。

---

## 权威输入

```text
dispatch/video_jobs/{video_job_id}.json
handoffs/scene_asset_handoff.json
assets/actual_asset_manifest.json
```

---

## 核心检查

### 1. Scene existence

`clip.scene_id` 必须存在于：

```text
scene_asset_handoff.scene_bindings
```

### 2. Location identity

必须严格相等：

```text
clip.location_id
== handoff.location_id
```

### 3. Sub-location identity

必须严格相等：

```text
clip.sub_location_id
== handoff.sub_location_id
```

### 4. Primary background identity

必须严格相等：

```text
clip.location_asset_id
== handoff.primary_location_asset_id
```

### 5. Asset existence

`location_asset_id` 与所有 `reference_asset_ids` 必须存在于 actual asset manifest。

### 6. Background reference proof

`location_asset` 模式：

```text
location_asset_id in reference_asset_ids
```

`scene_keyframe` 模式：

```text
scene_keyframe_asset_id in reference_asset_ids
```

并且关键帧资产的 metadata 能追溯到当前 `location_asset_id`。

---

## Gate 输出

```json
{
  "schema_version": "1.0",
  "passed": true,
  "project_id": "DEMO",
  "video_job_id": "demo_video_001",
  "clip_count": 5,
  "valid_clip_count": 5,
  "binding_coverage_ratio": 1.0,
  "checks": {
    "unknown_scene_count": 0,
    "location_id_mismatch_count": 0,
    "sub_location_id_mismatch_count": 0,
    "location_asset_mismatch_count": 0,
    "missing_location_asset_count": 0,
    "missing_reference_asset_count": 0,
    "background_reference_error_count": 0,
    "scene_keyframe_lineage_error_count": 0,
    "basic_schema_error_count": 0
  },
  "clip_results": [],
  "errors": [],
  "warnings": []
}
```

只有 `passed=true` 才能提交 n8n。
