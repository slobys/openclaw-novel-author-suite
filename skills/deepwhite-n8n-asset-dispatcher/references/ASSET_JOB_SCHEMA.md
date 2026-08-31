# Asset Job Schema

> v1.0 仅用于没有连续性依赖的兼容任务。`scene_bound_auto_v1.2`、包含 `reference_inputs` 或 `asset_lineage_id` 的自动生产任务必须使用 v2.1，示例见 `templates/asset-job.continuity.example.json`，并由 `validate-continuity-job.mjs` 校验。

```json
{
  "schema_version": "1.0",
  "job_id": "string, required, unique per batch",
  "project_id": "string, required",
  "source": "openclaw",
  "created_at": "ISO-8601 string, optional",
  "defaults": {
    "model": "gemini-3.1-flash-image",
    "aspect_ratio": "16:9",
    "image_size": "2K"
  },
  "assets": [
    {
      "asset_id": "CHAR_EXAMPLE_001",
      "category": "character|location|prop|style|storyboard|other",
      "name": "中文资产名称",
      "filename": "CHAR_EXAMPLE_001.png",
      "prompt_zh": "完整中文图片提示词",
      "prompt_en": "Complete English image prompt",
      "negative_prompt": "optional",
      "asset_role": "video_reference",
      "asset_kind": "character|creature|location|environment|prop",
      "angle_id": "three_quarter_front",
      "layout_type": "single_view_clean",
      "contains_multiple_independent_assets": false,
      "aspect_ratio": "9:16",
      "image_size": "2K",
      "model": "optional per-asset override",
      "reference_images": [],
      "metadata": {
        "scene_ids": [],
        "character_ids": [],
        "continuity_notes": "optional"
      }
    }
  ]
}
```

## Required

Job: `schema_version`, `job_id`, `project_id`, `source`, `defaults`, `assets`.

Asset: `asset_id`, `category`, `name`, `filename`, and at least one of `prompt_zh` / `prompt_en`.

`job_id`、`project_id` 与 `asset_id` 只允许 ASCII 字母、数字、下划线和短横线。`filename` 必须是 ASCII 安全的 `.png` 文件名。`category` 必须是文档列出的枚举值。

存在 `style_contract` 或 `style_contract_sha256` 时视为系列任务：两者必须同时存在，每个资产还必须有非空 `negative_prompt`。

## Prohibited

- API keys, webhook secrets, passwords.
- Arbitrary output directories.
- Duplicate asset IDs or duplicate filenames.
- Markdown fences around the file content.

## v2.1 自动生产额外要求

- Job：`schema_version` 必须为 `2.x`；正式发送时自动计算并绑定 `payload_sha256`。
- 每项资产必须包含完整 PORTABLE HARD LOCK、`lock_id`、可重新计算的 `lock_hash`、`depends_on` 和 `reference_inputs`。
- 视频生产参考必须是独立单视角图片：`asset_role=video_reference`、`asset_kind`、`angle_id`、`layout_type=single_view_clean`、`contains_multiple_independent_assets=false`。
- 场景资产还必须绑定 `scene_ids`、`location_id`、`sub_location_id` 和 `location_asset_id`。
- 必需参考的 `required=true` 时，`approved_only` 必须为 `true`。
- HTTP 2xx 仅代表 Webhook 入站；Registry 中全部必需资产通过 Job/Hash/Lock/文件校验并为 `approved` 才算完成。
