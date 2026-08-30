# 数据契约

## 1. 逐章摘要

每个 `summaries/chapter_XXXX.summary.json` 至少包含：

```json
{
  "schema_version": "1.0",
  "chapter_id": "CH0001",
  "source_file": "chapters/raw/CH0001.txt",
  "title": "第一章",
  "source_char_count": 12345,
  "events": [
    {
      "event_id": "EV-CH0001-001",
      "summary": "可见事件",
      "cause": "原因",
      "effect": "结果",
      "source_anchor": "段落或字符范围"
    }
  ],
  "character_state_changes": [],
  "locations": [],
  "props": [],
  "timeline_facts": [],
  "clue_updates": [],
  "chapter_end_state": {},
  "adaptable_beats": [],
  "immutable_facts": []
}
```

## 2. 全书圣经

`book_bible.json` 只记录全局规则、主题、叙事视角、时代、地理、能力规则和不可改写事实。人物细节放 `characters.json`，时间放 `timeline.json`，伏笔放 `clue_ledger.json`，避免单文件无限膨胀。

所有事实应带：

- `fact_id`
- `value`
- `source_chapter_ids`
- `confidence`
- `status: confirmed | inferred | conflicted`

## 3. 改编覆盖账本

`adaptation_ledger.json` 中每个重要事件只能处于一种状态：

- `assigned`：已分配到某集；
- `pending`：尚未分配；
- `reserved_for_later`：明确延后；
- `intentionally_omitted`：明确删减并记录理由；
- `merged`：与其他事件合并并记录目标事件。

每条重要事件还应记录：

- `source_priority: core | supporting | optional`
- `adaptation_action` 与理由
- `visualizability: high | medium | low`
- `emotional_value`
- `payoff_type: setup | micro | primary | series`
- `generation_risk: low | medium | high`
- `episode_assignment`

## 4. 系列定位策略

`plan/format_strategy.json` 冻结本系列的专业定位，至少包含：

```json
{
  "schema_version": "1.1",
  "series_id": "demo",
  "format_profile": "domestic_vertical_manga",
  "genre_profile": "suspense_mystery",
  "target_audience": "目标受众",
  "distribution_context": "国内短视频平台",
  "aspect_ratio": "9:16",
  "episode_duration_seconds": 90,
  "tone": ["克制", "紧张", "带黑色幽默"],
  "core_promise": "观众持续追看的核心承诺",
  "story_engine": "每集如何产生推进与回报",
  "visual_style": {},
  "asset_strategy": {},
  "production_risk_policy": {},
  "user_requirements_applied": [],
  "decision_evidence": []
}
```

## 5. 分集简报

`episodes/episode_XXX.json` 必须包含：

```json
{
  "schema_version": "1.1",
  "series_id": "demo",
  "season_number": 1,
  "episode_number": 1,
  "episode_project_id": "demo_s01e001",
  "title": "标题",
  "status": "planned",
  "target_duration_seconds": 90,
  "aspect_ratio": "9:16",
  "format_profile": "domestic_vertical_manga",
  "genre_profile": "suspense_mystery",
  "source_chapter_ids": ["CH0001"],
  "source_event_ids": ["EV-CH0001-001"],
  "adaptation_brief": {
    "logline": "本集一句话",
    "episode_goal": "本集人物目标",
    "primary_conflict": "冲突双方与失败代价",
    "scene_beats": [],
    "ending_hook": "具体未完成动作、揭示、选择、危险或代价"
  },
  "hook_contract": {
    "hook_type": "danger",
    "hook_text": "前3秒可见钩子",
    "established_by_seconds": 3,
    "conflict_clear_by_seconds": 15,
    "visual_evidence": ["画面证据"]
  },
  "rhythm_map": [
    {"at_seconds": 0, "function": "hook", "change": "出现异常"},
    {"at_seconds": 12, "function": "conflict", "change": "目标和代价成立"},
    {"at_seconds": 35, "function": "turn", "change": "信息改变局势"},
    {"at_seconds": 65, "function": "payoff", "change": "主承诺得到一次兑现"},
    {"at_seconds": 85, "function": "ending_hook", "change": "新危险出现"}
  ],
  "emotion_curve": {
    "start": "不安",
    "pressure": "受困",
    "turn": "发现线索",
    "primary_payoff": "暂时夺回主动",
    "residual": "更大威胁逼近"
  },
  "payoff_map": [
    {"type": "primary", "at_seconds": 65, "promise": "本集承诺", "delivery": "实际兑现"}
  ],
  "visual_strategy": {
    "visual_anchor": "标志性画面或道具",
    "vertical_composition": "1-3人清晰关系",
    "asset_reuse_ids": [],
    "new_asset_requirements": [],
    "high_risk_shots": [],
    "risk_mitigation": []
  },
  "continuity_in": {},
  "immutable_facts": [],
  "spoiler_locks": [],
  "expected_continuity_out": {},
  "production": {
    "auto_production_mode": true,
    "delivery_format": "text_prompts",
    "max_video_prompt_seconds": 15,
    "stop_before_external_publish": true
  },
  "professional_gate": {
    "passed": true,
    "overall_score": 86,
    "dimension_scores": {
      "source_fidelity": 90,
      "hook_clarity": 85,
      "conflict_progression": 84,
      "emotion_payoff": 83,
      "character_integrity": 88,
      "visual_storytelling": 85,
      "continuity_safety": 92,
      "production_feasibility": 84,
      "asset_efficiency": 86,
      "ending_pull": 85
    },
    "hard_failures": [],
    "evidence": ["来源与设计证据"],
    "issues": [],
    "repairs": [],
    "attempts": 1
  }
}
```

