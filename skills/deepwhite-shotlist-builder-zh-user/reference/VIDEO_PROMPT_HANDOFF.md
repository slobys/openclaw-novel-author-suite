# Video Prompt Handoff v1.0

`video_prompts/video_prompt_manifest.json` 是 Shotlist Builder 到 `deepwhite-n8n-video-dispatcher V2` 的结构化交接文件。

## 顶层结构

```json
{
  "schema_version": "1.0",
  "project_id": "DEMO",
  "source_scene_asset_plan_id": "demo_s01e001_scene_assets_v001",
  "source_asset_job_id": "demo_assets_20260827_001",
  "clips": []
}
```

## clips[]

每个 clip 必须是一个 Scene-bound prompt group：

```json
{
  "clip_id": "VP008",
  "scene_id": "SC03",
  "location_id": "LOC-MARKET",
  "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
  "location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
  "background_reference_mode": "location_asset",
  "shot_ids": ["SH008", "SH009"],
  "duration": 8,
  "reference_asset_ids": [
    "AST-CH-LIN-MANCHANG",
    "AST-LOC-MARKET-SALT-STALL-DAY"
  ],
  "prompt": "不要出现BGM，不要出现字幕……"
}
```

必须字段：

```text
clip_id
scene_id
location_id
sub_location_id
location_asset_id
background_reference_mode
shot_ids
duration
reference_asset_ids
prompt
```

## duration

AUTO + Dispatcher V2：

```text
4 <= duration <= 15
```

且必须是整数。

1–3 秒只能作为 clip 内部 Shot，不能直接成为独立 AUTO 生成任务。

## reference_asset_ids

`location_asset` 模式：

```text
reference_asset_ids 必须包含 location_asset_id
```

同时加入本 clip 真正使用的人物/道具资产，避免无关参考图污染生成。

`scene_keyframe` 模式：

必须存在：

```text
scene_keyframe_asset_id
```

并且 keyframe 必须出现在 `reference_asset_ids`，metadata 必须追溯到同一 `location_asset_id`。

## Shot 完整覆盖

所有 `shots/shot_scene_bindings.json` 中属于最终范围的 shot 必须且只能出现在一个 clip 的 `shot_ids` 中。

不允许：

```text
漏 shot
同一个 shot 被两个 clip 重复消费
一个 clip 混入两个 scene
一个 clip 混入两个 location asset
```

## 给 Video Dispatcher 的责任边界

Shotlist Builder 决定：

```text
剧情如何拆镜头
每个镜头属于哪个 Scene
每个 Scene 使用哪个 location asset
多个 Shot 如何组成一个生成 clip
clip 的 prompt / duration / reference_asset_ids
```

Video Dispatcher 决定：

```text
video_job_id
provider defaults
filename
提交 n8n
轮询结果
```

Dispatcher 不应重新导演或重新挑场景图。
