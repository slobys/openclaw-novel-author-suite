# novel-author 运行工具契约 — V5.4.0 Balanced-Lite / Novel Engine 0.4.7

本文件用于启动时确认能力，不替代 `novel-author-workflow.yaml` 的阶段裁决。只承认当前 OpenClaw runtime 真实注册的工具。

## 基础项目与配置

- `novel_project_create`
- `novel_project_list`
- `novel_project_status`
- `novel_project_configure`
- `novel_project_config_read`

## 规划与资料

- `novel_reference_import`
- `novel_reference_next_batch`
- `novel_reference_analysis_batch`
- `novel_reference_record_batch`
- `novel_artifact_write`
- `novel_artifact_read`
- `novel_idea_bank_write`
- `novel_creativity_review`

## 长篇状态与检索

- `novel_causal_event_record`
- `novel_foreshadowing_upsert`
- `novel_foreshadowing_due`
- `novel_story_ledger_upsert`
- `novel_story_ledger_query`
- `novel_dynamic_state_update`
- `novel_dynamic_state_context`
- `novel_memory_record`
- `novel_memory_search`

## 审计、提交、Closure 与修订

- `novel_logic_audit_prepare`
- `novel_chapter_audit_record`
- `novel_chapter_quality_record`
- `novel_prepare_chapter`
- `novel_commit_chapter`
- `novel_commit_status`
- `novel_read_chapter`
- `novel_revise_chapter`
- `novel_chapter_closure_record`
- `novel_chapter_closure_status`
- `novel_project_integrity_check`

`novel_prepare_chapter` 默认使用：

```json
{ "projectId": "<projectId>", "profile": "compact", "role": "writer" }
```

独立审稿前分别请求 `role=continuity-auditor` 和 `role=reader-editor`。只有关键章或诊断才用 `profile=full`；禁止把 full `packet` 与 full `context` 同时塞给普通 Writer。

正式写章至少要求项目/配置、prepare、audit record、quality record、commit、commit status、read、closure status 和 integrity 工具可用。缺失 `novel_chapter_quality_record`、`novel_commit_status` 或 `novel_project_integrity_check` 时，只能产出草稿，不能宣称 V5 服务端闭环完成。

## 隔离写作与审稿能力

正式 commit 要求 Writer、Continuity Auditor、Reader Editor 三个真实且不同的 session ID。必须使用 OpenClaw 当前真实可用的隔离 session/subagent 能力；不得虚构工具名或 session ID。服务端只验证结构化独立性，编排层仍必须真正创建隔离上下文。

推荐的真实生命周期：

1. 每章先用 `sessions_spawn(context=isolated, thinking=medium, runTimeoutSeconds=900)` 创建一个全新 Writer。主会话不得自己写正文；
2. Writer 只接收 compact writer packet，把正文、计划和17类随稿审计写入当前 chapter evidence 目录，最终回复只返回路径、Hash、汉字数和 session ID；
3. spawn 后立即用 `job_state.py register-task` 保存 `runId`、`childSessionKey`，从 `subagents(action=list)` 获得 `taskId` 后补记；
4. Writer 完成后运行 `writer_handoff_gate.py` 和 `chapter_length.py`。不足硬下限时只用 `sessions_send` 把准确差额发回同一个 Writer 一次，不创建新 Writer；
5. 正文定稿后，再用各自 compact packet 创建 Continuity Auditor 与 Reader Editor；普通章 `thinking=low`，关键章才 `high`；
6. 所需创建请求都得到 `status=accepted` 后调用 `sessions_yield` 等待推送，不轮询；恢复后先运行 job Guard，再用 `sessions_history` 读取最终回执；
7. 正文修订时优先用 `sessions_send` 让原三个子会话处理新 Hash；只有原会话不可访问、失败、超时或角色错误时才创建替代会话；
8. 任何创建、等待、回收或替换动作都必须记录真实标识；没有真实 ID 和成功结果时不得声称写作或审稿完成。

若当前 OpenClaw 的 `sessions_spawn` Schema 支持 `visible=true`，Writer 可以创建为 Dashboard 可见会话；不支持时必须直接使用隐藏的 isolated session，禁止因为可见性字段报错而自动重复 spawn。

## 停止与后台任务取消

- 主会话中的 `/stop` 是运行时级联急停，会停止该会话树内的活动子任务；单纯点界面停止按钮若只中断当前回合，还应发送 `/stop`。
- 用户要求停止时，先执行 `job_state.py cancel` 写入持久化 `cancelling` 屏障，再执行 `subagents(action=list)`；对每个活动 `taskId` 执行 `subagents(action=cancel, taskId=...)`，最后执行 `job_state.py confirm-cancel`。
- `subagents(action=cancel)` 只能取消当前请求者控制的会话树，所以 Writer 与两个 reviewer 必须由同一个主会话创建和登记。
- `cancelling/cancelled` 状态下不得 spawn、yield、sessions_send、resume、重试或处理迟到完成事件；每个阶段和 completion event 前都必须运行 `job_state.py guard`。
- 重复停止必须幂等：不创建新 job、不创建新子会话、不增加 revision；取消中断时保留 `cancelling`，直到下次只做取消对账。

