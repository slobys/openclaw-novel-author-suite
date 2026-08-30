---
name: deepwhite-scene-asset-planner
description: 为 AI 漫剧/短剧自动识别剧本中的地点、子场景、时间与环境状态，建立 scene_id → location_id → sub_location_id → location_asset_id 的强绑定，并规划可复用与必须新增的场景图片资产。Use after screenplay/continuity analysis and before still-image prompt generation or n8n asset generation. Use when a project needs automatic scene switching, location asset coverage, background variety, cross-episode location reuse, location-state variants, or deterministic validation that every scene/video clip has the correct environment asset. Do not generate final image prompts or video prompts; output structured scene-asset planning and gate evidence only.
---

# DeepWhite Scene Asset Planner｜场景资产规划器

本技能位于 **剧本/连续性分析之后、静态图片提示词生成之前**。它不是“多生成几张背景图”的提示词技巧，而是 DeepWhite 流水线中的场景资产调度层。

它负责把剧本中的叙事场次变成稳定、可复用、可验证的场景资产关系：

```text
剧情场次 Scene
  ↓
地点 Location
  ↓
子场景 Sub-location
  ↓
环境状态 Variant
  ↓
场景图片资产 Location Asset
  ↓
scene_id 强绑定 location_asset_id
```

最终必须保证：**每一个需要可见环境的场次都有一个主场景资产；发生空间移动的场次还必须有按顺序排列的路线锚点资产。后续分镜和视频任务不得自行猜测背景。**

---

## 何时使用

- 已完成单集剧本、分场大纲或连续性分析，需要进入图片资产规划。
- 自动化短剧中人物长期停留在同一张场景图，需要按剧情切换地点/子场景。
- 同一地点需要区分堂屋、卧室、院子、入口、街角、柜台等可视子空间。
- 需要跨集复用已有场景资产，同时只生成真正缺失的新场景。
- 需要把场景资产结果交给 `deepwhite-image-prompt-builder`、n8n 生图、shotlist 和 video dispatcher。

如果用户只要一张环境概念图提示词，不使用本技能，直接使用静态图片提示词技能。

---

## 核心职责

本技能只负责以下六件事：

1. **完整枚举场次**：读取当前制作范围内所有 scene，不能只挑“重点场景”。
2. **规范化地点层级**：建立 Location → Sub-location → Variant 三层环境身份。
3. **复用判断**：优先匹配系列资产注册表中的已有 location 资产。
4. **新增资产规划**：只有缺失或状态差异足够大时才生成新场景图。
5. **场景与路线强绑定**：固定 scene 的 primary/allowed assets，并为移动场次建立 departure/path/turn/reveal/arrival。
6. **权威场景覆盖 Gate**：以 `script/scene_index.json` 为分母达到 100% 后才能交给图片提示词/n8n。

本技能 **不负责**：

- 不写最终中英文图片提示词；
- 不调用图片生成模型；
- 不写视频运动提示词；
- 不设计逐镜头运镜；
- 不因为“画面要丰富”就改变人物实际去向、剧情事实或时代地理。

---

## 输入优先级

按以下顺序读取；存在冲突时高优先级覆盖低优先级：

1. 用户明确要求；
2. 当前集正式剧本 / 分场大纲；
3. 已确认连续性世界状态与 handoff；
4. `episodes/episode_XXX.json`；
5. 系列 `asset_registry.json` 中已验证 location 资产；
6. `format_strategy.json` 的画幅、风格和资产策略；
7. 章节摘要/小说原文，仅用于补足来源，不得推翻已确认剧本。

不得用旧分镜或旧提示词反向覆盖当前正式剧本。

---

## 标准输入

AUTO 模式至少需要：

- 当前集 `episode_project_id`；
- 当前制作范围的完整剧本或 scene breakdown；
- `script/scene_index.json`，包含完整 scene_id、顺序、时长和 movement_required；
- 若存在系列项目：`asset_registry.json`；
- 若存在连续性结果：地点/环境状态 handoff。

推荐同时读取：

