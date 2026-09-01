---
name: "deepwhite-asset-demand-resolver"
description: "镜头意图、按需资产、最小参考覆盖：生成可验证的需求清单与分波次生图计划。"
---

# DeepWhite Asset Demand Resolver

按以下步骤把剧本与场景绑定转换为最小图片资产集合。此技能只决定“哪些图片值得生成”；Scene Pack仍决定四锁和具体Prompt，Image Prompt Builder仍只打包，n8n仍只执行。

## 1. 生成镜头意图

在 `SHOT_INTENT_ONLY` 模式读取 `project.json`、`script/episode_script.md`、`script/scene_index.json`、`continuity/continuity_handoff.json` 与 `handoffs/scene_asset_handoff.json`。为每个预期镜头写入稳定 `shot_id`、精确继承的Scene绑定、人物、观察方向、景别、动作、道具状态与场景视图需求；输出 `shots/shot_intent_manifest.json` 和 `shots/shot_intent_bindings.json`。不得生成图片、最终分镜、视频Prompt或改变Scene绑定。完成标准：每个意图都有消费镜头和唯一Scene绑定，且Shot Intent绑定文件不与后续 `shots/shot_scene_bindings.draft.json` 共用路径。

## 2. 建立视觉需求

把每项需要稳定参考的视觉事实写成 `demands[]`：
- 每项包含 `demand_id`、非空 `shot_ids[]`、`category`、`risk_level`、`required`。
- 只有低风险背景细节可设置 `allow_text_only=true`。
- 角色身份、剧情核心道具、场景身份、近景脸部、极端视角、持续状态变化不得标为低风险文本覆盖。
完成标准：每个生成相关需求可追溯到至少一个镜头。

## 3. 建立候选资产

为能够覆盖需求的复用资产或计划资产写入 `candidates[]`：
- 每项包含 `asset_id`、`category`、`covers[]`、`generation_wave`。
- 人物、动物、生物候选写 `tier`、`angle_id` 和 `angle_pack_mode`。
- 单集默认 `angle_pack_mode=on_demand`；不得仅因 `episode_important` 创建八方向候选包。
- `series_core` 只有在系列合同明确要求时才可使用 `angle_pack_mode=full`，并写 `series_library=true`；系列库回填不得阻断当前集未使用方向。
- Wave 0只放主身份锚点、必要场景母版与剧情关键道具；Wave 1只放镜头实际需要的侧背视角、脸部、动作、状态、反向机位或路线机位。
完成标准：候选资产本身不等于生成要求，未覆盖真实需求的候选保持可跳过。

## 4. 应用按需规则

按以下规则减少候选：
- 人物：可见重要人物默认一个干净单视图Anchor-A；只有近景、强表情或频繁正反打才候选Anchor-B；只有实际镜头角度超出已有锚点可靠覆盖时才候选CP视图。
- 场景：默认一个M01；只有反向拍摄、越轴、路线移动、关键地标揭示或新子区域才候选P/V/CV/PX/路线资产。
- 道具：只有剧情核心、特写、持握跨片段、明确状态变化或错误外形会破坏剧情时才候选独立资产；普通家具与背景物嵌入场景。
- 依赖：从Anchor-A/B向所需视图扇出；左右方向分支隔离。不得用一条八方向长链让单个失败阻断整包。
完成标准：完整包是系列缓存策略，不是单集开工条件。

## 5. 解析最小覆盖

调用工作区权威Runner：

```bash
python3 scripts/resolve_asset_demand.py \
  --intent shots/shot_intent_manifest.json \
  --registry assets/reference_registry.json \
  --manifest-out assets/asset_demand_manifest.json \
  --coverage-out assets/reference_coverage_plan.json \
  --gate-out gates/asset_demand_coverage_gate.json
```

Registry尚不存在时可省略 `--registry`；存在时只能把 `status=approved` 的条目作为复用。Runner使用确定性最小覆盖：先复用已批准资产，再选择覆盖最多需求的计划资产，绝不选择零消费资产。完成标准：命令退出0且Gate通过。

## 6. 验证交接

必须满足：
- `coverage_ratio == 1.0`；
- `missing_demand_ids == []`；
- `orphan_generation_asset_ids == []`；
- 每个 `generation_requirements[]` 有非空 `consumer_shot_ids[]`，或显式 `series_library=true`；
- `reuse_assets[]` 不得重新进入n8n任务；
- Wave 0与Wave 1分别打包，任务写同一 `demand_manifest_path`、`demand_gate_path` 与对应 `demand_wave`。
Gate失败时返回需求或候选规划修复；不得通过增加无消费图片、静默切换完整包或退化为纯文本来伪造覆盖。
