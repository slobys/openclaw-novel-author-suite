# V1 → V2 Migration

This package keeps the same skill name:

```text
deepwhite-image-prompt-builder
```

so it can replace the existing folder in place.

## Main behavior change

V1:

```text
full script → select a compact set of strongest stills
```

V2:

```text
if no upstream asset plan:
  keep V1 behavior

if generation_requirements[] exists:
  STRICT_ASSET_PLAN_MODE
  every planned asset must be prompted one-to-one
```

## Recommended pipeline

```text
deepwhite-scene-asset-planner
→ assets/location_asset_requirements.json
→ deepwhite-image-prompt-builder V2
→ assets/location_asset_prompt_manifest.json
→ scripts/validate_location_prompt_manifest.py
→ deepwhite-n8n-asset-dispatcher
```

Do not change the skill slug in OpenClaw; replace the existing directory after backing it up.