```text
episodes/episode_XXX.json
continuity/continuity_handoff.json
asset_registry.json
plan/format_strategy.json
```

若没有 `scene_id`，先在 Stage 10 按剧本顺序生成 `SC01`、`SC02`……并写入 `script/scene_index.json`；Planner 不得从自己的输出反推 Scene 总数。

---

# 一、地点层级规范

## 1. Location｜地点母体

代表叙事上稳定的地理地点，例如：

```text
林家
青石集市
县衙
后山
同福客栈
```

同一地点跨集必须尽量复用稳定 `location_id`。

示例：

```text
location_id = LOC-LIN-HOME
canonical_name = 林家
```

Location 定义的是“这是哪里”，不是某一个具体镜头。

---

## 2. Sub-location｜子场景

代表同一 Location 内明显不同、可独立建立空间身份的区域，例如：

```text
林家
├── 堂屋
├── 卧室
├── 灶房
├── 院子
└── 院门外
```

示例：

```text
sub_location_id = SUBLOC-LIN-HOME-LIVINGROOM
```

满足以下任一条件时应拆成新的 Sub-location：

- 建筑/空间边界明确不同；
- 人物进入另一房间、院落、楼层、门外、街段；
- 背景主体构成发生明显变化，单纯换景别不足以表达；
- 后续会多次复用，值得建立稳定环境身份；
- 当前长场景视觉单调，剧本允许在同一地点内合理切换空间区域。

不得仅因为镜头从中景变特写就创建新 Sub-location。

---

## 3. Variant｜环境状态版

同一 Sub-location 的时间、天气、占用状态或剧情性变化达到视觉显著程度时，创建状态版。

示例：

```text
AST-LOC-LIN-HOME-LIVINGROOM-DAY
AST-LOC-LIN-HOME-LIVINGROOM-NIGHT
AST-LOC-LIN-HOME-LIVINGROOM-AFTER-FIRE
```

可形成 Variant 的变化包括：

- 日 / 夜 / 黎明 / 黄昏造成主照明逻辑明显变化；
- 晴 / 暴雨 / 大雪 / 大雾等显著环境变化；
- 火灾后、战斗后、被洗劫后、节庆布置等剧情性状态变化；
- 人群密度或营业状态改变且对故事表达重要。

不应因细微曝光差、普通云量、轻微杂物变化而创建新资产。

---

# 二、ID 与资产身份规则

默认只使用 ASCII 大写字母、数字与连字符，便于现有脚本和 n8n 传递。

推荐：

```text
LOC-<PLACE>
SUBLOC-<PLACE>-<ZONE>
AST-LOC-<PLACE>-<ZONE>-<STATE>
```

例如：

```text
LOC-LIN-HOME
SUBLOC-LIN-HOME-COURTYARD
AST-LOC-LIN-HOME-COURTYARD-DAY
```

若项目已有稳定 ID，必须沿用，不得为了“更漂亮”重命名。

每个 Location / Sub-location 必须有稳定的 `identity_fingerprint`。它描述不可随镜头漂移的环境身份，例如：

```text
layout + architecture + era + landmark + material + dominant_palette
```

状态版必须继承同一基础空间身份，不能把“夜晚版本”生成成另一栋建筑。

---

# 三、场次识别

对当前制作范围的剧本逐场读取，必须提取：

```text
scene_id
source_scene_label
scene_order
narrative_location_text
location_id
sub_location_id
time_of_day
weather
environment_state
characters
story_function
expected_duration_seconds（若已有）
```

如果剧本头写：

```text
SC03 外景·青石集市·日
```

且行动实际发生在盐铺前，则应规范化为：

```text
Location: 青石集市
Sub-location: 盐铺前/盐摊区域
Variant: Day
```

禁止把完整 scene header 原样当作新的 Location 名称，避免出现：

```text
“青石集市日景”
“青石集市下午”
“青石集市三人对话”
```

这些都不是新的地点身份。

---

# 四、复用决策

每个 Scene 必须先做复用匹配，再决定新增资产。

匹配顺序：

