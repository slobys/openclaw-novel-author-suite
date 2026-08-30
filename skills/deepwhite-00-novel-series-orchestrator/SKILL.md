---
name: deepwhite-00-novel-series-orchestrator
description: DeepWhite 小说转 AI 漫剧系列总控 v1.2。把整本 TXT、Markdown、DOCX 或 EPUB 小说改编为可追溯、连续性安全、场景资产强绑定、可串行自动生产的多集 AI 漫剧，并把 Screenwriting→Continuity→Scene Asset Planner→Image Prompt Builder→n8n 资产→Shotlist→Video Dispatcher→n8n 视频→最终合成写成不可跳过的流水线契约。用于长篇小说改编、竖屏漫剧、动态漫、AI 短剧、多集规划、跨集连续性、场景切换、成本控制、资产复用和自动 Gate；不替代具体单集技能。
---

# DeepWhite 00｜小说转 AI 漫剧系列总控 v1.2

本技能是 DeepWhite 系列的**总调度器和生产状态机**。它不直接写最终图片/视频提示词，也不直接调用图片模型、视频模型或 FFmpeg；它负责：

1. 把整本小说规划成可追溯分集；
2. 串行派发一集；
3. 为下游生成固定的 `production_pipeline_contract.json`；
4. 强制下游按正确 Skill 顺序执行；
5. 强制场景资产规划、场景图生成、分镜绑定和视频绑定全部留下确定性 Gate；
6. 只有整条 Pipeline Evidence 通过，才允许把本集标记为完成并派发下一集。

v1.2 的核心升级是：**“剧情换场”不再只是自然语言要求，而是系列生产契约的一部分。**

---

## 一、何时使用

- 用户提供整本小说或大量章节，要求制作多集 AI 漫剧、动态漫或短剧；
- 需要连续自动生成多集；
- 需要跨集人物、服装、时间线、伏笔、道具、地点和资产一致性；
- 需要人物随剧情进入不同地点，并让视频始终引用当前 Scene 的正确场景资产；
- 需要减少同一张背景图长时间复用导致的视觉疲劳；
- 需要避免复用场景被重复付费生成。

单集、单场景、单张图片任务不必调用本技能。

---

## 二、决策优先级

发生冲突时按以下顺序处理：

1. 用户当前明确要求；
2. 原著核心设定、人物动机与因果；
3. 已冻结的系列定位与内容边界；
4. 连续性世界状态；
5. Scene Asset Handoff 的机器绑定；
6. 平台节奏、影视表达与视觉多样性；
7. 生成成本与制作便利。

不得为了“多换背景”擅自把人物传送到剧情没有发生的地点。场景丰富优先来自：**真实剧情换场、同一大地点的合理子空间、时间/天气/环境状态 Variant、镜头与构图变化**。

---

## 三、总控不可违反的硬规则

- 不把整本小说直接塞给某一集下游 Agent。
- 所有改编事件必须可追溯到章节摘要或原文锚点。
- 先完成全书/全季规划，再开始首集生产。
- 同一系列最多一集处于 `running`。
- 上一集未取得有效最终 MP4，不得派发下一集。
- 单集失败后暂停系列，禁止自动整集无限重跑。
- 已完成的 `episode_project_id` 永不重复派发。
- 所有跨集资产使用稳定 `asset_id`；状态版不得覆盖基础资产。
- 复用资产必须来自当前系列 `asset_registry.json + series_assets/`，并通过大小与 SHA256 校验。
- `deepwhite-scene-asset-planner` 必须在连续性分析之后、图片提示词生成之前执行。
- `scene_asset_coverage_gate.json.passed` 不为 true 时，禁止进入场景生图。
- Scene coverage 必须以 `script/scene_index.json` 为分母；移动 Scene 必须通过路线锚点检查。
- Image Prompt Builder 检测到 `location_asset_requirements.json` 后必须进入 `STRICT_ASSET_PLAN_MODE`。
- `location_prompt_manifest_gate.json.passed` 不为 true 时，禁止提交场景生图。
- `angle_pack_gate.json.passed` 与 `asset_retry_budget_gate.json.passed` 不为 true 时，禁止提交图片任务。
- Shotlist Builder 必须继承 Scene Asset Handoff，不得自行换场景资产。
- `environment_continuity_gate.json.passed` 不为 true 时，禁止生成视频提示词。
- `shot_scene_binding_gate.json.passed` 不为 true 时，禁止生成 dispatcher-ready 视频提示词。
- Video Dispatcher 必须运行 Video Scene Binding Gate；失败时禁止向 n8n 提交视频任务。
- 总控 `complete` 前必须验证 `review/series_pipeline_evidence.json`；任一强制 Gate 缺失、失败或哈希不一致时，不得完成本集。

