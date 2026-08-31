

---

# 十三、AI短剧流水线批处理模式 Pipeline Batch（v3.3.0）

本节用于与 `drama-producer`、`deepwhite-image-prompt-builder`、分镜技能、转场技能及 n8n 自动生图联动。其规则优先于本技能的交互式“下一张”规则。

## 13.1 调用模式

自动生产中必须使用：

```yaml
invocation_mode: PIPELINE_BATCH
pass: BASE_ASSET | SHOT_ASSET_GAP
```

在 `PIPELINE_BATCH` 下：

- 禁止输出“请确认”“是否继续”“回复下一张”；
- 不等待用户逐项确认；
- 必须一次性写完本阶段全部机器可读文件；
- 仍必须为每个最终图片子资产生成完整 `PORTABLE HARD LOCK`；
- 任何四锁缺失均为失败关闭，返回 `HARD_LOCK_VALIDATION_FAILED`。

## 13.2 BASE_ASSET Pass

输入：

```text
project.json
script/
world/characters.json
world/locations.json
world/props.json
assets/asset_list.json
```

职责：

1. 将逻辑父实体展开为一张图片一个任务的子资产；
2. 为人物、场景、动物、生物、道具建立 Canonical Lock；
3. 生成基础锚点、空间布局、母版、反向验证与关键资产；
4. 生成依赖图和参考图职责计划；
5. 不根据尚未存在的分镜机械生成全部 V/CP/SH 资产。

默认基础资产：

- 人物：`C01` 主身份锚点，核心人物增加 `C06` 脸部锚点；
- 室外场景：`L01`、必要时 `B01`、`M01`、`P01`；
- 室内场景：`F01`、必要时 `E01/B01`、`M01`、`P01`；
- 动物：`A01`；
- 生物：`CR01`；
- 道具：`P01`，复杂道具可增加 `P03`。

输出：

```text
assets/continuity/index.json
assets/continuity/scenes/*.json
assets/continuity/characters/*.json
assets/continuity/animals/*.json
assets/continuity/creatures/*.json
assets/continuity/props/*.json
assets/expanded_asset_list.base.json
assets/asset_dependency_graph.base.json
assets/reference_plan.base.json
```

## 13.3 SHOT_ASSET_GAP Pass

额外输入：

```text
shots/shotlist.md
assets/reference_registry.json
assets/continuity/
assets/expanded_asset_list.base.json
```

职责：

1. 读取分镜实际需要的角度、景别、位置、动作和道具状态；
2. 优先复用已经 `approved` 的基础锚点；
3. 仅补齐真正缺少的 `V/CV/PX/CP/SH` 等子资产；
4. 输出每个目标资产实际需要上传的参考图和角色/场景职责；
5. 不重新设计父实体，不改写已封存四锁。

输出：

```text
assets/shot_asset_requests.json
assets/expanded_asset_list.shot.json
assets/asset_dependency_graph.shot.json
assets/reference_plan.shot.json
```

## 13.4 父实体与子图片资产

`assets/asset_list.json` 继续保存剧本层逻辑父实体，例如：

```text
AST-CH01  主角
AST-LOC01 院落
AST-PR01  牛车
```

n8n 不直接生成父实体。必须先展开为子图片资产，例如：

```text
AST-CH01  -> CH001-ST01-C01-v001
AST-CH01  -> CH001-ST01-C06-v001
AST-LOC01 -> SC001-ST01-L01-v001
AST-LOC01 -> SC001-ST01-M01-v001
AST-LOC01 -> SC001-ST01-V01-v001
AST-PR01  -> PR001-ST01-P01-v001
```

每个子资产只对应一张计划生成的图片和一个唯一文件名。

## 13.5 子资产强制字段

每个 `expanded_asset_list*.json` 中的子资产至少包含：

```yaml
asset_id:
parent_asset_id:
family_id:
style_id:
asset_code:
category:
name:
aspect_ratio:
generation_stage: anchor | derived | shot
lock_id:
lock_hash:
depends_on: []
reference_inputs: []
prompt_zh:
filename:
status: planned
```

`reference_inputs[]` 至少包含：

```yaml
asset_id:
role:
required:
approved_only:
```

允许的典型职责：

```text
spatial_topology
volume_blockout
visual_master
reverse_proof
identity_master
face_master
adjacent_view
character_pose
prop_master
style_reference
```

## 13.6 权威层级和锁变更策略

权威顺序：

```text
script/world_state
  -> deepwhite-scene-pack-builder 的四锁与连续性 Manifest
  -> deepwhite-image-prompt-builder 的 PACKAGER_ONLY 输出
  -> n8n 执行和 reference_registry
```

后续技能不得同义改写、摘要、移动或删除四锁。必须计算并传播 `lock_hash`。

发现输入/输出 `lock_hash` 不一致时返回：

```text
LOCK_MUTATION_DETECTED
```

## 13.7 画幅规则

若子资产没有显式覆盖：

```text
location / scene / storyboard / shot -> 16:9
character / animal / creature / prop -> 9:16
```

最终视频镜头继续使用项目视频画幅，不能因为人物定妆图为 9:16 而改变成片画幅。

## 13.8 reference_registry 使用规则

只有下列状态可以进入参考链：

```text
approved
```

以下状态不得作为参考：

```text
planned
generated
unreviewed
failed
rejected
superseded
```

如果必需参考图缺失，子资产状态必须变为：

```text
blocked_by_dependency
```

不得退化为纯文本偷偷生成。
