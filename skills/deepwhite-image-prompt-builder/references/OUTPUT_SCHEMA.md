# Image Prompt Builder V2 Output Schema

## 1. assets/location_asset_prompt_manifest.json

```json
{
  "schema_version": "2.0",
  "mode": "strict_asset_plan",
  "project_id": "DEMO",
  "episode_project_id": "demo_s01e001",
  "source_plan_id": "demo_s01e001_scene_assets_v001",
  "source_requirement_count": 1,
  "assets": [
    {
      "asset_id": "AST-LOC-MARKET-SALT-STALL-DAY",
      "category": "location",
      "name": "青石集市·盐摊·白天",
      "filename": "AST-LOC-MARKET-SALT-STALL-DAY.png",
      "prompt_zh": "完整中文场景图片提示词",
      "prompt_en": "Complete English environment image prompt",
      "reference_images": [],
      "metadata": {
        "scene_ids": ["SC03"],
        "location_id": "LOC-MARKET",
        "sub_location_id": "SUBLOC-MARKET-SALT-STALL",
        "identity_fingerprint": "market-salt-stall-stone-road-wood-awning-v1",
        "source_plan_id": "demo_s01e001_scene_assets_v001",
        "continuity_notes": "保持盐摊、主街方向、遮棚、麻袋和木架空间关系稳定"
      }
    }
  ]
}
```

### Required manifest fields

```text
schema_version
mode
project_id
episode_project_id
source_plan_id
source_requirement_count
assets
```

### Required asset fields

```text
asset_id
category
name
filename
prompt_zh
prompt_en
metadata
```

### Required location metadata

```text
scene_ids
location_id
sub_location_id
identity_fingerprint
source_plan_id
```

`filename` 默认：

```text
<asset_id>.png
```

除非项目有已确认的命名规范。

---

## 2. gates/location_prompt_coverage_gate.json

validator 生成：

```json
{
  "schema_version": "1.0",
  "passed": true,
  "requirement_count": 1,
  "output_asset_count": 1,
  "coverage_ratio": 1.0,
  "missing_asset_ids": [],
  "unexpected_asset_ids": [],
  "duplicate_output_asset_ids": [],
  "metadata_mismatches": [],
  "reuse_overlap_asset_ids": [],
  "errors": []
}
```

---

## 3. handoffs/image_prompt_handoff.json

```json
{
  "schema_version": "1.0",
  "mode": "strict_asset_plan",
  "project_id": "DEMO",
  "episode_project_id": "demo_s01e001",
  "source_plan_id": "demo_s01e001_scene_assets_v001",
  "prompt_manifest_path": "assets/location_asset_prompt_manifest.json",
  "coverage_gate_path": "gates/location_prompt_coverage_gate.json",
  "asset_count": 1,
  "asset_ids": ["AST-LOC-MARKET-SALT-STALL-DAY"],
  "passed": true
}
```
