# AUTO_MACHINE_MODE 输出契约

本契约只负责把已确认剧本事实落成机器状态，不负责视觉资产设计。

## world/characters.json

顶层字段：`schema_version`、`project_id`、`characters[]`。每个角色至少包含：

- `character_id`：稳定 ASCII ID；
- `name`；
- `identity_fingerprint`：不可因镜头变化而改变的身份事实；
- `current_state`：服装、伤痕、污渍、持物、位置等当前状态对象。

## world/locations.json

顶层字段：`schema_version`、`project_id`、`locations[]`。每个地点至少包含 `location_id`、`name` 和 `current_state`。这里只记录真实空间事实；不得生成图片资产 ID。

## world/props.json

顶层字段：`schema_version`、`project_id`、`props[]`。每个道具至少包含 `prop_id`、`name` 和 `current_state`。

## continuity/continuity_handoff.json

顶层字段：`schema_version`、`project_id`、`source_scene_index`、`scenes[]`。每个 Scene 必须包含：

- `scene_id`；
- `character_ids[]`、`location_id`、`prop_ids[]`；
- `state_before`、`state_changes`、`state_after`；
- `evidence[]`：对应剧本动作、台词或场景描述；没有证据的字段写 `unknown`，不能编造。

`scenes[]` 必须与 `script/scene_index.json` 一一对应、无遗漏、无额外 Scene、顺序一致。地点和实体引用必须能在三个 world 文件中解析。
