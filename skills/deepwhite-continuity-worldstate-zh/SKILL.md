---
name: deepwhite-continuity-worldstate-zh
description: 将剧本、场景文本、分场大纲或分镜表转换为中文连续性分析与世界状态账本。Use when the user asks for continuity analysis, scene memory, world state, character/prop/location consistency, shot-to-shot state inheritance, continuity bible, visual consistency rules, or wants to prevent AI-generated shots from changing character identity, costume, wounds, props, lighting, geography, screen direction, or environmental state. Enforce scope confirmation, baseline-state extraction, state-change ledger, spatial-axis confirmation, continuity-risk audit, and a confirmed handoff block for downstream shotlist, image-prompt, and video-prompt skills. Chinese output only.
---

# DeepWhite Continuity World-State Builder ZH v1.0

作者：DeepWhite

把剧本中的“发生了什么”转化为后续分镜和生成提示词可继承的“当前世界到底处于什么状态”。本技能不是重写剧本，也不是直接生成视频提示词；它负责建立连续性底座，防止人物、服装、伤痕、道具、空间、时间、光线和动作在镜头之间无故重置。

## 最高规则

- 只用简体中文输出。
- 不改写剧情，不新增关键事件，不替用户补不存在的设定。
- 所有状态必须能从用户材料推断；推断项标注 `待确认`。
- 区分三类信息：`固定设定`、`当前状态`、`本镜变化`。
- 任何状态变化必须有触发原因；没有触发原因则视为连续性风险。
- 人物左右、前后、朝向、视线、持物手、伤痕侧别必须具体。
- 不直接输出最终图片提示词、视频提示词或 HTML。
- 正式交付前必须经过范围确认、基线确认和连续性确认三个 Gate。

## 启动路由

| 用户材料 | 默认处理 |
|---|---|
| 完整剧本 / 多场戏 | 按场景建立世界状态，并生成跨场继承表 |
| 单场剧本 / 分镜表 | 建立逐镜状态账本 |
| 已有图片提示词 / 视频提示词 | 反向审计状态冲突并修正连续性描述 |
| 用户指出某些画面接不上 | 先做断点诊断，再补世界状态与修复规则 |
| 只有故事梗概 | 只建立可确认的高层连续性，不伪造镜头级细节 |

## AUTO_MACHINE_MODE

当调用参数包含 `mode: AUTO_MACHINE_MODE` 时，本模式优先于下面三个交互 Gate。它用于已确认单集剧本的自动生产，不向用户询问“确认范围/基线/连续性”，而是一次写完并验证以下机器文件：

```text
world/characters.json
world/locations.json
world/props.json
continuity/continuity_handoff.json
```

必须读取 `script/scene_index.json`，并把其中全部 `scene_id` 作为覆盖分母。输出要求见 `references/AUTO_MACHINE_OUTPUT.md`，结构示例见 `templates/world-state-bundle.example.json`。

完成后运行：

```bash
python3 scripts/validate_world_state_bundle.py \
  --project-root . \
  --scene-index script/scene_index.json \
  --out gates/world_state_bundle_gate.json
```

只有 Gate 满足以下条件才可交给 Scene Asset Planner：

- `passed == true`；
- `scene_coverage_ratio == 1.0`；
- `zero_unknown_references == true`；
- 三类实体 ID 唯一；
- 每个 Scene 的开场状态、变化和镜尾状态均为对象；
- 所有状态都有剧本证据或明确标记为 `unknown`，不得用猜测补满。

本模式仍不得规划图片角度、生成 Prompt 或给 Scene 绑定 `location_asset_id`；这些属于 Scene Asset Planner 与 Scene Pack。

## Hard Gates

### 1. Scope Confirmation Gate
先确认处理范围：场景编号、镜头编号或文本起止。若用户已明确指定范围，直接复述范围并继续；若材料很长且范围不明确，只问一个窄问题。

输出：

```text
【连续性分析范围】
场景：...
镜头：...
材料来源：剧本 / 分镜 / 提示词 / 混合

请回复“确认范围”，或告诉我要增删哪些部分。
```

输出后停止，不进入基线分析。

### 2. Baseline State Gate
范围确认后，提取场景开始时的基线状态，至少包括：

- 时间与天气
- 场景结构与出入口
- 光源与色温
- 人物身份锚点、服装、发型、伤痕、污渍
- 人物初始位置、朝向、视线、姿态
- 道具位置、归属、完整度、数量、开关状态
- 环境持续活动与持续声音
- 摄影轴线与屏幕方向

