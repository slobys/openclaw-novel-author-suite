# Scene Asset Planner 数据契约 v1.1

AUTO production 必须提供 `script/scene_index.json`；Coverage 分母来自 `scene_index.scenes[]`，不得从 `scene_asset_plan.scene_bindings[]` 自己推导。每条 index 至少包含 `scene_id`、`scene_order`、`expected_duration_seconds`、`movement_required` 和可选 `route_requirements`。

每个 Scene 仍保留唯一 `primary_location_asset_id`，并可增加：

```json
{
  "allowed_location_asset_ids": ["AST-DEPARTURE", "AST-PATH", "AST-ARRIVAL"],
  "route_anchors": [
    {"route_anchor_id":"RA-SC02-01","role":"departure","order":1,"location_asset_id":"AST-DEPARTURE","predecessor_environment_asset_id":null},
    {"route_anchor_id":"RA-SC02-02","role":"path","order":2,"location_asset_id":"AST-PATH","predecessor_environment_asset_id":"AST-DEPARTURE"},
    {"route_anchor_id":"RA-SC02-03","role":"arrival","order":3,"location_asset_id":"AST-ARRIVAL","predecessor_environment_asset_id":"AST-PATH"}
  ]
}
```

合法角色为 `departure/path/turn/reveal/arrival`。移动 Scene 至少需要 departure/arrival 和两个不同资产；时长超过 12 秒默认至少三个锚点。

本文件定义四个标准输出：

1. `assets/scene_asset_plan.json`
2. `assets/location_asset_requirements.json`
3. `gates/scene_asset_coverage_gate.json`
4. `handoffs/scene_asset_handoff.json`

所有 ID 只使用字母、数字、下划线和连字符。

---

## 1. scene_asset_plan.json

```json
{
  "schema_version": "1.0",
  "project_id": "DEMO",
  "episode_project_id": "demo_s01e001",
  "plan_id": "demo_s01e001_scene_assets_v001",
  "format_profile": "domestic_vertical_manga",
  "aspect_ratio": "9:16",
  "source": {
    "screenplay": "script/final_screenplay.md",
    "continuity_handoff": "continuity/continuity_handoff.json",
    "asset_registry": "asset_registry.json"
  },
  "policy": {
    "same_background_soft_limit_seconds": 24,
    "same_background_hard_limit_seconds": 35,
    "allow_editorial_sublocation_enrichment": true,
    "require_100_percent_scene_coverage": true
  },
  "locations": [],
  "sub_locations": [],
  "location_assets": [],
  "scene_bindings": [],
  "summary": {}
}
```

### locations[]

```json
{
  "location_id": "LOC-LIN-HOME",
  "canonical_name": "林家",
  "location_type": "residence",
  "narrative_identity": "林满仓一家居住的普通农家院落",
  "identity_fingerprint": "rural-courtyard-north-room-earthwall-timber-v1",
  "source_scene_ids": ["SC01", "SC02"],
  "existing_registry_match": null
}
```

### sub_locations[]

```json
{
  "sub_location_id": "SUBLOC-LIN-HOME-LIVINGROOM",
  "location_id": "LOC-LIN-HOME",
  "canonical_name": "林家堂屋",
  "spatial_role": "indoor_main_room",
  "spatial_identity": "正门内主屋，木桌居中，土墙，右侧通往灶房",
  "identity_fingerprint": "lin-home-livingroom-table-earthwall-right-kitchen-v1",
  "source_scene_ids": ["SC01"]
}
```

### location_assets[]

```json
{
  "asset_id": "AST-LOC-LIN-HOME-LIVINGROOM-DAY",
  "category": "location",
  "name": "林家堂屋·白天",
  "location_id": "LOC-LIN-HOME",
  "sub_location_id": "SUBLOC-LIN-HOME-LIVINGROOM",
  "asset_role": "base",
  "base_asset_id": null,
  "state_version": null,
  "variant": {
    "time_of_day": "day",
    "weather": "clear",
    "environment_state": "normal",
    "occupancy_state": "neutral"
  },
  "identity_fingerprint": "lin-home-livingroom-table-earthwall-right-kitchen-v1",
  "decision": "reuse_exact",
  "registry_status": "verified",
  "scene_ids": ["SC01"],
  "generation_required": false
}
```

状态版示例：

```json
{
  "asset_id": "AST-LOC-LIN-HOME-LIVINGROOM-NIGHT",
  "category": "location",
  "asset_role": "state_version",
  "base_asset_id": "AST-LOC-LIN-HOME-LIVINGROOM-DAY",
  "state_version": "night-v1",
  "variant": {
    "time_of_day": "night",
    "weather": "clear",
    "environment_state": "normal",
    "occupancy_state": "neutral"
  },
  "generation_required": true
}
```

### scene_bindings[]

每个 scene 必须且只能出现一次。

```json
{
  "scene_id": "SC03",
  "source_scene_label": "3. 外景·青石集市·日",
  "scene_order": 3,
  "narrative_location_text": "青石集市盐摊",
  "location_id": "LOC-MARKET",
  "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
  "primary_location_asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
  "supporting_location_asset_ids": [],
  "time_of_day": "day",
  "weather": "clear",
  "environment_state": "busy_market",
  "characters": ["CHAR-LIN-MANCHANG"],
  "story_function": "林满仓发现盐价暴涨",
  "expected_duration_seconds": 18,
  "location_change_from_previous": true,
  "visual_change_type": "hard_location_change",
  "binding_reason": "人物从村口进入集市盐摊，空间身份明确改变",
  "single_location_justification": null
}
```

