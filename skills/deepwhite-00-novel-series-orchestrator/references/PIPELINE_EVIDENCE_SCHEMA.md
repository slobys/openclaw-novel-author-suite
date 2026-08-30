# Series Pipeline Evidence Schema v1.0

`review/series_pipeline_evidence.json` 是总控在 `complete` 之前要求的最终生产证据。

它不是 Agent 自己写一个 `passed=true` 就算通过。推荐由：

```bash
scripts/validate_episode_pipeline.py
```

读取真实 artifact/gate 文件后自动生成，并为每个文件记录 SHA256。

## Example

```json
{
  "schema_version": "1.0",
  "pipeline_profile": "scene_bound_auto_v1.2",
  "episode_project_id": "demo_s01e001",
  "passed": true,
  "required_gate_count": 8,
  "passed_gate_count": 8,
  "artifacts": {
    "scene_asset_plan": {
      "relative_path": "assets/scene_asset_plan.json",
      "sha256": "..."
    },
    "scene_asset_handoff": {
      "relative_path": "handoffs/scene_asset_handoff.json",
      "sha256": "..."
    },
    "location_asset_prompt_manifest": {
      "relative_path": "assets/location_asset_prompt_manifest.json",
      "sha256": "..."
    },
    "actual_asset_manifest": {
      "relative_path": "assets/actual_asset_manifest.json",
      "sha256": "..."
    },
    "video_prompt_manifest": {
      "relative_path": "video_prompts/video_prompt_manifest.json",
      "sha256": "..."
    },
    "video_job": {
      "relative_path": "dispatch/video_jobs/demo_video_001.json",
      "sha256": "..."
    }
  },
  "gates": {
    "scene_asset_coverage": {
      "relative_path": "gates/scene_asset_coverage_gate.json",
      "sha256": "...",
      "passed": true
    },
    "location_prompt_manifest": {
      "relative_path": "gates/location_prompt_manifest_gate.json",
      "sha256": "...",
      "passed": true
    },
    "angle_pack": {
      "relative_path": "gates/angle_pack_gate.json",
      "sha256": "...",
      "passed": true
    },
    "asset_retry_budget": {
      "relative_path": "gates/asset_retry_budget_gate.json",
      "sha256": "...",
      "passed": true
    },
    "environment_continuity": {
      "relative_path": "gates/environment_continuity_gate.json",
      "sha256": "...",
      "passed": true
    },
    "shot_scene_binding": {
      "relative_path": "gates/shot_scene_binding_gate.json",
      "sha256": "...",
      "passed": true
    },
    "video_prompt_review": {
      "relative_path": "review/video_prompt_gate_review.json",
      "sha256": "...",
      "passed": true
    },
    "video_scene_binding": {
      "relative_path": "gates/video_scene_binding_gate.json",
      "sha256": "...",
      "passed": true
    }
  },
  "errors": [],
  "warnings": [],
  "created_at": "..."
}
```

## Complete-time verification

`series_orchestrator.py complete` 对 AUTO v1.2 episode 必须再次检查：

1. evidence 位于当前 `episode_project_id` 的 project root 内；
2. `passed == true`；
3. `pipeline_profile == scene_bound_auto_v1.2`；
4. 八个 required gate 都存在且 passed；
5. evidence 中每个 artifact/gate 的 `relative_path` 不能逃逸 project root；
6. 当前磁盘文件 SHA256 与 evidence 中记录完全一致。

因此某人事后修改了 Gate JSON 或 Video Job，旧 Evidence 会立刻失效。
