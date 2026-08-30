---
name: deepwhite-n8n-video-dispatcher
description: 将 DeepWhite 已通过视频提示词审核与场景资产绑定审核的 Seedance 视频任务整理成严格 video_prompt_manifest.json 与 video_job.json，并通过受保护 Webhook 派发给 n8n。V2 强制把每个 clip 的 scene_id 与 Scene Asset Planner 的 location_id、sub_location_id、location_asset_id 一一绑定，并在提交前运行确定性的 Video Scene Binding Gate。仅在 AUTO_PRODUCTION_MODE、视频提示词 Gate 通过、scene_asset_handoff Gate 通过、实际资产完整且用户未要求“只生成提示词/不要生成视频”时使用。不得在本技能中重写剧情或偷偷替换场景。
---

# DeepWhite n8n 视频派发 V2

本技能是视频生成前最后一道机器 Gate。

它只做三件事：

1. 将已定稿视频提示词封装成严格 JSON；
2. 强制验证 `clip → scene → location asset` 的绑定关系；
3. Gate 通过后把任务派发给 n8n。

不要在本技能中重写剧情、重新分镜、修改资产外观、替换场景、发明缺失资产或调用视频模型。

---

## V2 核心不变量

每个 `clips[]` 必须同时具有：

```text
scene_id
location_id
sub_location_id
location_asset_id
```

并且必须满足：

```text
clip.scene_id
→ handoffs/scene_asset_handoff.json
→ expected location_id
→ expected sub_location_id
→ expected primary_location_asset_id
```

即：

```text
clip.location_id == expected.location_id
clip.sub_location_id == expected.sub_location_id
clip.location_asset_id == expected.primary_location_asset_id
```

任何一项不一致：`FAIL`，不得调用 n8n。

---

## 前置条件

同时满足才继续：

- `project.json` 状态为 `video_prompts_ready` 或项目定义的等价已完成状态。
- 原有 `review/video_prompt_gate_review.json` 已允许进入视频生产。
- `gates/scene_asset_coverage_gate.json` 存在且 `passed=true`。
- `handoffs/scene_asset_handoff.json` 存在且 `gate_passed=true`。
- `assets/actual_asset_manifest.json` 存在；所有最终引用资产拥有唯一 `asset_id`。
- 最终视频提示词存在，并且每条提示词能够明确映射到唯一 `scene_id`。
- 用户没有说“只生成提示词”“不要生成视频”“不要发送到 n8n”。

如果视频提示词只有自然语言地点、没有机器可读 `scene_id`，停止并返回上游修复。不得从剧情文字猜 `scene_id`。

---

## 权威来源优先级

场景身份只服从：

```text
handoffs/scene_asset_handoff.json
```

实际资产存在性只服从：

```text
assets/actual_asset_manifest.json
```

视频提示词不得覆盖 Scene Asset Planner 的地点绑定。

如果提示词写“集市”，但 `scene_id=SC05` 在 handoff 中绑定“林家堂屋”，这是上游冲突，应停止生产，不得自行选择其中一个。

---

## 两种背景参考模式

### A. `location_asset`

默认模式。`reference_asset_ids` 必须直接包含：

```text
location_asset_id
```

适合直接使用场景环境图 + 人物图作为视频参考。

### B. `scene_keyframe`

当上游已经生成并审核过“人物 + 正确场景”的场次/镜头关键帧时可以使用。

必须提供：

```text
background_reference_mode = scene_keyframe
scene_keyframe_asset_id
```

并满足：

- `scene_keyframe_asset_id` 存在于 `actual_asset_manifest.json`；
- `reference_asset_ids` 包含该关键帧；
- 关键帧 metadata 中的 `source_location_asset_id` / `base_location_asset_id` / `location_asset_id` 至少一个明确等于当前 `location_asset_id`；
- 若关键帧明确标记为 rejected / failed / blocked，则禁止使用。

不得用“看起来像这个场景”代替资产血缘验证。

---

## 工作流

1. 读取：
   - `project.json`
   - `review/video_prompt_gate_review.json`
   - `gates/scene_asset_coverage_gate.json`
   - `handoffs/scene_asset_handoff.json`
   - `assets/actual_asset_manifest.json`
   - 最终 shotlist / video prompt 输出
2. 为每个视频片段分配稳定 `clip_id`：`VP001`、`VP002`……
3. 从每个片段的 `scene_id` 查询 Scene Asset Handoff。
4. 把权威绑定写入：
   - `location_id`
   - `sub_location_id`
   - `location_asset_id`
5. 根据实际参考方式填写：
   - `background_reference_mode=location_asset`；或
   - `background_reference_mode=scene_keyframe` + `scene_keyframe_asset_id`
6. 只写入 `actual_asset_manifest.json` 中真实存在的 `reference_asset_ids`。
7. 按提示词中“图片1、图片2……”的实际顺序排列 `reference_asset_ids`。
8. 生成：

