---
name: deepwhite-image-prompt-builder
description: Create polished bilingual static-image prompts for DeepWhite projects. Supports ordinary single-image and script key-still workflows, plus a mandatory STRICT_ASSET_PLAN_MODE for upstream asset requirement manifests such as assets/location_asset_requirements.json. In strict mode, convert every generation_requirements item one-to-one into a generation-ready prompt asset while preserving IDs, scene bindings, location hierarchy, identity fingerprints, continuity constraints, and asset count. Never select, merge, omit, rename, or invent planned assets in strict mode. Do not create video prompts, motion timing, audio instructions, or independently redesign upstream asset planning.
---

# DeepWhite Image Prompt Builder V2

本技能负责把**已经确定“要生成什么”的静态资产需求**写成高质量、中英双语、可直接交给 n8n Asset Dispatcher 的图片提示词。

V2 保留原来的普通图片提示词能力，但新增一条最高优先级规则：

> 当上游存在结构化资产需求清单时，本技能不再拥有“挑哪些图值得生成”的决定权。

尤其当检测到 `assets/location_asset_requirements.json` 或等价的 `generation_requirements[]` 时，必须进入 `STRICT_ASSET_PLAN_MODE`。

---

# 一、模式选择

按以下优先级选择模式；高优先级覆盖低优先级。

## MODE A — STRICT_ASSET_PLAN_MODE｜严格资产计划模式

满足任一条件即进入：

- 输入包含 `location_asset_requirements.json`；
- 输入包含结构化 `generation_requirements[]`；
- 上游明确来自 `deepwhite-scene-asset-planner`；
- 用户明确要求“按资产计划逐条生成，不得删减/合并”；
- 工作目录中存在当前制作范围的 `assets/location_asset_requirements.json` 且本任务是场景图片提示词生产。

本模式为自动化短剧流水线的默认场景资产模式。

### 最高优先级硬规则

对 `generation_requirements[]`：

```text
输入 N 条 requirement
→ 必须输出 N 条 asset prompt
```

必须满足：

```text
requirement.asset_id == output.asset_id
requirement.category == output.category
requirement.name == output.name
requirement.scene_ids == output.metadata.scene_ids
requirement.location_id == output.metadata.location_id
requirement.sub_location_id == output.metadata.sub_location_id
requirement.identity_fingerprint == output.metadata.identity_fingerprint
```

禁止：

- 挑“最重要的几张”；
- 把两个 requirement 合成一张图；
- 删除“看起来重复”的 requirement；
- 自己新增未规划的 Location/Sub-location；
- 修改稳定 `asset_id`；
- 把 `reuse_assets[]` 再写成生图任务；
- 为了“画面更好看”改变剧本地点、年代、环境状态或空间身份；
- 用角色资产替代场景资产；
- 输出“万能场景图”覆盖多个本应不同的子场景。

若上游 requirement 本身冲突或缺少关键字段，返回上游修复；不得静默猜测新资产身份。

---

## MODE B — SCRIPT_KEY_STILLS_MODE｜剧本关键静帧模式

仅在**没有结构化资产计划**，且用户直接给剧本/场景，希望生成若干关键静态图提示词时使用。

此模式可以选择：

- 人物亮相；
- 情绪特写；
- 环境建立图；
- 关键道具；
- 海报构图；
- 高潮静帧。

若完整剧本没有指定数量，可选择紧凑的一组关键静帧。

**注意：这一“精选关键图”规则绝不能覆盖 MODE A。**

---

## MODE C — SINGLE_IMAGE_MODE｜单图模式

用户只描述一张图、一个人物、一个场景、一个产品或一个概念时使用。

---

# 二、输入优先级

冲突时按以下优先级处理：

1. 用户当前明确要求；
2. 上游结构化 asset requirement；
3. 场景资产 handoff / continuity handoff；
4. 已确认 series asset registry / identity fingerprint；
5. 当前剧本；
6. 风格规范 / format strategy；
7. 小说原文或旧提示词，仅作补充。

不得让旧提示词覆盖新的资产计划。

---

# 三、STRICT_ASSET_PLAN_MODE 标准输入

优先读取：

