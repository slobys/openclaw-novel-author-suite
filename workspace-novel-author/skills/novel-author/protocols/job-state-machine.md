# Job State Machine Protocol V5.0

本地 job 只负责编排；章节与项目事实仍以 `novel-engine` 为准。

## 严格状态

```text
pending → preparing → drafting → length_gate → auditing
→ quality_gate → precommit_gate → committing → closing
→ integrity_gate → committed
```

`failed`、`blocked`、`reconciling` 为异常状态。禁止跨级、倒退或用 force 绕过。

进入 `precommit_gate` 必须提供 `qualityPass=true` 且绑定正文 Hash 的 receipt；进入 `committing` 必须提供 `gatePass=true` 的 precommit receipt；进入 `closing` 必须提供 engine commit receipt；进入 `committed` 必须提供 closure receipt。

同一项目只能有一个活动 job 和一个 Writer。多章严格串行，父会话逐章启动 isolated Writer 并等待最终状态。

长度不足不是无限重试条件。初次长度 receipt 绑定正文 Hash；只有低于项目 `minHanChars` 时允许一次自动修订。修订必须经 `draft_revision_gate.py` 证明 Hash 已改变且达到硬下限。相同正文、仍低于下限或第二次自动修订一律进入 `blocked`，不得用“现在真正扩写”等文字继续占用回合。

所有 mutation 使用 revision/CAS。相同稳定错误码第二次失败进入 blocked。commit 投递不确定从 `committing` 进入 `reconciling`：先查询 engine；已存在且 Hash 一致→closing，明确不存在→precommit_gate 并复用原 requestId，仍不确定→停止。
