---
name: deepwhite-n8n-asset-dispatcher
description: 将已经通过资产计划与图片提示词 Gate 的人物、场景、道具和风格参考整理成严格 JSON，并通过受保护的 Webhook 提交给 n8n 自动生成图片。Use after the image-prompt manifest is complete and before the final actual-asset-based shotlist. Preserve planned asset IDs and prompts, exclude verified reuse assets, validate the job manifest, and invoke the bundled sender. Do not rewrite the story, invent missing assets, or treat HTTP acceptance as confirmed execution.
metadata: {"openclaw":{"requires":{"bins":["node"],"env":["N8N_ASSET_WEBHOOK_URL","N8N_ASSET_WEBHOOK_SECRET"]}}}
---

# DeepWhite n8n Asset Dispatcher

把 OpenClaw 已经生成并确认的资产图片提示词，转换成机器可读任务并提交给 n8n。这个技能只负责“整理与派发”，不重新创作剧本、分镜或资产设定。

## 使用时机

仅在以下条件满足后使用：

1. 上游技能已经给出最终资产图片提示词。
2. 人物、场景、道具、风格与连续性信息已经确认。
3. 用户明确要求自动提交到 n8n 生图，或当前自动化任务规定完成后自动提交。

## 最高规则

- 不让 n8n 解析 Markdown 或自然语言资产清单；必须发送严格 JSON。
- 不修改上游提示词的角色身份、服装、道具、场景结构、时代、光线与连续性锚点。
- 缺少提示词的资产标记为 `blocked`，不得自行补写后提交。
- 每个资产必须有稳定的 `asset_id`、`category`、`name`、`filename` 和至少一种提示词。
- 文件名只使用英文字母、数字、下划线和短横线，扩展名统一为 `.png`。
- 不把 n8n Webhook 密钥或 Gemini API Key 写入任务 JSON。
- 默认一批任务只属于一个 `project_id` 和一个 `job_id`。

## 标准分类

- `character`：人物标准设定图、表情图、服装状态图
- `location`：场景、环境、空间设定图
- `prop`：关键道具、可读文字道具、载具
- `style`：全局风格、材质、灯光参考图
- `storyboard`：故事板或构图参考图
- `other`：无法归入上述类型但已确认需要生成的资产

## 任务 JSON

严格使用 `references/ASSET_JOB_SCHEMA.md`。核心结构：

```json
{
  "schema_version": "1.0",
  "job_id": "episode01_assets_20260724_001",
  "project_id": "episode01",
  "source": "openclaw",
  "defaults": {
    "model": "gemini-3.1-flash-image",
    "aspect_ratio": "16:9",
    "image_size": "2K"
  },
  "assets": []
}
```

## 工作流

1. 从上游最终结果提取资产，不读取未确认草稿。
2. 按人物、场景、道具、风格等分类。
3. 为每项生成稳定 ID，例如：
   - `CHAR_JINGJING_BASE_001`
   - `LOC_LIVINGROOM_NIGHT_001`
   - `PROP_POLAROID_001`
4. 中文提示词放入 `prompt_zh`，英文提示词放入 `prompt_en`。
5. 如果上游只有一种语言，只填写已有字段，不做机械翻译。
6. 将任务写入当前项目：

```text
dispatch/asset_jobs/{job_id}.json
```

7. 校验 JSON 后，通过本技能脚本提交：

```bash
node ~/.openclaw/skills/deepwhite-n8n-asset-dispatcher/scripts/send-assets-to-n8n.mjs dispatch/asset_jobs/{job_id}.json
```

如果本技能安装在工作区而不是 `~/.openclaw/skills`，从当前技能 location 找到脚本并执行，不要猜路径。

8. HTTP 2xx 后记录 `webhook_accepted_unverified`；只有拿到 execution/task ID、固定 Job 输出目录或可信回调后，才报告任务已经开始执行。
9. 提交成功后，只报告 job_id、资产数量、n8n 接收状态和清单文件路径。不得把密钥输出到聊天。

## 提交前检查

- `assets` 数量大于 0。
- 所有 `asset_id` 在本任务内唯一。
- 所有 `filename` 在本任务内唯一。
- 每项至少有非空 `prompt_zh` 或 `prompt_en`。
- `aspect_ratio` 仅使用：`1:1`、`2:3`、`3:2`、`3:4`、`4:3`、`4:5`、`5:4`、`9:16`、`16:9`、`21:9`。
- `image_size` 仅使用：`1K`、`2K`、`4K`。
- `gemini-3.1-flash-lite-image` 只使用 `1K`。

## 失败处理

- HTTP 401/403：停止，报告 Webhook 鉴权失败。
- HTTP 404：停止，报告 n8n 生产 Webhook 地址不正确或工作流未激活。
- HTTP 429/5xx：脚本自动重试；仍失败则保留 JSON 文件，报告可重新提交。
- 任务结构错误：不发送，逐项列出缺失字段。

## 输出格式

```text
【n8n 资产任务已提交】
job_id：...
project_id：...
资产数量：...
任务清单：dispatch/asset_jobs/....json
n8n 接收状态：webhook_accepted_unverified / execution_confirmed
```

<!-- BEGIN DEEPWHITE_CONTINUITY_DISPATCH_V2 -->

# Continuity Asset Job v2.1（最高优先级）

当任务 `schema_version` 为 `2.x` 或包含 `reference_inputs` 时，必须使用连续资产派发模式。

除旧版必需字段外，保留：

```text
parent_asset_id
family_id
style_id
asset_code
generation_stage
lock_id
lock_hash
depends_on
reference_inputs
anchor_roles
```

派发前必须：

1. 校验 project/job/asset ID 和 filename 均为安全 ASCII 值，禁止路径片段；
2. 校验依赖图无环，外部依赖必须同时出现在 `reference_inputs`；
3. 确认所有必需参考图声明包含 `approved_only: true`；
4. 按四锁原文重新计算完整 `sha256:<64hex>`，不得只检查非空；
5. 运行 `validate-continuity-job.mjs`；发送脚本也会再次执行同一验证；
6. 使用 `send-continuity-job-to-n8n.mjs` 提交；`--dry-run` 不要求 Webhook 环境变量；
7. 正式自动生产必须加 `--wait --registry-snapshot=assets/reference_registry.json`；
8. 只有每个必需资产都为 `approved`，且 `job_id`、`payload_sha256`、`lock_hash`、文件大小和文件 SHA256 全部匹配，才算本阶段完成。

`shared_asset_root` 只能来自 Gateway 的 `OPENCLAW_ASSET_SHARED_ROOT`，禁止由任务 Payload 指定。HTTP 2xx 仍只记录为 `webhook_accepted_unverified`。

不得删除额外连续性字段后降级为 v1 任务。

<!-- END DEEPWHITE_CONTINUITY_DISPATCH_V2 -->
