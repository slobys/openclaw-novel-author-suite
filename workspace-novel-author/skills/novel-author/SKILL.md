---
name: novel-author
description: 使用 Novel Engine 0.4.8 以工具受限的逐章隔离 Writer、低 Token 独立审稿和可取消状态机创作、续写、审计及版本化修订中文长篇小说。
---

# Novel Author V5.4.1 Tool-Safe Isolation — Novel Engine 0.4.8 Bridge

`novel-engine` 是作品事实、正文、状态、审计、Quality、台账、记忆、Closure 和提交结果的唯一权威来源。本 Skill 提供创作判断；workspace 脚本只作为第二道确定性门禁与本地编排证据。

项目任务先遵循根目录 `TOOLS.md` 和 `novel-author-workflow.yaml`。不得跳过能力预检、项目配置读取、Hash 绑定、独立审稿、服务端 Quality、可恢复提交、服务端 Closure 或完整性 Gate。

## 按需读取

- 提交前：`protocols/precommit-gate.md`、`protocols/independent-quality.md`；
- 创建或回收 Writer/Reviewer：`protocols/tool-limited-sessions.md`；
- 多章/失败/重连：`protocols/job-state-machine.md`；
- 长篇上下文：`protocols/dynamic-state-memory.md`；
- 类型体验：`protocols/genre-promise.md`；
- 计划偏移：`protocols/outline-drift.md`；
- Promise、关系、情绪：对应协议；
- 服务端硬门禁：`protocols/server-side-gate.md`。

只读取当前阶段需要的协议，不把全部参考一次塞入上下文。

## 新项目

先建立 creative brief：目标阅读体验、不可改变要求、可探索范围、受众、篇幅、边界和禁用套路。形成多个真正不同的候选，从原创性、张力、人物能动性、可持续性、情绪潜力和类型承诺筛选。

方向冻结后保存 premise、story engine、world/world-rules、characters、master/volume/rolling chapter outline、writing rules 和 genre profile。主要角色建立 Voice Profile；主要对手/制度/生态建立 Opposition Clock；初始化 Promise/Payoff、Relationship 与稳定 Beat ID。使用 `novel_project_configure` 固化每本书自己的 writing/quality/enforcement 规格。

## 单章准备

1. `novel_project_status` 与 `novel_project_config_read`；
2. `novel_prepare_chapter(profile=compact, role=writer)` 获取精简资料包；只有关键章或诊断才使用 full；
3. 仅在需要窄化历史时调用 `novel_dynamic_state_context`、`novel_memory_search`、`novel_story_ledger_query`；
4. 每章创建一个新的 isolated Writer session，由它内部比较 2–3 个推进方案并返回 `novel-writer-return-v1` JSON；主会话使用真实 session ID 和 `materialize_session_handoff.py` 落盘、计算 Hash，再执行确定性 Gate。Writer 不需要文件、命令、Novel Engine 或会话编排工具。

优先选择：主角有代价主动选择、因果成立、至少一个关系/信息/Promise/对手压力变化、与近期章节不机械重复，并自然兑现 `genreProfile`。

## 审计与质量

隔离 Writer 对最终正文随稿执行 17 项逻辑审计：facts、timeline、space、motivation、knowledge、worldRules、resources、causality、foreshadowing、originality、voice、sceneDynamics、promiseFairness、relationshipContinuity、emotionCurve、fatigueRisk、oppositionPressure。它把审计和正文放在同一个结构化最终回复中；主会话先将回执确定性落盘，再使用 `writer_handoff_gate.py` 校验完整审计、真实 Writer session ID 与正文 Hash，不再单独进行一次模型通读。

默认篇幅为硬下限 2000、理想目标 2600、建议上限 3200。Writer 可把 2300–2900 作为普通章工作区间以留出汉字统计余量；达到项目硬下限即通过长度 Gate，理想目标不是强制最低值。只有低于硬下限才把准确差额发回同一个 Writer 一次，并用 `draft_revision_gate.py` 验证正文 Hash 确实变化且达到下限；禁止主会话补字、新建 Writer 或重复口头承诺扩写。同 Hash、仍不足或第二次尝试立即 `blocked`。