---

# 四、固定单集生产流水线

AUTO 生产默认使用：

```text
scene_bound_auto_v1.2
```

执行顺序固定为：

```text
00 Series Orchestrator 派发 episode context + pipeline contract
│
├─ 01 deepwhite-screenwriting-v1
│     └─ 单集剧本 / script/scene_index.json
│
├─ 02 deepwhite-continuity-worldstate-zh
│     └─ 时间、天气、环境状态、人物/道具连续性
│
├─ 02.5 deepwhite-scene-asset-planner
│     ├─ assets/scene_asset_plan.json
│     ├─ assets/location_asset_requirements.json
│     ├─ handoffs/scene_asset_handoff.json
│     └─ gates/scene_asset_coverage_gate.json
│
├─ 03 deepwhite-image-prompt-builder V2
│     ├─ STRICT_ASSET_PLAN_MODE
│     ├─ assets/location_asset_prompt_manifest.json
│     ├─ assets/angle_pack_manifest.json
│     ├─ gates/location_prompt_manifest_gate.json
│     └─ gates/angle_pack_gate.json
│
├─ 03.5 deepwhite-n8n-asset-dispatcher
│     ├─ 只提交真正 generation_assets
│     └─ gates/asset_retry_budget_gate.json（跨 Job 最多 3 次）
│
├─ 04 Asset Result + AI Review
│     └─ assets/actual_asset_manifest.json
│
├─ 05 deepwhite-shotlist-builder-zh-user v2.8+
│     ├─ shots/shot_scene_bindings.json
│     ├─ gates/environment_continuity_gate.json
│     ├─ gates/shot_scene_binding_gate.json
│     ├─ review/video_prompt_gate_review.json
│     └─ video_prompts/video_prompt_manifest.json（基于实际图片的候选终稿）
│
├─ 05.5 deepwhite-shot-transition-builder-zh（仅必要时）
│     └─ 不得改变 scene/location/location_asset 机器绑定
│
├─ 05.75 Video Prompt Readiness
│     └─ 若 Transition 改动提示词，重跑 Shot Scene Binding Gate 后冻结最终 manifest
│
├─ 06 deepwhite-n8n-video-dispatcher V2
│     ├─ dispatch/video_jobs/{video_job_id}.json
│     └─ gates/video_scene_binding_gate.json
│
├─ 07 n8n Video Generation + Review
│
├─ 08 FFmpeg / Final Composition
│     └─ final_video_manifest.json
│
├─ 09 validate_episode_pipeline.py
│     └─ review/series_pipeline_evidence.json
│
└─ 10 series_orchestrator.py complete
      └─ 通过后才允许推进下一集
```

任何下游 Agent 都不得重新排序强制阶段。

---

## 五、Scene Asset Planner 是强制阶段，不是可选增强

过去的流程：

```text
剧本 → Image Prompt Builder 自己选少量关键图
```

会导致多个 Scene 最终共用一张“万能背景”。v1.2 改为：

```text
剧本
→ Continuity
→ Scene Asset Planner 先决定每个 Scene 在哪里
→ Image Prompt Builder 只负责怎么画
```

权威映射：

```text
scene_id
→ location_id
→ sub_location_id
→ primary_location_asset_id
```

例如：

```text
SC01 → 林家堂屋 → AST-LOC-LIN-HOME-LIVINGROOM-DAY
SC02 → 林家庭院 → AST-LOC-LIN-HOME-COURTYARD-DAY
SC03 → 村口老树 → AST-LOC-VILLAGE-ENTRANCE-DAY
SC04 → 集市入口 → AST-LOC-MARKET-ENTRANCE-DAY
SC05 → 盐摊 → AST-LOC-MARKET-SALT-STALL-DAY
```