两个角色的 `checks` 与 17 类章节总审计是不同 Schema：

- `continuity-auditor`：7 项，`facts`、`timeline`、`knowledgeBoundary`、`stateContinuity`、`causality`、`promiseContinuity`、`relationshipContinuity`；
- `reader-editor`：6 项，`readability`、`pacing`、`repetition`、`genreExperience`、`hookQuality`、`characterAgency`。

`requiredAuditCategoryCount=17` 只说明 `novel_chapter_audit_record` 的覆盖要求。不得据此给每个 reviewer 伪造 17 项 `checks`。非阻断建议放入 `issues`；Schema/Payload 错误只修结构，不触发模型重审。

每个 reviewer check 的标准值是 `{ "status": "pass|note|warning|not_applicable", "evidence": "可选说明" }`。兼容精确状态字符串 `"pass"`，但不接受描述文字或 `"pass：说明"`。`independent_audit_gate.py` 成功后会生成 `engineReviews`；调用 `novel_chapter_quality_record` 时必须原样传入其中的两个 review，不得再次重组。

调用 `novel_chapter_quality_record` 前必须一次检查完整 Hash 契约：

- `content` 计算出的 canonical SHA-256；
- `continuityReview.bodySha256`；
- `readerReview.bodySha256`；
- `genreGate.bodySha256`；
- `signature.bodySha256`；

以上五处必须相同。`genreGate` 必须有 `pass=true` 或 `genrePass=true`；不能只传本地字段 `genreGatePass=true`。`signature` 除 `bodySha256` 外至少保留一个真实字段，例如 `chapterNo`、`function`、`rhythm` 或 `experienceScores`。

## 服务端能力证据

`novel_project_status.serverCapabilities` 应至少表明：

- `serverGateVerified=true`；
- `hanLengthRecount=true`；
- `auditBodyHashBinding=true`；
- `completeAuditCoverage=true`；
- `independentQualityReceipt=true`；
- `closureReceiptRequired=true`；
- `requestIdRequired=true`；
- `derivedBodyHashBinding=true`；
- `requiredAuditCategoryCount=17`；
- `requestIdIdempotency=true`；
- `requestIdPayloadBinding=true`；
- `crashRecoverableTransactions=true`；
- `commitStatusReconciliation=true`；
- `revisionCas=true`；
- `dynamicStateLedger=true`；
- `threeTierMemory=true`；
- `storyLedgers=true`；
- `projectIntegrityCheck=true`。

运行 `server_capability_gate.py` 时优先直接输入 `novel_project_status` 的完整 JSON。只有验证通过才能报告服务端 V5 Gate 已启用。

## 本地确定性脚本

本地脚本继续作为第二道防线和编排证据：

- `chapter_length.py`
- `draft_revision_gate.py`
- `chapter_payload_gate.py`
- `writer_handoff_gate.py`
- `independent_audit_gate.py`
- `genre_promise.py`
- `quality_gate.py`
- `precommit_gate.py`
- `job_state.py`
- `chapter_closure.py`
- `chapter_signature.py`
- `narrative_fatigue.py`
- `dynamic_state.py`
- `memory_index.py`
- `outline_drift.py`
- `server_capability_gate.py`

其中本地 dynamic state、memory、signature、closure 仅是可删除镜像或编排凭证；服务端 `novel_*` 数据才是权威状态。

## 调用纪律

- 不用 commit 或修订写操作测试参数。
- Schema/参数错误先检查真实工具 Schema；同一稳定错误第二次失败即 blocked。
- 401/403/404、参数校验失败、确定性业务拒绝不自动重复。
- commit 超时或投递不确定先进入 reconciling，调用 `novel_commit_status` 后决定是否复用同一 requestId。

## Closure Payload 契约

`novel_chapter_closure_record.operations` 的合法 key 只有：`causalEvents`、`foreshadowing`、`promisePayoff`、`relationshipGraph`、`oppositionClocks`、`chapterSignature`、`dynamicState`、`memoryIndex`。

每个值必须是状态字符串，或更推荐使用对象：

```json
{
  "status": "completed",
  "evidence": "story/dynamic/state.json",
  "reason": "Dynamic state updated for this chapter."
}
```

- `completed`：必须在同一个 operation 对象内提供 `evidence` 字符串；路径必须存在，且文件中有当前章节和正文 Hash 的绑定记录；
- `skipped`：必须在同一个对象内提供非空 `reason`，不要伪造 evidence；
- 禁止增加顶层 `evidence` 对象；
- 已成功写入的派生台账不得因 Closure Payload 错误重复写入；先读 `novel_chapter_closure_status`，只补 pending/failed 项。

标准 evidence 路径：

- `causalEvents` → `story/causal-events.json`
- `foreshadowing` → `story/foreshadowing.json`
- `promisePayoff` → `story/ledgers/promises.json`
- `relationshipGraph` → `story/ledgers/relationships.json`
- `oppositionClocks` → `story/ledgers/opposition-clocks.json`
- `chapterSignature` → `story/ledgers/chapter-signatures.json`
- `dynamicState` → `story/dynamic/state.json`
- `memoryIndex` → `story/memory/index.json`
