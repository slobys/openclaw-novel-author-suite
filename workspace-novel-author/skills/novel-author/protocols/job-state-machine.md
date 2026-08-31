# Job State Machine Protocol V5.4

本地 job 只负责编排；章节与项目事实仍以 `novel-engine` 为准。

## 严格状态

```text
pending → preparing → drafting → length_gate → auditing
→ quality_gate → precommit_gate → committing → closing
→ integrity_gate → committed
```

`failed`、`blocked`、`reconciling`、`cancelling` 为异常状态，`cancelled` 为终止状态。禁止跨级、倒退或用 force 绕过。

进入 `precommit_gate` 必须提供 `qualityPass=true` 且绑定正文 Hash 的 receipt；进入 `committing` 必须提供 `gatePass=true` 的 precommit receipt；进入 `closing` 必须提供 engine commit receipt；进入 `committed` 必须提供 closure receipt。

同一项目只能有一个活动 job 和一个 Writer。多章严格串行，父会话逐章启动全新的 isolated Writer，并用 `register-task` 保存 Writer/Reviewer 的 taskId、runId 和 sessionKey。任何等待、重试或处理完成事件之前先运行 `guard`。

长度不足不是无限重试条件。初次长度 receipt 绑定正文 Hash；只有低于项目 `minHanChars` 时允许一次自动修订。修订必须经 `draft_revision_gate.py` 证明 Hash 已改变且达到硬下限。相同正文、仍低于下限或第二次自动修订一律进入 `blocked`，不得用“现在真正扩写”等文字继续占用回合。

所有 mutation 使用 revision/CAS。相同稳定错误码第二次失败进入 blocked。commit 投递不确定从 `committing` 进入 `reconciling`：先查询 engine；已存在且 Hash 一致→closing，明确不存在→precommit_gate 并复用原 requestId，仍不确定→停止。

## 两阶段取消

1. `cancel --job <id>` 是幂等请求：第一次把所有未 committed 章节写成 `cancelling`，输出已登记的取消目标；重复调用不增加 revision。
2. `cancelling` 是持久化硬屏障。所有普通 mutation、spawn、sessions_send、yield、retry、resume 和迟到 completion 都必须被拒绝。
3. 主会话对 `subagents(action=list)` 返回的每个活动 taskId 执行 `subagents(action=cancel, taskId=...)`。不得创建“清理子会话”来做取消。
4. 实际取消动作结束后运行 `confirm-cancel --evidence <结果>`，状态变为 `cancelled`。若中间再次中断，保持 `cancelling`，下次只继续取消对账。
5. `cancelled` job 不再占用项目活动 job 名额；后续恢复创作必须创建新 job，并重新以 engine `nextChapter` 为准。

`/stop` 是 OpenClaw 会话树的运行时急停；它解决“先把正在跑的子任务停下来”。`cancel/confirm-cancel` 解决“重连或迟到事件不能又把流水线拉起来”。两者配合使用，不能互相替代。