后续 Shot、Video Prompt、Video Job 必须沿这条链继承，不得从自然语言重新猜。

---

## 六、总控派发时必须生成 Pipeline Contract

`dispatch-next` 除了写：

```text
input/series_episode_context.json
```

还必须写：

```text
input/production_pipeline_contract.json
```

Contract 至少冻结：

- `pipeline_profile = scene_bound_auto_v1.2`；
- required skill sequence；
- required artifact paths；
- required Gate paths；
- 场景资产覆盖必须 100%；
- Shot/Prompt/Video 场景绑定必须 100%；
- 4–15 秒视频生成任务规则；
- 禁止跨 Scene 合并一个视频任务；
- Scene Planner 的复用资产必须进入资产复用 Gate；
- 完成前必须生成 Pipeline Evidence。

下游不得静默改写 Contract。需要变更时必须重新生成 Contract，并使原 Evidence 失效。

---

## 七、系列资产复用 v1.2

### 1. 分集简报中的 `asset_reuse_ids`

它仍用于系列层预判人物/道具/地点复用，但不再是本集最终场景复用的唯一来源。

### 2. Scene Planner 的动态复用

Scene Planner 会输出：

```text
handoffs/scene_asset_handoff.json
  verified_reuse_asset_ids[]
```

`series_asset_gate.py build-plan` 必须同时读取它，并把这些 ID 加入：

```text
forbidden_generation_asset_ids
```

因此即使分集简报事先没有预测到某个旧场景可复用，Scene Planner 后来确认可复用后也不能再次付费生图。

### 3. 复用资产进入 Shotlist

当前 n8n manifest 通常只含新图，所以在 Shotlist 阶段必须把：

```text
n8n_generated
+
series_reuse
```

合并成：

```text
assets/actual_asset_manifest.json
```

Scene Handoff 中任何 `location_asset_id` 不存在于 enriched manifest 时，Shot Gate 必须失败。

---

# 八、Gate 状态机

## Gate A｜Series Professional Gate

由 `validate_series.py` 检查：

- 来源覆盖；
- 钩子；
- 冲突；
- 情绪/回报；
- 人物完整性；
- 视觉可拍性；
- 连续性；
- 生产可行性；
- 资产效率；
- 结尾追更力。

## Gate B｜Scene Asset Coverage Gate

必须：

```text
passed = true
scene_coverage_ratio = 1.0
primary_binding_ratio = 1.0
```

禁止：漏 Scene、重复 Scene 绑定、未知 primary asset、reuse/generation 重叠。

## Gate C｜Location Prompt Manifest Gate

必须保证：

```text
Planner generation_requirements N 条
=
Image Prompt Builder 输出 N 条
```

`asset_id`、`scene_ids`、`location_id`、`sub_location_id`、`identity_fingerprint` 一一保持。

## Gate D｜Shot Scene Binding Gate

必须：

```text
scene_coverage_ratio = 1.0
shot_binding_ratio = 1.0
prompt_binding_ratio = 1.0
```

## Gate E｜Video Prompt Review Gate

`review/video_prompt_gate_review.json` 必须明确允许进入视频生产。

## Gate F｜Video Scene Binding Gate

每条 clip：

```text
clip.scene_id
→ handoff.scene_bindings[scene_id]
→ exact location_id/sub_location_id/allowed location_asset_id/route_anchor_id
```

并验证真实资产存在。

## Gate G｜Pipeline Evidence Gate

最终 MP4 完成后，运行：

```bash
python3 scripts/validate_episode_pipeline.py \
  --project-root ${OPENCLAW_STATE_DIR}/workspace-drama-producer/projects/{episode_project_id} \
  --out ${OPENCLAW_STATE_DIR}/workspace-drama-producer/projects/{episode_project_id}/review/series_pipeline_evidence.json
```

只有 `passed=true` 才允许：

```bash
series_orchestrator.py complete ... --pipeline-evidence ...
```

