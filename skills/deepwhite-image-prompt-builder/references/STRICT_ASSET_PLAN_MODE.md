# STRICT_ASSET_PLAN_MODE

## Purpose

该模式用于把 Scene Asset Planner 已经确定的静态场景资产需求逐条转换为生成提示词。

它解决的是：

```text
上游已经要求生成 6 张场景图
↓
Image Prompt Builder 不能再自行“精选成 2 张”
```

## Trigger

任一成立：

- `assets/location_asset_requirements.json` 存在；
- 输入对象包含 `generation_requirements`；
- source skill 为 `deepwhite-scene-asset-planner`；
- 用户明确要求严格逐条资产生产。

## One-to-one invariant

设：

```text
R = generation_requirements 的 asset_id 集合
O = location_asset_prompt_manifest.assets 的 asset_id 集合
```

必须：

```text
R == O
```

且每个 ID 只能出现一次。

## Preserved fields

场景资产至少保留：

```text
asset_id
category
name
scene_ids
location_id
sub_location_id
identity_fingerprint
source_plan_id
```

## Prompt responsibility

Builder 可以决定：

- 如何把结构写得更清楚；
- 如何表达光线、构图、材质与空间；
- 中英文表达质量；
- 在不违反上游状态时增强可生成性。

Builder 不可以决定：

- 哪个场景不生成；
- 两个不同 Sub-location 合成一个；
- 改 asset_id；
- 改 location/sub-location 身份；
- 把白天改夜晚；
- 把复用资产重新生成；
- 为了视觉丰富擅自新增剧情地点。

## Location prompt emphasis

场景资产是后续视频的环境锚点。Prompt 应优先确保：

1. 地点身份可识别；
2. 空间结构清晰；
3. 主要 landmark 位置稳定；
4. 材质、时代、建筑语言稳定；
5. 状态变化正确；
6. 保留人物活动区域；
7. 后续可重复引用。

不要把场景资产写成“剧情海报”。