```text
assets/location_asset_requirements.json
handoffs/scene_asset_handoff.json
assets/angle_pack_requirements.json        # 存在核心/常驻/单集重要人物或生物时
plan/format_strategy.json                 # 若存在
asset_registry.json                       # 若需要参考已确认世界视觉规范
```

其中 `location_asset_requirements.json` 至少应包含：

```json
{
  "project_id": "...",
  "episode_project_id": "...",
  "source_plan_id": "...",
  "generation_requirements": [],
  "reuse_assets": []
}
```

每条场景 requirement 推荐包含：

```text
asset_id
category = location
name
location_id
sub_location_id
asset_role
base_asset_id
state_version
identity_fingerprint
scene_ids
visual_identity
state_requirements
composition_requirements
continuity_constraints
```

字段契约以 `deepwhite-scene-asset-planner` 输出为权威。

---

# 四、STRICT_ASSET_PLAN_MODE 工作流

## Step 1｜锁定 Requirement 集合

读取 `generation_requirements[]`，记录：

```text
source_requirement_count
required_asset_ids
reuse_asset_ids
```

立即检查：

- `generation_requirements[]` 是否为数组；
- `asset_id` 是否唯一；
- 是否存在与 `reuse_assets[]` 重叠的 asset_id；
- 每条 `category` 是否为当前技能可处理的静态资产类型；
- 对场景资产，`location_id`、`sub_location_id`、`identity_fingerprint` 是否存在。

场景 requirement 不完整时，不得用剧本重新规划地点；返回 Scene Asset Planner 修复。

---

## Step 2｜逐条构建 Prompt，不做筛选

严格按 requirement 原顺序逐条处理。

对于 location 类资产，Prompt 必须由以下信息构建：

```text
[环境身份 Identity]
+
[空间布局 Layout]
+
[核心地标 Landmarks]
+
[时代/建筑/材质 Materials]
+
[时间天气与环境状态 State]
+
[构图用途 Composition]
+
[系列风格 Style]
+
[连续性约束 Continuity]
```

不得把 `scene_ids` 当成需要画在图中的文字。

---

## Step 3｜场景 Prompt 的身份优先原则

场景资产首先是**可复用的环境身份参考图**，不是某个镜头的动作画面。

如果：

```text
composition_requirements.purpose = environment_reference
```

则默认：

- 清楚展示空间布局；
- 让主要建筑、道路、门窗、柜台、摊位、地标的位置关系可读；
- 保留后续人物表演空间；
- 避免让单一角色占据画面主体；
- 不写视频运动；
- 不写时间轴；
- 不把“故事动作”覆盖成环境设定图的主视觉。

如果 requirement 允许背景人群：

```text
character_presence = none_or_nonidentifiable_background_extras
```

可以出现无身份、非主体的背景路人，但不得生成明确主角脸或稳定角色身份。

---

## Step 4｜Identity Fingerprint 不得漂移

`identity_fingerprint` 是环境不可漂移的身份锁。

Prompt 必须把 `visual_identity` 中的稳定元素落实为可见画面：

- architecture；
- layout；
- landmarks；
- materials；
- palette；
- 其他上游锁定的身份要素。

若生成状态版：

```text
base_asset_id != null
或 state_version != null
```

则新的 Prompt 应表达“同一空间的状态变化”，不能重新设计建筑布局。

例如：

```text
白天堂屋 → 夜晚堂屋
```

允许改变照明、窗外亮度、灯火状态；不允许把门从左边变到右边、桌子位置完全重构、建筑风格改变。

---

## Step 5｜State Requirements

把上游状态写成明确可见事实：

```text
time_of_day
weather
environment_state
occupancy_state
```

不要为了“更电影感”擅自改变它们。

例如：

```text
weather = clear
```

不得自行改成暴雨。

```text
environment_state = after_fire
```

必须体现火灾后的可见变化，而不是生成正常状态。

---

## Step 6｜Composition Requirements

优先服从上游：

```text
purpose
preferred_view
keep_center_action_space
character_presence
```

常见映射：

- `wide_establishing` → 广角环境建立构图，空间关系清晰；
- `medium_environment` → 中等范围展示主要活动区；
- `facade_reference` → 以建筑正面和入口关系为重点；
- `interior_reference` → 重点展示室内空间布局；
- `prop_area_reference` → 重点展示柜台/摊位/工作区，但仍保持地点身份。

