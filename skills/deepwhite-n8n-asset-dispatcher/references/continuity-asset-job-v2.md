# Continuity Asset Job v2.1

当任务 `schema_version` 为 `2.x` 或包含 `reference_inputs` 时，使用连续资产派发模式。

## 提交前

1. `project_id/job_id/asset_id/filename` 必须通过安全 ASCII 校验；
2. `shared_asset_root` 只能来自 `OPENCLAW_ASSET_SHARED_ROOT`，不得出现在 Payload；
3. `depends_on` 必须无环；外部依赖必须同时声明为 `reference_inputs`；
4. 必需参考图必须声明 `approved_only: true`；
5. `lock_hash` 必须是四锁规范化对象的完整 SHA256；
6. 运行 `validate-continuity-job.mjs`。发送脚本会再次执行相同验证并生成 `payload_sha256`。

## 正式自动生产

```bash
node scripts/send-continuity-job-to-n8n.mjs dispatch/asset_jobs/job.json \
  --wait \
  --registry-snapshot=assets/reference_registry.json
```

HTTP 2xx 只表示 `webhook_accepted_unverified`。只有 Registry 中每个必需资产均为 `approved`，且 `job_id`、`payload_sha256`、`lock_hash`、`file_size` 和文件 `sha256` 全部匹配，才算阶段成功。

`rejected/failed/superseded` 是失败终态，不是成功终态。
