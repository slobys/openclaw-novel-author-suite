# v1.1 → v1.2 Migration

## What changes

v1.1 的总控主要负责系列规划、串行队列、跨集状态和资产复用。

v1.2 增加：

- Scene Asset Planner 强制阶段；
- scene/location/sub-location/location-asset 全链路绑定；
- Image Prompt Builder strict plan gate；
- Shot Scene Binding Gate；
- Video Scene Binding Gate；
- complete 前 Pipeline Evidence Gate；
- Scene Planner 动态复用 ID 进入 `series_asset_gate.py build-plan`。

## Existing episode JSON

已有 `schema_version=1.1` 文件不会因为格式本身被拒绝。

但当：

```text
production.auto_production_mode == true
```

且没有显式：

```text
legacy_pipeline_allowed = true
```

新的 `dispatch-next` 默认给它生成：

```text
scene_bound_auto_v1.2
```

Pipeline Contract。

因此升级后继续跑旧项目，也会自动进入新的场景强绑定流水线。

## How to keep legacy behavior temporarily

仅用于迁移期，在 episode `production` 中显式设置：

```json
{
  "legacy_pipeline_allowed": true,
  "pipeline_profile": "legacy_v1.1",
  "require_pipeline_evidence": false
}
```

不建议新项目使用。

## Downstream requirement

AUTO v1.2 完成前需要运行：

```bash
python3 ${OPENCLAW_SKILLS_DIR}/deepwhite-00-novel-series-orchestrator/scripts/validate_episode_pipeline.py \
  --project-root ${OPENCLAW_STATE_DIR}/workspace-drama-producer/projects/{episode_project_id} \
  --out ${OPENCLAW_STATE_DIR}/workspace-drama-producer/projects/{episode_project_id}/review/series_pipeline_evidence.json
```

然后 `complete` 增加：

```text
--pipeline-evidence .../review/series_pipeline_evidence.json
```
