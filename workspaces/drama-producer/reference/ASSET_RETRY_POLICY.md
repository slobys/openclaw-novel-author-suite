# Asset Retry Circuit Breaker v1.0

图片传输重试与语义重生成分开计数。HTTP 429/5xx 的同一 Job、同一 payload 传输重试不增加图片生成次数；换 Job 或换 payload 的真实重生成会占用一次预算。

同一 `asset_lineage_id + requirement_sha256` 默认最多生成 3 次（首次 + 2 次有依据的修订）。后续尝试必须更换 prompt，并写非 `initial` 的 `revision_reason_code`。已有 accepted 结果、已有未终结 Job、原样重复被拒 prompt，或达到总预算时，Gate 会阻止派发。

每个 asset-job 资产必须包含：

```text
asset_lineage_id
requirement_sha256
revision_reason_code
```

回调或审核后必须执行：

```bash
python3 scripts/asset_retry_guard.py update --job dispatch/asset_jobs/{job_id}.json --status accepted
python3 scripts/asset_retry_guard.py update --job dispatch/asset_jobs/{job_id}.json --status rejected --reason-code wrong_identity --evidence review/asset_review.json
```

达到预算后状态为 `held_for_asset_review`，AUTO 流程停止，不再自行创建第 4 个 Job。
