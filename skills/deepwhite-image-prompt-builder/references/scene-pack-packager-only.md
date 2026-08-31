<!-- BEGIN DEEPWHITE_SCENE_PACK_PACKAGER_ONLY_V1 -->

# Scene Pack Integration：PACKAGER_ONLY（最高优先级）

当调用参数包含：

```yaml
mode: PACKAGER_ONLY
```

本技能只执行格式打包，不再承担视觉设计。

输入权威文件：

```text
assets/continuity/
assets/expanded_asset_list.base.json 或 assets/expanded_asset_list.shot.json
assets/reference_plan.*.json
assets/reference_registry.json（如有）
```

强制规则：

1. `prompt_zh` 已存在时逐字复制，不得重写、精炼、翻译后回译或调序；
2. 必须保留 `PORTABLE HARD LOCK` 及四锁完整原文；
3. 输入和输出 `lock_id`、`lock_hash` 必须一致；
4. 发现任何锁变化，返回 `LOCK_MUTATION_DETECTED`；
5. 逻辑父实体不直接形成 n8n 图片任务；只打包展开后的子资产；
6. 一个子资产对应一个 Prompt、一个文件名、一个 `assets[]` 对象；
7. 每个对象原样保留 `depends_on`、`reference_inputs`、`generation_stage`、`anchor_roles`；
8. 画幅优先读取子资产 `aspect_ratio`，不得统一覆盖为项目画幅；
9. 输出目录：BASE_ASSET 使用 `prompts/base_assets/`，SHOT_ASSET_GAP 使用 `prompts/shot_assets/`；
10. 允许生成英文副本，但不得用英文版本反向改变中文四锁。

asset-job v2 中每个资产至少输出：

```yaml
asset_id:
parent_asset_id:
category:
name:
filename:
prompt_zh:
aspect_ratio:
generation_stage:
lock_id:
lock_hash:
depends_on: []
reference_inputs: []
```

本模式覆盖旧规则中“一个父资产只映射一张设定页”的限制；旧规则仅用于未启用 Scene Pack 的兼容项目。

<!-- END DEEPWHITE_SCENE_PACK_PACKAGER_ONLY_V1 -->