`keep_center_action_space=true` 时，必须在画面主要表演区保留足够视觉空间，不要被大型装饰物完全占满。

---

## Step 7｜Prompt 结构

### English Prompt

建议结构：

```text
Canonical environment identity and place name.
Visible architecture, spatial layout and landmarks.
Materials and era language.
Time/weather/environment state.
Composition and camera/framing for a reusable environment reference.
Lighting and color philosophy.
Series visual style.
Continuity-preserving identity details.
```

### 中文提示词

中文不是逐字翻译，而是保持完全相同的资产身份与构图意图。

必须优先保证：

```text
环境是谁
空间怎么长
关键物在哪
当前是什么状态
这张图拿来干什么
后续哪些东西不能变
```

---

# 五、普通模式 Prompt 原则

在 MODE B/C 中，继续使用以下基础结构：

```text
[Subject + Action]
+ [Location / Context]
+ [Composition]
+ [Lighting]
+ [Style / Aesthetic]
+ [Camera / Lens]
+ [Color Grading]
```

始终提供 English Prompt + 中文提示词。

静态图片中只描述一个可成立的瞬间，不写：

- 视频时长；
- 时间戳；
- 运镜随时间变化；
- 对白同步；
- 音效/BGM；
- 转场动画。

---

# 六、STRICT 模式标准输出

AUTO 模式必须写出：

```text
assets/location_asset_prompt_manifest.json
assets/angle_pack_manifest.json
gates/location_prompt_coverage_gate.json
gates/angle_pack_gate.json
handoffs/image_prompt_handoff.json
```

字段见 `references/OUTPUT_SCHEMA.md`。

## 1. location_asset_prompt_manifest.json

每个 `generation_requirements[]` 对应且只对应一个 `assets[]` 项。

输出资产字段应兼容现有 `deepwhite-n8n-asset-dispatcher`：

```json
{
  "asset_id": "...",
  "category": "location",
  "name": "...",
  "filename": "<asset_id>.png",
  "prompt_zh": "...",
  "prompt_en": "...",
  "reference_images": [],
  "metadata": {
    "scene_ids": [],
    "location_id": "...",
    "sub_location_id": "...",
    "identity_fingerprint": "...",
    "source_plan_id": "...",
    "continuity_notes": "..."
  }
}
```

不得把 `reuse_assets[]` 写入此 manifest 的 `assets[]`。

---

## 2. location_prompt_coverage_gate.json

必须记录确定性检查：

```text
requirement_count
output_asset_count
coverage_ratio
missing_asset_ids
unexpected_asset_ids
duplicate_output_asset_ids
metadata_mismatch_count
reuse_overlap_count
passed
```

只有以下条件同时成立才能通过：

```text
coverage_ratio = 1.0
missing_asset_ids = []
unexpected_asset_ids = []
duplicate_output_asset_ids = []
metadata_mismatch_count = 0
reuse_overlap_count = 0
```

推荐调用：

```bash
python3 scripts/validate_location_prompt_manifest.py \
  --requirements assets/location_asset_requirements.json \
  --manifest assets/location_asset_prompt_manifest.json \
  --gate-out gates/location_prompt_coverage_gate.json
```

Gate 失败时不得进入 n8n Asset Dispatcher。

## 2.1 独立多视角资产包 Gate

核心、常驻、单集重要角色、宠物和常驻生物必须按 `references/ANGLE_PACK_CONTRACT.md` 输出八个独立 9:16 文件。每个角度是一个独立 `asset_id` 和 `filename`，并共享同一身份参考 SHA、身份指纹、状态 ID 与风格合同 SHA。

标准顺序为：front、front_left_three_quarter、left_profile、rear_left_three_quarter、back、rear_right_three_quarter、right_profile、front_right_three_quarter。

横向多角度设定页只能标记为 `design_sheet`，不得写成 `video_reference`，也不得用一张拼图冒充完整资产包。提交 n8n 前执行：