1. 完全相同 `location_asset_id` 已注册且校验通过 → `reuse_exact`；
2. 同 `sub_location_id` 且状态兼容 → `reuse_compatible`；
3. 同 Location 但缺该 Sub-location → `generate_new_sublocation`；
4. 同 Sub-location 但状态差异显著 → `generate_state_variant`；
5. 全新地点 → `generate_new_location`。

禁止因为已有“林家堂屋”就把“林家庭院”错误复用为同一张图。

禁止因为已有“集市白天”就在剧情明确夜间时强行复用白天图。

同一场景图可绑定多个 Scene，只要它们的空间与环境状态确实兼容。

---

# 五、视觉多样性策略

本技能的目标不是“每场都换背景”，而是 **剧情正确 + 视觉不过度重复 + 资产成本可控**。

## 默认原则

- 地点真实变化：必须切换场景资产。
- 同一地点进入不同房间/区域：优先切换对应 Sub-location。
- 同一房间的连续对话：允许复用，不为凑数量强制生成新图。
- 长时间停留在同一空间且视觉疲劳：只有在剧情/空间允许时，规划同 Location 的合理 Sub-location 或环境建立图。
- 不允许通过无依据“瞬移”到新地点来制造变化。

## 默认软阈值

当存在可靠时长数据时：

- `domestic_vertical_manga`：同一 `location_asset_id` 连续使用超过 **24 秒**触发视觉多样性检查；超过 **35 秒**是硬失败，必须先拆分为真实子空间/路线锚点后再验证。
- `cinematic_horizontal`：超过 **35 秒**触发检查；超过 **50 秒**必须给出理由或拆分方案。
- 用户/项目配置可覆盖阈值。

软阈值允许通过 `single_location_justification` 解释；硬阈值不允许用文字理由覆盖。密室审讯、病房对话等固定空间应规划同一空间内真实存在的方向/子区资产，而不是伪造新地点。

详细规则见 `references/SCENE_VARIETY_POLICY.md`。

---

# 六、主场景资产绑定

每一个 Scene 必须写：

```text
primary_location_asset_id
```

它是后续视频生成的背景权威来源。

示例：

```json
{
  "scene_id": "SC04",
  "location_id": "LOC-MARKET",
  "sub_location_id": "SUBLOC-MARKET-ENTRANCE",
  "primary_location_asset_id": "AST-LOC-MARKET-ENTRANCE-DAY"
}
```

一个 Scene 仍只有一个 `primary_location_asset_id`，但可以声明 `allowed_location_asset_ids[]`。当人物在 Scene 内连续移动时，必须再声明有序 `route_anchors[]`，每个锚点只绑定一个环境资产，并记录 `predecessor_environment_asset_id`。

移动场次至少包含 departure 与 arrival 两个不同环境资产；预计时长超过 12 秒时默认至少 3 个锚点。可用角色只有 `departure/path/turn/reveal/arrival`。

如果同一剧本场次内部发生叙事硬切或时空跳跃，必须先拆为多个 Scene；连续步行、转弯、揭示和抵达则保留为同一 Scene 的路线锚点。不得使用：

```text
SC04 → [AST-LOC-A, AST-LOC-B, AST-LOC-C]
```

来掩盖 scene 划分错误。

可选 `supporting_location_asset_ids` 仅用于：

- 窗外远景；
- 门外可见区域；
- 建立镜头；
- 极少量空间关系辅助。

它不能替代主绑定。

---

# 七、输出文件

AUTO 模式至少生成四个文件：

```text
assets/scene_asset_plan.json
assets/location_asset_requirements.json
gates/scene_asset_coverage_gate.json
handoffs/scene_asset_handoff.json
```

字段契约见 `references/SCENE_ASSET_SCHEMA.md`。

## 1. scene_asset_plan.json

权威场景规划表。记录全部 Location、Sub-location、资产和 Scene 绑定。

## 2. location_asset_requirements.json

只包含需要交给静态图片提示词 Agent 的 **location 类资产需求**。

已复用资产不得再次出现在 `generation_requirements` 中。

## 3. scene_asset_coverage_gate.json

