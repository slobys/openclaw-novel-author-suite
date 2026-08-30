# n8n V2 兼容说明

V2 保持 Webhook event：

```text
openclaw_video_generation_requested
```

并保留旧版字段：

```text
clip_id
scene_id
prompt
duration
reference_asset_ids
filename
```

新增字段：

```text
location_id
sub_location_id
location_asset_id
background_reference_mode
scene_keyframe_asset_id
shot_ids
```

## 如果你的 n8n 工作流只是读取旧字段

通常无需修改，新增 JSON 字段会被忽略。

## 如果 n8n 使用严格 JSON Schema / Set 节点白名单

需要把新增字段加入允许列表，否则这些字段可能在工作流中被丢弃。

## 调用 Seedance/API 时

不要把 DeepWhite 的内部绑定字段原样传给视频供应商 API，除非供应商明确接受。

推荐：

```text
OpenClaw video_job
↓
n8n 保存完整 clip 元数据
↓
Resolve reference_asset_ids → 实际图片 URL/文件
↓
只把供应商支持字段传给视频 API
```

DeepWhite 内部字段主要用于：

- 保证正确场景；
- 日志追踪；
- 失败重试；
- 回调后 QA；
- 定位“哪个场景引用错图”。