---

# 九、失败回退原则

不要因为某个 Gate 失败就从头重做整集。

```text
Scene Asset Gate 失败
→ 回到 Scene Asset Planner

Location Prompt Gate 失败
→ 回到 Image Prompt Builder

图片审核失败
→ 只重做失败 asset

Shot Scene Binding Gate 失败
→ 回到 Shotlist/绑定生成

Video Scene Binding Gate 失败
→ 回到 Video Job/上游 Prompt Manifest

单个视频片段失败
→ 只重试该 clip（遵守 provider 重试上限）

最终合成失败
→ 不重新生图/生视频，先修合成
```

只有不可消解的上游设定冲突、来源覆盖失败或连续两次结构化修复仍失败时，才暂停系列等待用户。

---

# 十、分集数据契约

新规划项目推荐 `episode_XXX.json.schema_version = 1.2`。

`visual_strategy` 除原字段外增加：

```json
{
  "scene_asset_policy": {
    "required": true,
    "planner_skill": "deepwhite-scene-asset-planner",
    "require_100_percent_scene_coverage": true,
    "allow_editorial_sublocation_enrichment": true,
    "same_background_soft_limit_seconds": 24,
    "same_background_hard_limit_seconds": 35
  },
  "scene_asset_plan_path": "assets/scene_asset_plan.json",
  "location_asset_requirements_path": "assets/location_asset_requirements.json",
  "scene_asset_handoff_path": "handoffs/scene_asset_handoff.json",
  "scene_asset_gate_path": "gates/scene_asset_coverage_gate.json"
}
```

`production` 推荐：

```json
{
  "auto_production_mode": true,
  "pipeline_profile": "scene_bound_auto_v1.2",
  "require_pipeline_evidence": true,
  "delivery_format": "text_prompts",
  "max_video_prompt_seconds": 15,
  "min_auto_video_clip_seconds": 4,
  "stop_before_external_publish": true
}
```

v1.1 分集仍可读取；但在 AUTO 模式下，总控派发时默认升级到 `scene_bound_auto_v1.2` Contract，除非项目显式设置 `legacy_pipeline_allowed=true`。

---

# 十一、自动 Gate 与人工 Gate

用户要求全自动时：

- 不反复要求“确认资产/确认位置/确认时间”；
- 用 JSON Gate + 确定性验证器 + AI Review Evidence 替代人工确认；
- 但任何硬 Gate 失败必须停止当前阶段；
- 不得伪造 `passed=true`；
- 不得为了过 Gate 修改 asset_id、scene_id、hash、审核状态或血缘。

用户明确要求手动确认时，可以保留人工 Gate，但场景绑定的确定性验证仍建议执行。

---

# 十二、兼容性

本版本预期配套：

```text
deepwhite-screenwriting-v1
deepwhite-continuity-worldstate-zh
deepwhite-scene-asset-planner
deepwhite-image-prompt-builder V2+
deepwhite-n8n-asset-dispatcher
deepwhite-shotlist-builder-zh-user v2.8+
deepwhite-shot-transition-builder-zh（可选）
deepwhite-n8n-video-dispatcher V2+
```

Webhook event 不变：

```text
deepwhite_series_episode_ready
```

因此不要求为了 v1.2 改动总控 Hook URL。

---

# 十三、资源

- `references/MANHUA_DRAMA_ADAPTATION.md`：平台漫剧改编规则；
- `references/DATA_CONTRACTS.md`：系列、分集、资产和 Pipeline 数据契约；
- `references/PRODUCTION_PIPELINE_V1_2.md`：固定单集生产状态机；
- `references/PIPELINE_EVIDENCE_SCHEMA.md`：完成前证据格式；
- `references/MIGRATION_V1_1_TO_V1_2.md`：升级说明；
- `scripts/ingest_novel.py`：小说分章；
- `scripts/validate_series.py`：系列规划验证；
- `scripts/series_orchestrator.py`：入队、派发、完成、失败恢复；
- `scripts/series_asset_gate.py`：跨集资产注册/复用/生成清单 Gate；
- `scripts/validate_episode_pipeline.py`：最终整条生产链证据 Gate。