记录确定性覆盖检查与 AI 视觉审核结果。

## 4. scene_asset_handoff.json

提供给 image prompt、shotlist、video dispatcher 的简化权威映射。

---

# 八、给 Image Prompt Builder 的交接

本技能决定“哪些场景图必须生成”；Image Prompt Builder 只负责“如何把这些场景图写成高质量图片提示词”。

因此下游不得重新执行：

> 从完整剧本挑少量最值得生成的静态图。

对本技能输出的 `location_asset_requirements.json`，必须逐条生成，不得漏项、合并或自行删除。

每个 generation requirement 至少给下游：

```text
asset_id
category = location
name
location_id
sub_location_id
variant
identity_fingerprint
scene_ids
visual_identity
state_requirements
composition_requirements
continuity_constraints
```

随后 Image Prompt Builder 把它们转换成 n8n Asset Job 的：

```text
prompt_zh
prompt_en
metadata.scene_ids
```

---

# 九、给 Shotlist Builder 的交接

Shotlist 不再自己猜背景。

每个 shot 继承所属 Scene 的：

```text
scene_id
location_id
sub_location_id
primary_location_asset_id
allowed_location_asset_ids
route_anchor_id（有路线时）
```

shot 的 `location_asset_id` 必须是该 Scene 的 allowed asset；有路线时还必须与 `route_anchor_id` 精确对应，不能任意换图。

如果 shotlist 发现剧情实际地点与 `scene_asset_handoff.json` 冲突，应返回上游修复，不得静默改绑。

---

# 十、给 Video Dispatcher 的交接

每个视频 clip 必须满足：

```text
clip.scene_id
→ scene_asset_handoff.scene_bindings[scene_id]
→ primary_location_asset_id
→ reference_asset_ids 中必须包含该场景资产或由该场景资产生成的已批准 scene keyframe
```

若缺少对应背景引用，视频任务 Gate 必须失败。

推荐后续把 VIDEO_JOB_SCHEMA 扩展为显式字段：

```json
{
  "scene_id": "SC04",
  "location_id": "LOC-MARKET",
  "location_asset_id": "AST-LOC-MARKET-ENTRANCE-DAY"
}
```

详细交接见 `references/INTEGRATION_HANDOFF.md`。

---

# 十一、Scene Asset Coverage Gate

在进入图片提示词或 n8n 生图前必须通过。

## 硬失败

任一情况直接 `passed = false`：

- 当前范围存在 Scene 未进入规划；
- 未提供 `script/scene_index.json` 却声称 AUTO Gate 已通过；
- Scene 缺少 `location_id`；
- Scene 缺少 `sub_location_id`；
- Scene 缺少 `primary_location_asset_id`；
- 同一 Scene 出现多个主场景资产；
- `primary_location_asset_id` 不存在于复用资产或待生成资产集合；
- generation requirement 重复 asset_id；
- 标记为 reuse 的资产未出现在已验证注册表；
- 同 asset_id 对应多个不兼容的空间身份；
- 移动场次缺少 departure/arrival、锚点不足或全部锚点仍使用同一环境资产；
- 场景状态明确冲突，例如“夜间剧情”绑定纯日间环境资产且没有兼容说明。

## 必须达到

```text
scene_coverage_ratio = 1.0
primary_binding_ratio = 1.0
authoritative_scene_index_used = true
movement_scene_count = resolved_movement_scene_count
unresolved_scene_count = 0
```

## 软审核

AI 审核还要检查：

- 视觉是否长期重复；
- 是否出现无剧情依据的过度换景；
- 同一地点是否被错误拆成大量重复资产；
- 资产数量是否与短剧成本相称；
- 关键地点是否缺少稳定空间身份；
- 跨集复用是否充分。

AUTO 模式最多自动修订两次。两次后仍存在硬失败则停止流程，不允许进入 n8n。

---

# 十二、推荐自动工作流