所有无法确定的内容放入 `待确认项`，不得自行填满。

结束时询问：

```text
基线状态是否正确？请回复“确认基线”，或逐项修改。
```

输出后停止。

### 3. Continuity Confirmation Gate
基线确认后，生成逐镜状态变化账本、继承锁和风险审计。结束时询问：

```text
连续性账本是否通过？请回复“确认连续性”，或告诉我需要修改的镜头。
```

确认前不得生成下游交接块。

## 工作流

### Phase 1 — 读取与切分

1. 读取全部指定材料。
2. 识别场景边界、镜头边界、动作触发点、时间跳跃和地点变化。
3. 标出所有可能影响后续画面的状态事件：换衣、受伤、流血、拿起、放下、开门、关灯、下雨、物品破损、人员进出、镜头越轴等。

### Phase 2 — 建立基线

使用 `references/STATE_SCHEMA.md`。固定设定与当前状态必须分开：

- 固定设定：角色不会因镜头变化而改变的身份特征。
- 当前状态：此刻可变化但必须继承的状态。
- 未知项：材料没有提供，不能编造。

### Phase 3 — 逐镜状态账本

每个镜头记录：

1. `继承自上一镜头`：开场必须保持的状态。
2. `本镜唯一变化`：本镜发生的新增变化。
3. `镜尾状态`：交给下一镜头的精确状态。
4. `禁止重置`：模型最容易错误恢复的内容。
5. `连续性证据`：对应剧本动作或台词。

### Phase 4 — 空间与轴线审计

使用 `references/AXIS_AND_SCREEN_DIRECTION.md`。重点检查：

- 人物是否在无动作依据时换边。
- 角色面对方向是否与对话对象一致。
- 进入画面和离开画面的方向是否相互匹配。
- 门、窗、桌、床、车辆等固定物是否漂移。
- 持物手、伤痕侧别、光源方向是否翻转。
- 切反打是否守住 180 度轴线；若越轴，必须有过轴镜头或明确动机。

### Phase 5 — 风险审计

使用 `references/CONTINUITY_RISKS.md`。风险等级：

- `⚠️⚠️⚠️ 严重`：会让角色、场景或动作看起来像另一个时空。
- `⚠️ 高`：会造成明显跳切、左右颠倒或道具复原。
- `注意`：不一定错误，但需要下游提示词明确。

### Phase 6 — 下游交接

用户确认连续性后，输出可直接交给分镜、图片提示词和视频提示词技能的 `连续性继承块`，使用 `templates/HANDOFF_TEMPLATE.md`。

## 默认输出格式

```markdown
# 连续性分析｜场景 {N}

## 1. 场景基线状态
...

## 2. 固定连续性锚点
...

## 3. 逐镜状态变化账本
| 镜头 | 继承状态 | 本镜变化 | 镜尾状态 | 禁止重置 | 证据 |

## 4. 空间与轴线锁
...

## 5. 连续性风险
...

## 6. 待确认项
...
```

## 输出精度规则

- 位置：写东/西/南/北或画面左/中/右，并说明参照物。
- 朝向：写面朝哪个角色、物体或方位。
- 手部：明确左手、右手、双手、空手。
- 道具：明确谁持有、放在哪里、是否开启、破损程度、剩余数量。
- 伤痕：明确身体部位和左右侧，记录出血、干涸、擦拭后的变化。
- 服装：记录脱下、卷袖、湿透、沾灰、破损等累计状态。
- 光线：记录主光方向、强弱、色温、闪烁与熄灭。
- 情绪：只记录可见表演状态，不写内心解释。
- 动作：镜尾必须写到可以成为下一镜头第一帧的程度。

## Avoid

- 不把每个镜头写成独立新场景。
- 不使用“保持一致”代替具体状态。
- 不让物品在没有动作的情况下自动回到原位。
- 不让伤痕、湿衣、灰尘、血迹在切镜后消失。
- 不让人物在无走位动作时交换左右位置。
- 不把摄影机变化误写成人物位置变化。
- 不把推测伪装成确定事实。

## File Map

- `references/STATE_SCHEMA.md` — 世界状态字段和继承规则
- `references/AXIS_AND_SCREEN_DIRECTION.md` — 空间轴线与屏幕方向审计
- `references/CONTINUITY_RISKS.md` — 常见连续性断点与风险等级
- `templates/HANDOFF_TEMPLATE.md` — 下游技能连续性继承块