```bash
python3 scripts/validate_angle_pack.py \
  --manifest assets/angle_pack_manifest.json \
  --job dispatch/asset_jobs/{job_id}.json \
  --out gates/angle_pack_gate.json
```

---

## 3. image_prompt_handoff.json

向 n8n dispatcher 交接：

```text
source_mode = strict_asset_plan
source_plan_id
prompt_manifest_path
coverage_gate_path
asset_count
asset_ids
passed
```

下游不得重新选择场景资产，只负责打包和提交。

---

# 七、与 n8n Asset Dispatcher 的边界

Image Prompt Builder：

```text
决定“怎么画”
```

Scene Asset Planner：

```text
决定“必须画什么”
```

n8n Asset Dispatcher：

```text
决定“怎么把已确认任务提交生成”
```

因此：

- 本技能不发送 Webhook；
- 本技能不改写 n8n secret；
- 本技能不自行指定平台/模型，除非用户明确要求；
- Dispatcher 不得重新改写 prompt；
- Dispatcher 只接收 Gate 已通过的 prompt manifest。

---

# 八、错误处理

## A. Requirement 缺字段

场景 requirement 缺：

```text
asset_id
location_id
sub_location_id
identity_fingerprint
```

→ FAIL，上游修复。

不能自行产生新的地点身份。

## B. Requirement 数量与输出数量不同

→ FAIL。

## C. 同一 asset_id 出现两次

→ FAIL。

## D. generation 与 reuse 重叠

→ FAIL。

## E. Prompt 与 requirement 环境状态冲突

例如 requirement 为夜晚，Prompt 写成正午。

→ AI Review FAIL，重写该 prompt，不改 asset_id。

## F. 风格信息缺失

若结构和身份字段完整但没有系列风格，可使用项目已确认的默认视觉风格；若仍不可得，则写中性、忠实的环境提示词，不得因此删掉资产。

---

# 九、禁止行为

- STRICT 模式不得输出“我选了其中 5 张最重要的场景图”。
- 不得把多个 `scene_ids` 误解成需要多生成几张同 asset_id 图片。
- 不得把同一 requirement 重复提交多次。
- 不得把 `reuse_assets` 复制进 generation manifest。
- 不得发明不存在的角色、建筑、招牌、时代元素。
- 不得用抽象审美词替代空间身份描述。
- 不得让状态版破坏基础地点布局。
- 不得在静态场景资产提示词中写“镜头推进、人物走过、随后转身”等视频语言。
- 不得因为完整剧本很长而在 STRICT 模式自动压缩 asset 数量。
- 不得把角色设定拼图、多面板或一张图内的多个角度作为生产视频参考；每个角度必须独立生成。

---

# 十、完成定义

STRICT_ASSET_PLAN_MODE 只有在以下全部满足时才算完成：

1. 每条 generation requirement 都生成中英文 prompt；
2. 资产 ID 和关键绑定字段全部原样保留；
3. reuse asset 没有重复生成；
4. `location_asset_prompt_manifest.json` 已写出；
5. 确定性 validator 通过；
6. `location_prompt_coverage_gate.json.passed = true`；
7. `image_prompt_handoff.json.passed = true`；
8. 需要多视角包时，`angle_pack_gate.json.passed = true`；
9. 下游可直接交给 n8n Asset Dispatcher。

---

# 十一、推荐 DeepWhite 流水线位置

```text
Screenwriting
↓
Continuity Worldstate
↓
Scene Asset Planner
↓
location_asset_requirements.json
↓
DeepWhite Image Prompt Builder V2
   └─ STRICT_ASSET_PLAN_MODE
↓
location_asset_prompt_manifest.json
↓
Location Prompt Coverage Gate
↓
Independent Angle Pack Gate
↓
N8N Asset Dispatcher
↓
图片生成与资产审核
↓
actual_asset_manifest.json
↓
Shotlist / Video Prompt / Video Dispatcher
```

相关细节：

- `references/STRICT_ASSET_PLAN_MODE.md`
- `references/OUTPUT_SCHEMA.md`
- `templates/location-asset-requirements.example.json` 与 `templates/location-asset-prompt-manifest.example.json`：可直接配对运行 validator 的通过示例
- `scripts/validate_location_prompt_manifest.py`
