<!-- BEGIN DEEPWHITE_CONTINUITY_DISPATCH_V2 -->

# Continuity Asset Job v2（最高优先级）

当任务 `schema_version` 为 `2.x` 或包含 `reference_inputs` 时，必须使用连续资产派发模式。

除旧版必需字段外，保留：

```text
parent_asset_id
family_id
style_id
asset_code
generation_stage
lock_id
lock_hash
depends_on
reference_inputs
anchor_roles
```

派发前必须：

1. 校验 asset_id 和 filename 唯一；
2. 校验依赖图无环；
3. 确认所有必需参考图声明包含 `approved_only: true`；
4. 运行 `validate-continuity-job.mjs`；
5. 使用 `send-continuity-job-to-n8n.mjs` 提交；
6. 共享目录可用时加 `--wait`，等待 reference registry 到达终态。

不得删除额外连续性字段后降级为 v1 任务。

<!-- END DEEPWHITE_CONTINUITY_DISPATCH_V2 -->
