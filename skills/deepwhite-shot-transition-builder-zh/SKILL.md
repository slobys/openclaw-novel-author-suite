---
name: deepwhite-shot-transition-builder-zh
description: 为相邻镜头、相邻视频片段或相邻图片提示词生成中文镜头衔接设计与 Transition Bridge。Use when the user asks to connect shots, smooth transitions, bridge two AI video clips, preserve first/last frame continuity, create action overlap, camera-motion continuity, eyeline match, match cut, motivated cut, audio bridge, or repair shots that feel disconnected. Requires either a confirmed continuity world-state ledger or enough source material to reconstruct one. Enforce pair selection, boundary-frame extraction, transition-method confirmation, and delivery of copy-ready transition blocks for downstream video prompts. Chinese output only.
---

# DeepWhite Shot Transition Builder ZH v1.0

作者：DeepWhite

把“镜头A结束”和“镜头B开始”之间缺失的动作、构图、摄影机、视线、环境和声音连续关系补出来。目标不是添加炫技转场，而是让两个镜头看起来发生在同一时空、同一动作链中。

## 最高规则

- 只用简体中文输出。
- 优先使用动作连续、视线连续、构图连续和声音连续；不默认使用花哨特效转场。
- 镜头B第一帧必须继承镜头A最后一帧的世界状态。
- 每个衔接只允许明确列出的变化，其余状态锁定。
- 不改写剧情，不偷偷增加人物、道具或新动作结果。
- 不把“自然衔接”当作描述，必须写出具体动作桥。
- 转场类型必须由叙事需求决定，而非随机套模板。
- 若缺少连续性账本，先调用或执行简化连续性分析，不得直接猜。

## Hard Gates

### AUTO_PRODUCTION_MODE

当本技能由 `drama-producer` 的 `scene_bound_auto_v1.2` 合同调用，且以下证据均存在时，使用自动模式：

- `handoffs/scene_asset_handoff.json.gate_passed == true`；
- `gates/shot_scene_binding_gate.json.passed == true`；
- 最终 shotlist、timing plan 与 video prompt manifest 已落盘。

自动模式下不把下面三个确认 Gate 转交用户。先识别真正需要桥接的镜头对；不需要桥接的边界记录 `not_required`，不得为了形式完整给每对镜头强加 Transition。需要桥接时生成 `transition/transition_plan.md` 和 `gates/transition_gate.json`，由证据化 Reviewer 检查动作、视线、声音与边界状态，最多修订两轮。

自动模式仍必须遵守：

- 不得改变 `scene_id`、`location_id`、`sub_location_id`、`location_asset_id`；
- 明确地点变化时只设计有动机的切换，不把两个 Scene 合并成一个生成 clip；
- 修改视频提示词后重新运行 Shot Scene Binding Gate；
- 两轮后仍有 Critical 问题时暂停，不得伪造 Gate 通过。

### 1. Shot-Pair Gate
先列出要处理的镜头对：A→B、B→C。若用户已提供完整分镜，可批量列出。

```text
【待处理镜头对】
1. 镜头01 → 镜头02
2. 镜头02 → 镜头03

请回复“确认镜头对”，或告诉我要增删哪些衔接。
```

输出后停止。

### 2. Boundary Frame Gate
对每个镜头对，提取：

- A镜最后一帧：人物位置、姿态、动作阶段、视线、手部、道具、摄影机、构图、光线、声音。
- B镜第一帧：原始要求。
- 两者冲突：无法同时成立的部分。
- 必须补齐的中间动作。

结束时询问：

```text
边界帧理解是否正确？请回复“确认边界帧”，或逐项修改。
```

输出后停止。

### 3. Transition Method Gate
为每个镜头对推荐一种主衔接方式，并说明原因。用户确认后才写最终桥接提示词。

可用方法见 `references/TRANSITION_TYPES.md`。

```text
请回复“确认衔接方式”，或指定要改成动作接、视线接、声音桥、匹配剪辑等方式。
```

输出后停止。

## 工作流

### Phase 1 — 读取上游材料

优先读取：
1. 已确认的连续性继承块。
2. 分镜表中的画面动作概述、构图、机位、动作、音效。
3. 图片提示词或视频提示词。
4. 原剧本动作。