## 6. 单集完成后的跨集状态

`drama-producer` 在调用 `complete` 前生成：

```json
{
  "schema_version": "1.0",
  "series_id": "demo",
  "episode_project_id": "demo_s01e001",
  "character_states": [],
  "prop_states": [],
  "location_states": [],
  "timeline_position": {},
  "clue_states": [],
  "unresolved_continuity_risks": []
}
```

## 7. 系列资产注册、复用与增量

系列资产采用两层结构：

- `asset_registry.json`：只保存稳定 ID、身份指纹、规范相对路径、大小、SHA256 和版本关系；
- `series_assets/{asset_id}/`：保存可跨集复用的规范图片副本，不依赖历史 n8n job 目录。

本集没有新增或更新资产时，`assets/series_asset_delta.json` 也必须是完整对象：

```json
{
  "schema_version": "1.2",
  "series_id": "demo",
  "episode_project_id": "demo_S01E002",
  "assets": []
}
```

新增基础资产示例：

```json
{
  "schema_version": "1.2",
  "series_id": "demo",
  "episode_project_id": "demo_S01E001",
  "assets": [
    {
      "asset_id": "AST-CH01-BASE",
      "category": "character",
      "name": "主角基础定妆",
      "asset_role": "base",
      "identity_fingerprint": "face-hair-costume-body-v1",
      "source_path": "/data/openclaw-assets/DEMO/demo_assets_001/DEMO_CH01_v01.png",
      "source_file_size": 2456789,
      "source_sha256": "64位十六进制SHA256"
    }
  ]
}
```

状态版必须使用新的 `asset_id`，并额外给出 `base_asset_id` 与 `state_version`。其 `identity_fingerprint` 必须和基础资产一致；伤痕、湿衣、服装变化等状态图不得覆盖基础定妆 ID。

每次派发前，总控会解析 `visual_strategy.asset_reuse_ids`，并验证：

1. ID 在注册表中唯一存在；
2. `canonical_relative_path` 位于当前系列的 `series_assets/` 内；
3. 文件可读且非空；
4. 文件大小与登记值相同；
5. 实际 SHA256 与登记值相同。

任何一项失败均停止派发，不进入生图或视频生产。下游必须使用 `series_asset_gate.py build-plan` 生成 `asset_generation_plan.json`，只提交其中的 `generation_assets`；注册表已复用的 ID 会出现在 `excluded_reuse_assets`，禁止再次付费生成。

---

# 8. v1.2 场景强绑定生产扩展

新规划项目推荐把 `episodes/episode_XXX.json.schema_version` 升级为：

```text
1.2
```

v1.2 保留 v1.1 的所有专业字段，并扩展 `visual_strategy` 与 `production`。

## 8.1 visual_strategy.scene_asset_policy

```json
{
  "visual_strategy": {
    "visual_anchor": "本集标志性视觉",
    "asset_reuse_ids": [],
    "new_asset_requirements": [],
    "high_risk_shots": [],
    "risk_mitigation": [],
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
}
```

这些路径描述的是单集 `workspace-drama-producer/projects/{episode_project_id}/` 内的相对路径。

## 8.2 production pipeline

```json
{
  "production": {
    "auto_production_mode": true,
    "pipeline_profile": "scene_bound_auto_v1.2",
    "require_pipeline_evidence": true,
    "delivery_format": "text_prompts",
    "min_auto_video_clip_seconds": 4,
    "max_video_prompt_seconds": 15,
    "stop_before_external_publish": true
  }
}
```

AUTO v1.2 的生成视频 clip 必须是 4–15 秒整数；1–3 秒仅能作为内部 Shot。

## 8.3 Pipeline Contract

总控每次 `dispatch-next` 为本集生成：

```text
input/production_pipeline_contract.json
```

它冻结：

- required skill sequence；
- scene asset policy；
- required artifact paths；
- required gates；
- video duration / cross-scene policy；
- final pipeline evidence requirement。

Contract SHA256 会进入 `series_episode_context.json` 和队列运行记录。

## 8.4 Scene Asset authoritative handoff

本集下游必须生成：

```text
handoffs/scene_asset_handoff.json
```

权威关系：

```text
scene_id
→ location_id
→ sub_location_id
→ primary_location_asset_id
```

后续 Shotlist 和 Video Dispatcher 不得重新猜地点。

## 8.5 Pipeline Evidence

`review/series_pipeline_evidence.json` 至少验证：

- `scene_asset_coverage`；
- `location_prompt_manifest`；
- `shot_scene_binding`；
- `video_prompt_review`；
- `video_scene_binding`。

每个 Gate 和关键 artifact 都记录相对路径与 SHA256。`series_orchestrator.py complete` 在 commit 前重新读取文件并校验 hash。

## 8.6 Scene Planner 动态复用

`scene_asset_handoff.json.verified_reuse_asset_ids` 是本集 Scene Planner 在读取系列注册表后确认的复用资产。

`series_asset_gate.py build-plan` 应同时读取：

```text
series_episode_context.asset_generation_policy.forbidden_generation_asset_ids
+
scene_asset_handoff.verified_reuse_asset_ids
```

两者并集都禁止再次进入 generation assets。
