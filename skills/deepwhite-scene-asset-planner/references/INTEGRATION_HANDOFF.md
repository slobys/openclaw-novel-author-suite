# 上下游集成规范

## A. 与 Series Orchestrator

推荐在 `episode_XXX.json.visual_strategy` 中新增或同步：

```json
{
  "scene_asset_plan_path": "assets/scene_asset_plan.json",
  "scene_asset_handoff_path": "handoffs/scene_asset_handoff.json",
  "scene_asset_gate_path": "gates/scene_asset_coverage_gate.json"
}
```

`asset_reuse_ids` 中应包含本集已验证复用的 location asset IDs。

`new_asset_requirements` 应同步本技能的 generation requirements，但不要把自然语言需求当作唯一权威来源；权威明细仍是 `location_asset_requirements.json`。

---

## B. 与 Image Prompt Builder

原有 Image Prompt Builder 对完整剧本会“挑少量关键静态图”。当输入来自本技能时，必须覆盖这一默认行为。

建议上游指令：

```text
读取 assets/location_asset_requirements.json。
对 generation_requirements[] 逐条生成一一对应的中英文静态场景图片提示词。
不得重新筛选、合并或删除 requirement。
必须保留原 asset_id、scene_ids、location_id、sub_location_id、identity_fingerprint。
```

输出映射到现有 Asset Job：

```json
{
  "asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
  "category": "location",
  "name": "青石集市·盐摊·白天",
  "filename": "AST-LOC-MARKET-SALT-STALL-DAY.png",
  "prompt_zh": "...",
  "prompt_en": "...",
  "metadata": {
    "scene_ids": ["SC03"],
    "continuity_notes": "保持盐摊空间结构与身份指纹"
  }
}
```

---

## C. 与 n8n Asset Dispatcher

现有 `category=location` 已兼容，无需增加新 category。

必须保证：

- reuse asset 不再次提交 n8n；
- generation requirement 每个 asset_id 只提交一次；
- n8n 返回的 actual asset manifest 保留原 asset_id；
- 场景图审核失败时，只重做失败 asset，不重做整批人物/道具。

---

## D. 与 Continuity Worldstate

Continuity 负责“状态事实”，Scene Asset Planner 负责“资产身份和绑定”。

Continuity 提供：

```text
时间
天气
门窗/环境变化
空间关系
剧情造成的环境状态
```

Scene Asset Planner 判断这些变化是否值得形成新的 location Variant。

不得把每个连续性微变化都生成新背景图。

---

## E. 与 Shotlist Builder

Shotlist 对每个 shot 继承 Scene 绑定：

```json
{
  "shot_id": "SH008",
  "scene_id": "SC03",
  "location_id": "LOC-MARKET",
  "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
  "location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY"
}
```

若一个 shot 需要场景关键帧，可以基于该 `location_asset_id` + character assets 生成关键帧，但关键帧不能改变地点身份。

---

## F. 与 Video Dispatcher

推荐把现有 VIDEO_JOB_SCHEMA 的 clip 扩展：

```json
{
  "clip_id": "VP008",
  "scene_id": "SC03",
  "location_id": "LOC-MARKET",
  "location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
  "prompt": "...",
  "duration": 8,
  "reference_asset_ids": [
    "AST-CH-LIN-MANCHANG",
    "AST-LOC-MARKET-SALT-STALL-DAY"
  ]
}
```

Video Gate 应检查：

```text
scene_id 存在于 scene_asset_handoff
clip.location_asset_id == handoff.primary_location_asset_id
location_asset_id 存在于 actual_asset_manifest 或已验证系列 registry
reference_asset_ids 包含正确 location asset，或包含以其为基础生成且已审核通过的 scene keyframe
```

任何一项失败都禁止提交 n8n 视频任务。

---

## G. 推荐流水线位置

```text
01 Screenwriting
→ 02 Continuity Worldstate
→ 02.5 Scene Asset Planner   ← 新增
→ 03 Image Prompt Builder
→ n8n Asset Generation
→ Asset Review
→ 04 Shotlist Builder
→ Video Prompt
→ Video Dispatcher
→ n8n Video Generation
→ Final Composition
```