调用 `novel_chapter_audit_record` 保存经 Gate 验证的 Writer Audit。随后分别调用 compact continuity/reader packet，用两个真实隔离上下文执行 Continuity Auditor 与 Reader Editor；Reviewer 只返回 `novel-review-return-v1` JSON，由主会话绑定真实 session/正文 Hash 后生成 Genre Gate 和 provisional Chapter Signature，并调用 `novel_chapter_quality_record`。Writer 不得自己替代审稿角色。普通章节 Writer 默认 `thinking=medium`、reviewer 默认 `thinking=low`；关键章才提升强度。

17 类章节总审计与 reviewer checks 不可混用：Continuity 固定 7 项，Reader 固定 6 项，具体 Schema 与会话复用方式见 `protocols/independent-quality.md`。`note`/`warning` 不自动触发修订；只有阻断问题才修改正文。审稿检查先经 `independent_audit_gate.py` 标准化，Quality 提交必须原样使用回执中的 `engineReviews`，禁止自行生成 `pass：说明`。

提交 Engine Quality 前按同一协议校验五处正文 Hash，并把本地 `genreGatePass` 映射为 Engine 所需的 `genreGate.pass`；不要用服务端报错逐字段试探 Payload。

正文任何修改都使旧 Audit、Quality、Signature 和本地 receipt 失效，但同章修订优先复用原 Writer 和两个审稿 session，对新 Hash 重新出具结论。每章最多一轮自动定点修订；Schema/Payload 错误只修结构，禁止重新运行语义审稿。

## 停止与取消

用户要求停止时，先运行 `job_state.py cancel` 建立持久化 `cancelling` 屏障，再用 `subagents(action=list)` 获取活动 `taskId` 并逐个 `subagents(action=cancel)`，最后运行 `job_state.py confirm-cancel`。每次 spawn 后必须用 `job_state.py register-task` 保存任务标识；每个阶段、重试和 completion event 前必须运行 `job_state.py guard`。

`cancelling/cancelled` 状态禁止 spawn、yield、sessions_send、resume、审计、提交与后续章节。迟到的完成事件只记录，不恢复流水线；重复停止不创建任务。运行时需要立即急停时，在创建这些子会话的主聊天发送 `/stop`，再在恢复后完成上述持久化取消对账。

## Commit 与对账

使用稳定 `requestId` 调用 `novel_commit_chapter`。正文 Hash 统一采用 `CRLF/CR→LF + trim + UTF-8`。服务端会重算篇幅/Hash，验证 Audit/Quality 和 requestId Payload，并通过可恢复事务写入；返回的 `confirmed/chapterNo/requestId/bodySha256` 可直接作为状态机证据。

投递不确定时先 `novel_commit_status`：只有 `not_found` 才能用同一 requestId、同一 Payload 重试；`committed` 直接进入 Closure；`pending` 继续对账，绝不盲目重提。

## 服务端 Closure

commit 后按真实变化调用因果、伏笔、通用故事台账、`novel_dynamic_state_update` 与 `novel_memory_record`。所有记录绑定当前正文 Hash。然后 `novel_chapter_closure_record`，再 `novel_chapter_closure_status` 确认 complete。

本地 `dynamic_state.py`、`memory_index.py` 和 `chapter_closure.py` 只可保留镜像/编排证据，不得代替服务端状态。

Engine Closure 的 `evidence` 必须是各 `operations.<name>` 对象内部的项目相对 JSON 路径；completed 必须有 evidence，skipped 必须有 reason。Schema 错误时先读 Closure 状态，只重建回执，禁止重复写入已经成功的台账。

## 完整性与修订

每章结束后 `novel_project_integrity_check(repair=false)`；每5章、卷边界、异常恢复和修订后执行完整检查。`repair=true` 只修复可确定的 Meta/State，不伪造语义事实。

修订前 `novel_read_chapter` 读取当前 Hash 与 revision；新正文重新 Audit/Quality 后调用 `novel_revise_chapter`，传 `expectedBodySha256`、`expectedRevision` 和稳定 requestId。修订后重建所有 stale body-binding。

## 长线控制与交付

每 5 章运行 Narrative Fatigue、Arc Audit、Outline Drift；优先调整未来 3–8 章，不静默改写历史。

一章可直接交付全文；多章默认报告章节号、标题、汉字数、Audit、Quality、Commit、Closure、Integrity 和下一章号。用户要求全文时再读取或导出，避免把全部正文重复塞入父会话。