```text
剧本完成
  ↓
连续性分析
  ↓
DeepWhite Scene Asset Planner
  ├─ 场次枚举
  ├─ Location 规范化
  ├─ Sub-location 规划
  ├─ Registry 复用匹配
  ├─ 新场景资产需求
  ├─ Scene → Asset 绑定
  └─ Coverage / Variety Gate
  ↓
location_asset_requirements.json
  ↓
DeepWhite Image Prompt Builder
  ↓
Asset Job
  ↓
n8n 生图
  ↓
图片审核 / actual_asset_manifest
  ↓
Shotlist Builder
  ↓
Video Prompt / Dispatcher
```

---

# 十三、AUTO_GATE_MODE 行为

用户要求全自动制作时：

1. 不询问“要生成几个场景”。
2. 读取完整当前集剧本，不只看摘要。
3. 以 `script/scene_index.json` 为权威分母枚举全部 Scene。
4. 先尝试 Registry 复用。
5. 为缺失空间生成 requirement。
6. 计算覆盖率与背景连续使用情况。
7. 运行一次确定性验证和一次独立 AI 视觉审核。
8. 如果可修复，最多自动修订两次。
9. Gate 通过后写 handoff。
10. 继续下游，不重复询问人工确认。

只有以下情况暂停：

- 剧本本身无法判断人物究竟在哪；
- 同一 Scene 内存在无法消解的地点冲突；
- 必须复用的注册资产损坏/缺失；
- 两次修订后仍无法达到 100% 场景覆盖。

---

# 十四、MANUAL_GATE_MODE 行为

人工模式下输出：

1. 场次 → 地点 → 子场景 → 资产表；
2. 将复用资产和新增资产分开；
3. 标记视觉多样性风险；
4. 等待用户 `确认场景资产规划` 后再交给图片提示词技能。

用户若调整某个 Scene 的地点，只失效受影响 Scene 及共享资产绑定，不必重做整集。

---

# 十五、禁止行为

- 不得只为整集生成一张“万能背景”并让所有 Scene 复用。
- 不得把“地点名称相同”误认为“子空间相同”。
- 不得在剧情没有地点变化时随机发明城市、街道、房间。
- 不得把人物定妆图当场景资产。
- 不得让图片提示词 Agent 再自行决定删掉场景需求。
- 不得让 shotlist/video prompt Agent 覆盖本技能的 scene → location asset 权威映射。
- 不得把时间/天气小差异无限膨胀成大量资产。
- 不得为了视觉丰富牺牲连续性与空间逻辑。

---

# 十六、完成条件

只有全部满足才算本技能完成：

```text
[ ] 当前制作范围 Scene 100% 枚举
[ ] Coverage 分母来自 script/scene_index.json
[ ] 每个 Scene 有 location_id
[ ] 每个 Scene 有 sub_location_id
[ ] 每个 Scene 有唯一 primary_location_asset_id
[ ] 每个 primary asset 可由 reuse 或 generation requirement 解析
[ ] 复用资产未重复进入 generation requirements
[ ] 硬切/时空跳跃已拆 Scene，连续移动已建立路线锚点
[ ] 时间/天气/剧情状态兼容
[ ] 视觉多样性审核有结论
[ ] scene_asset_coverage_gate.passed = true
[ ] scene_asset_handoff.json 已生成
```

通过后，本技能的 `scene_asset_handoff.json` 是后续场景绑定的唯一权威来源。

---

## 资源

- `references/SCENE_ASSET_SCHEMA.md`：完整 JSON 数据契约。
- `references/LOCATION_TAXONOMY.md`：Location / Sub-location / Variant 拆分准则。
- `references/SCENE_VARIETY_POLICY.md`：视觉多样性与资产成本平衡规则。
- `references/INTEGRATION_HANDOFF.md`：与 Image Prompt、n8n、Shotlist、Video Dispatcher 的交接规范。
- `templates/scene-asset-plan.example.json`：完整示例。
- `templates/scene-index.example.json`：权威 Scene 清单示例。
- `templates/scene-asset-handoff.example.json`：多路线锚点 Handoff 示例。
- `scripts/validate_scene_asset_plan.py`：确定性 Coverage Gate 验证器。