### summary

```json
{
  "scene_count": 5,
  "location_count": 3,
  "sub_location_count": 5,
  "location_asset_count": 5,
  "reuse_asset_count": 2,
  "generation_asset_count": 3,
  "scene_coverage_ratio": 1.0,
  "primary_binding_ratio": 1.0,
  "longest_same_background_seconds": 24,
  "visual_variety_risk": "low"
}
```

---

## 2. location_asset_requirements.json

这是给 Image Prompt Builder 的输入，而不是最终 n8n Asset Job。

```json
{
  "schema_version": "1.0",
  "project_id": "DEMO",
  "episode_project_id": "demo_s01e001",
  "source_plan_id": "demo_s01e001_scene_assets_v001",
  "generation_requirements": [
    {
      "asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
      "category": "location",
      "name": "青石集市·盐摊·白天",
      "location_id": "LOC-MARKET",
      "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
      "asset_role": "base",
      "base_asset_id": null,
      "state_version": null,
      "identity_fingerprint": "market-salt-stall-stone-road-wood-awning-v1",
      "scene_ids": ["SC03"],
      "visual_identity": {
        "architecture": "架空东方古代集市，青石路，两侧低矮木构铺面",
        "layout": "盐摊位于画面右侧，后方是木架和麻袋，左侧为主街通道",
        "landmarks": ["粗布遮棚", "木制盐斗", "成排麻袋"],
        "materials": ["青石", "旧木", "粗布", "麻袋"],
        "palette": ["土褐", "灰青", "暖木色"]
      },
      "state_requirements": {
        "time_of_day": "day",
        "weather": "clear",
        "environment_state": "busy_market",
        "occupancy_state": "background_people_allowed"
      },
      "composition_requirements": {
        "purpose": "environment_reference",
        "preferred_view": "wide_establishing",
        "keep_center_action_space": true,
        "character_presence": "none_or_nonidentifiable_background_extras"
      },
      "continuity_constraints": [
        "后续同一盐摊镜头必须保持摊位、主街方向与主要材质一致"
      ]
    }
  ],
  "reuse_assets": [
    {
      "asset_id": "AST-LOC-LIN-HOME-LIVINGROOM-DAY",
      "scene_ids": ["SC01"],
      "registry_status": "verified"
    }
  ]
}
```

规则：

- `generation_requirements` 只能包含 `generation_required=true` 的 location asset。
- `reuse_assets` 不得再次出现在 generation requirements。
- Image Prompt Builder 必须逐条输出，不得“挑重点”。

---

## 3. scene_asset_coverage_gate.json

```json
{
  "schema_version": "1.0",
  "project_id": "DEMO",
  "episode_project_id": "demo_s01e001",
  "source_plan_id": "demo_s01e001_scene_assets_v001",
  "passed": true,
  "deterministic_checks": {
    "scene_count_expected": 5,
    "scene_count_planned": 5,
    "scene_coverage_ratio": 1.0,
    "primary_binding_ratio": 1.0,
    "unresolved_scene_count": 0,
    "duplicate_scene_binding_count": 0,
    "missing_primary_asset_count": 0,
    "unknown_primary_asset_count": 0,
    "reuse_generation_overlap_count": 0,
    "duplicate_generation_asset_count": 0,
    "hard_location_cut_conflict_count": 0,
    "state_conflict_count": 0
  },
  "visual_review": {
    "status": "passed",
    "risk_level": "low",
    "long_same_background_runs": [],
    "over_fragmentation_risks": [],
    "continuity_risks": [],
    "cost_risks": [],
    "repairs_applied": []
  },
  "errors": [],
  "warnings": [],
  "attempts": 1
}
```

---

## 4. scene_asset_handoff.json

这是下游最简权威映射。

```json
{
  "schema_version": "1.0",
  "project_id": "DEMO",
  "episode_project_id": "demo_s01e001",
  "source_plan_id": "demo_s01e001_scene_assets_v001",
  "gate_passed": true,
  "scene_bindings": {
    "SC01": {
      "location_id": "LOC-LIN-HOME",
      "sub_location_id": "SUBLOC-LIN-HOME-LIVINGROOM",
      "primary_location_asset_id": "AST-LOC-LIN-HOME-LIVINGROOM-DAY"
    },
    "SC02": {
      "location_id": "LOC-LIN-HOME",
      "sub_location_id": "SUBLOC-LIN-HOME-COURTYARD",
      "primary_location_asset_id": "AST-LOC-LIN-HOME-COURTYARD-DAY"
    }
  },
  "required_generation_asset_ids": [
    "AST-LOC-LIN-HOME-COURTYARD-DAY"
  ],
  "verified_reuse_asset_ids": [
    "AST-LOC-LIN-HOME-LIVINGROOM-DAY"
  ]
}
```

下游不得在 `gate_passed != true` 时继续生产。
