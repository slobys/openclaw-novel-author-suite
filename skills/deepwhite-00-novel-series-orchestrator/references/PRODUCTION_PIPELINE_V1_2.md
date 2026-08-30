# Production Pipeline Contract v1.2

## Profile

```text
scene_bound_auto_v1.2
```

该 Profile 把每集 AUTO 生产变成一个有状态、不可跳步的流水线。

## Mandatory stages

| Order | Stage ID | Skill / action | Required result |
|---|---|---|---|
| 10 | screenplay | deepwhite-screenwriting-v1 | Scene IDs 稳定的单集剧本 + 权威 scene_index |
| 20 | continuity | deepwhite-continuity-worldstate-zh | 当前集连续性与环境状态 |
| 25 | scene_asset_plan | deepwhite-scene-asset-planner | scene plan / requirements / handoff / coverage gate |
| 30 | image_prompt | deepwhite-image-prompt-builder V2 | strict location prompt manifest |
| 35 | image_prompt_gate | deterministic validator | location prompt manifest gate passed |
| 37 | angle_pack_gate | deterministic validator | independent 9:16 angle pack gate passed |
| 40 | asset_generation | deepwhite-n8n-asset-dispatcher | only generation assets submitted |
| 45 | asset_review | n8n result + AI review | enriched actual asset manifest |
| 50 | shotlist | deepwhite-shotlist-builder-zh-user v2.8+ | actual-asset-based shotlist + shot bindings + draft video prompt manifest |
| 52 | environment_continuity_gate | deterministic validator | route anchors, predecessor references and landmark continuity passed |
| 55 | shot_binding_gate | deterministic validator | shot binding ratios all 1.0 |
| 60 | transition | deepwhite-shot-transition-builder-zh | optional; cannot change machine location binding |
| 65 | video_prompt_ready | producer gate | transition applied when needed; final prompt manifest revalidated |
| 70 | video_dispatch | deepwhite-n8n-video-dispatcher V2 | video job + video scene gate |
| 80 | video_generation | n8n | accepted clip results |
| 90 | final_composition | FFmpeg / producer | final MP4 + manifest |
| 95 | pipeline_evidence | validate_episode_pipeline.py | series_pipeline_evidence.json passed |
| 100 | series_complete | series_orchestrator.py complete | commit episode, update world/asset state |

## Required fixed artifact paths

```text
input/series_episode_context.json
input/production_pipeline_contract.json
script/scene_index.json
assets/scene_asset_plan.json
assets/location_asset_requirements.json
assets/location_asset_prompt_manifest.json
assets/angle_pack_manifest.json
assets/actual_asset_manifest.json
shots/spatial_blocking.json
handoffs/scene_asset_handoff.json
gates/scene_asset_coverage_gate.json
gates/location_prompt_manifest_gate.json
gates/angle_pack_gate.json
gates/asset_retry_budget_gate.json
gates/environment_continuity_gate.json
gates/shot_scene_binding_gate.json
gates/video_scene_binding_gate.json
review/video_prompt_gate_review.json
video_prompts/video_prompt_manifest.json
dispatch/video_jobs/{video_job_id}.json
review/series_pipeline_evidence.json
```

最终视频 manifest 的位置可以由现有 producer 决定，但 `complete` 仍会验证最终 MP4 的 SHA256。

## Mandatory gate thresholds

### Scene Asset Coverage

```text
passed == true
scene_coverage_ratio == 1.0
primary_binding_ratio == 1.0
authoritative_scene_index_used == true
movement_scene_count == resolved_movement_scene_count
```

其中比例可能位于 `deterministic_checks` 下。

### Location Prompt Manifest

```text
passed == true
coverage_ratio == 1.0
missing_asset_ids == []
unexpected_asset_ids == []
```

### Shot Scene Binding

```text
passed == true
scene_coverage_ratio == 1.0
shot_binding_ratio == 1.0
prompt_binding_ratio == 1.0
authoritative_scene_index_used == true
```

### Independent Angle Pack

核心、常驻、单集重要人物及常驻生物必须有八个独立 9:16 文件。`pack_count == validated_pack_count`；多面板设定页不得作为 video reference。

### Asset Retry Budget

`passed == true`。同一 `asset_lineage_id + requirement_sha256` 最多 3 次真实生成，换 Job ID 不能重置；同 Job 同 payload 的网络重传不增加生成次数。

### Environment Continuity

```text
passed == true
route_anchor_coverage_ratio == 1.0
```

非首路线锚点必须提供已验证的前一环境引用证据，地标世界关系不得无解释突变。

### Video Prompt Review

必须明确允许进入视频生产。推荐：

```text
ready_for_video_prompt_generation == true
```

若使用旧结构，则所有硬 Gate 必须为 passed，且不存在 blocker。

### Video Scene Binding

```text
passed == true
binding_coverage_ratio == 1.0
```

## Stage invalidation

上游发生变化时，只让依赖它的下游失效：

- screenplay changed → continuity 及其后全部失效；
- continuity changed → scene asset plan 及其后全部失效；
- scene asset plan/handoff changed → image prompt gate、asset manifest、shot/video binding 全部失效；
- generated/reviewed image changed → actual asset manifest、shot/video binding 失效；
- route anchor/spatial continuity changed → environment continuity、shot/video binding 失效；
- shotlist/timing changed → shot binding、transition、video prompt、video scene binding 失效；
- transition changed final prompt text → rerun shot binding and video prompt readiness；
- video prompt/job changed → video scene binding 与当前视频结果失效；
- only final edit changed → 不使图片/视频资产失效。

## Cross-scene rule

一个 AUTO 视频生成 clip 不得跨两个 `scene_id`，也不得跨两个 `route_anchor_id`。即使两个 Scene 在同一大地点，也必须在 Scene 边界新建 clip。

## Duration rule

```text
4 <= generated_clip_duration <= 15 seconds
```

内部 Shot 可以 1–3 秒，但必须包含在合规的生成 clip 内，或生成 4 秒后在合成阶段裁切。