### Phase 2 — 提取边界状态

使用 `references/BOUNDARY_FRAME_SCHEMA.md`。必须把“动作进行到哪一步”写清，例如：

- 错误：他正在抬手。
- 正确：右肘已抬至胸口高度，右手距离门把约8厘米，手指尚未接触。

### Phase 3 — 选择衔接机制

按优先级选择：

1. 同一动作的动作重叠。
2. 视线与视线对象匹配。
3. 屏幕方向和运动方向匹配。
4. 构图形状、色块或物体位置匹配。
5. 声音先入或声音延续。
6. 有叙事动机的遮挡切、甩镜、焦点转移、光闪或环境物切换。

除非用户明确要求，不用无动机溶解、粒子散开、旋转缩放等模板化转场。

### Phase 4 — 设计动作桥

每个镜头对必须包含：

- `A镜尾部保留动作`：剪切前保留多少动作。
- `切点`：在哪个可见事件发生时切。
- `B镜开头重复量`：重复同一动作的最后 10%-30%，避免跳动作。
- `摄影机接续`：景别、角度、运动速度、方向如何接。
- `构图接续`：主体在画面中的区域、大小、视线落点如何接。
- `状态锁`：不能变化的服装、伤痕、道具、光线和空间。
- `声音桥`：声音是提前进入、跨切延续还是在切点结束。
- `镜尾交接`：B镜结束后交给下一镜的状态。

### Phase 5 — 失败风险审计

使用 `references/TRANSITION_FAILURES.md`，检查：

- 动作跳帧或重复过多。
- 人物换边、朝向翻转、持物换手。
- 镜头运动方向相撞。
- 景别变化没有视觉锚点。
- B镜第一帧重新摆姿势。
- 声音突断或环境声重启。
- 光线、天气、烟雾、粒子状态重置。

### Phase 6 — 输出下游桥接块

使用 `templates/TRANSITION_BLOCK_TEMPLATE.md`。可直接插入视频提示词中，但不替代完整视频提示词。

## 默认输出格式

```markdown
# 镜头衔接设计｜镜头{A} → 镜头{B}

## 1. 边界帧
**A镜最后一帧：** ...
**B镜第一帧：** ...

## 2. 主衔接方式
...

## 3. 动作与切点
...

## 4. 摄影机与构图接续
...

## 5. 状态锁与禁止项
...

## 6. 声音桥
...

## 7. 可复制 Transition Bridge
```text
...
```
```

## Transition 写作规则

- 第一行必须写：`接续上一镜头最后一帧，不重新建立人物姿势。`
- 写清第一帧的身体、手部、视线、道具接触点。
- 写清动作从哪个百分比或动作阶段继续。
- 写清切点的视觉触发物。
- 写清摄影机速度与方向是否延续、减速或反向；反向必须有动机。
- 写清 B 镜开头保留多少动作重叠。
- 写清环境声与关键音效如何跨切。
- 结尾必须写 `⚠️禁止重置` 列表。

## 批量模式

多个镜头连续处理时，先生成 `衔接总览表`：

| 镜头对 | 主方法 | 切点 | 动作重叠 | 声音桥 | 风险 |

然后逐对输出 Transition Bridge。每一对都必须读取上一对的镜尾状态，不能相互独立生成。

## Avoid

- 不写“镜头自然过渡到下一镜”。
- 不用同一个转场套路覆盖所有镜头。
- 不为了顺滑而增加剧本没有的复杂动作。
- 不让 B 镜从完成姿势重新开始同一动作。
- 不在切点前后同时改变人物位置、机位、光线和道具状态。
- 不把连续动作切成两个互不相关的表演。
- 不默认添加 BGM。

## File Map

- `references/BOUNDARY_FRAME_SCHEMA.md` — 首尾帧提取规范
- `references/TRANSITION_TYPES.md` — 衔接方法目录与适用条件
- `references/TRANSITION_FAILURES.md` — 常见失败与修复方式
- `templates/TRANSITION_BLOCK_TEMPLATE.md` — 可复制镜头衔接块
