# 从 V1 升级到 V2

## 不变

- Skill 名仍为 `deepwhite-n8n-video-dispatcher`。
- Webhook event 不变。
- 环境变量名称不变。
- 原 prompt / duration / reference_asset_ids / filename 继续使用。
- 原 Seedance 默认模型与参数不自动改变。

## 新增

每个 clip 必须增加：

```text
location_id
sub_location_id
location_asset_id
background_reference_mode
```

并在派发前读取：

```text
handoffs/scene_asset_handoff.json
assets/actual_asset_manifest.json
```

## 新 Gate

```text
gates/video_scene_binding_gate.json
```

Gate 失败不得调用 n8n。

## 上游最低要求

Video Prompt / Shotlist 必须至少能给 Dispatcher 提供唯一 `scene_id`。

Dispatcher 可以根据 `scene_id` 从 Scene Asset Handoff 填充权威 location 字段，但不得根据自然语言猜 scene_id。
