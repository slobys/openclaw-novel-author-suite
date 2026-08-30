# Independent Angle Pack Contract v1.0

核心角色、常驻角色、单集重要角色、宠物和常驻生物必须生成标准八方向资产包。每个角度是一个独立 9:16 文件，禁止把八个角度拼在同一张图里。

标准顺序：`front`、`front_left_three_quarter`、`left_profile`、`rear_left_three_quarter`、`back`、`rear_right_three_quarter`、`right_profile`、`front_right_three_quarter`。

同包资产必须共享 `subject_id`、`state_id=neutral_identity_state`、`identity_fingerprint`、`identity_reference_sha256` 和 `style_contract_sha256`。每个资产必须声明 `asset_role=video_reference`、`layout_type=single_view_clean`、`contains_multiple_independent_assets=false`。

横向角色设定页或多面板图片只允许作为 `design_sheet` 供人工比对身份，永远不能替代八个独立生产文件，也不能进入视频 reference bundle。

执行：

```bash
python3 scripts/validate_angle_pack.py \
  --manifest assets/angle_pack_manifest.json \
  --job dispatch/asset_jobs/{job_id}.json \
  --out gates/angle_pack_gate.json
```