```text
video_prompts/video_prompt_manifest.json
dispatch/video_jobs/{video_job_id}.json
```

9. 先运行确定性场景绑定 Gate：

```bash
python3 scripts/validate_video_scene_bindings.py \
  --job dispatch/video_jobs/{video_job_id}.json \
  --scene-handoff handoffs/scene_asset_handoff.json \
  --assets assets/actual_asset_manifest.json \
  --out gates/video_scene_binding_gate.json
```

10. 仅当 `passed=true` 后运行 dry-run：

```bash
python3 scripts/submit_video_job.py \
  --job dispatch/video_jobs/{video_job_id}.json \
  --scene-handoff handoffs/scene_asset_handoff.json \
  --assets assets/actual_asset_manifest.json \
  --binding-gate-out gates/video_scene_binding_gate.json \
  --dry-run
```

11. dry-run 通过后正式提交：

```bash
python3 scripts/submit_video_job.py \
  --job dispatch/video_jobs/{video_job_id}.json \
  --scene-handoff handoffs/scene_asset_handoff.json \
  --assets assets/actual_asset_manifest.json \
  --binding-gate-out gates/video_scene_binding_gate.json
```

12. HTTP `200/201/202/204` 只表示 Webhook 接收成功。写入 `dispatch/last_video_submission.json` 并标记 `webhook_accepted_unverified`；只有响应包含 execution/task ID、固定 Job 输出目录已出现或收到可信回调，才变更为 `execution_confirmed` / `waiting_video_result`。

---

## 绑定生成规则

假设 handoff：

```json
{
  "SC03": {
    "location_id": "LOC-MARKET",
    "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
    "primary_location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY"
  }
}
```

那么属于 `SC03` 的所有视频片段，无论有几个镜头，都必须继承：

```text
location_id = LOC-MARKET
sub_location_id = SUBLOC-MARKET-SALT-STALL
location_asset_id = AST-LOC-MARKET-SALT-STALL-DAY
```

不得因为人物换机位、景别改变、动作变化而换成另一个 location asset。

只有进入新的 `scene_id`，或上游 Scene Asset Planner 正式更新 handoff，才能改变场景绑定。

---

## Video Scene Binding Gate 必查项

每条 clip 检查：

- `scene_id` 是否存在于 handoff；
- `location_id` 是否与 handoff 完全一致；
- `sub_location_id` 是否与 handoff 完全一致；
- `location_asset_id` 是否与 `primary_location_asset_id` 完全一致；
- `location_asset_id` 是否真实存在于 actual asset manifest；
- 所有 `reference_asset_ids` 是否真实存在；
- `location_asset` 模式是否直接引用正确背景；
- `scene_keyframe` 模式是否拥有正确的场景资产血缘；
- `clip_id`、`filename` 是否唯一；
- `duration` 是否 4–15 秒；
- `prompt` 是否非空、≤2200字符并以 `不要出现BGM，不要出现字幕` 开头。

任何错误都必须阻断生产。

---

## 固定默认值

保持旧版默认行为，避免升级后改变生成质量：

- 模型：`doubao-seedance-2-0-mini-260615`
- 分辨率：`720p`
- 画幅：继承 `project.json`，缺失使用 `16:9`
- 音频：`generate_audio=true`
- 水印：`false`
- 每片段最多有效生成次数：`2`
- 每片段参考图片：建议 1–4 张，硬上限 9 张

除非项目配置明确指定，否则不要自行切换 Fast、1080p 或其他模型。

---

## n8n 兼容规则

V2 在 `clips[]` 新增场景绑定字段，但发送给 Seedance/视频供应商时，n8n 应只映射供应商真正接受的字段。

推荐 n8n 保留以下字段用于日志、路由和 QA：

```text
scene_id
location_id
sub_location_id
location_asset_id
background_reference_mode
scene_keyframe_asset_id
```

而调用视频供应商 API 时仍只传其 API 接受的 prompt、duration、reference images、ratio 等字段。

详见 `references/N8N_COMPATIBILITY.md`。

---

## 安全约束

- 从环境变量读取 `N8N_VIDEO_WEBHOOK_URL`、`N8N_VIDEO_WEBHOOK_SECRET`。
- 禁止把密钥写入 JSON、日志、项目文件或聊天。
- 禁止发送 OpenClaw/NAS 绝对路径或图片 Base64。
- 禁止为了过 Gate 伪造 asset ID、scene ID、关键帧血缘、审核结果、时长或提示词。
- Gate 失败时只报告错误，不自动“修成能过”。应回到产生错误的上游模块修复。

---

## 完成条件

提交成功后报告：

```text
project_id
video_job_id
expected_count
scene_binding_gate = passed
n8n HTTP 状态
waiting_video_result
```

随后等待 `n8n_video_generation_completed` 回调，不在当前会话轮询视频供应商。
