# Environment Continuity Gate v1.0

移动场次不再把一个 Scene 强制绑定为一张背景。`scene_asset_handoff.json` 为该 Scene 给出有序 `route_anchors`；分镜、空间阻挡和视频提示词必须逐锚点继承。

每个 `shots/spatial_blocking.json.environment_continuity_map.routes[].nodes[]` 至少包含：

- `route_anchor_id`、`role`、`location_asset_id`、`predecessor_environment_asset_id`；
- `inherited_location_id`；
- 人物位置、机位、观察方向和路线方向；
- 地标 ID、地标世界关系、预期画面位置/尺度、距离变化、视差和遮挡解释；
- 除第一个锚点外，`reference_evidence.provider_reference_verified=true`，且 `reference_asset_ids` 包含上一个环境资产。

硬规则：路线锚点集合和顺序必须与 Handoff 完全一致；地标世界关系不得无解释改变；上一个环境资产必须真实作为下一张图/下一段视频的参考输入，而不能只把 ID 写进 JSON。

执行：

```bash
python3 scripts/validate_environment_continuity.py \
  --handoff handoffs/scene_asset_handoff.json \
  --assets assets/actual_asset_manifest.json \
  --spatial shots/spatial_blocking.json \
  --out gates/environment_continuity_gate.json
```
