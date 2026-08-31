---
name: novel-engine-operations
description: 操作 Novel Engine V5 服务端工具，负责项目状态、审计、提交、对账、Closure、修订和完整性检查；具体小说创作规则由 workspace 的 novel-author Skill 负责。
---

# Novel Engine Operations — V5.4 Balanced-Lite

`novel-engine` 是作品业务事实、章节正文和提交状态的唯一权威来源。聊天记忆、workspace 缓存、任务文件和本地脚本只负责创作判断、编排或派生校验；冲突时以 `novel_*` 工具返回为准。

## 开始任何项目任务

1. 调用 `novel_project_list` 确认项目；
2. 调用 `novel_project_status` 获取 `nextChapter`、服务端能力、未完成 Closure、待恢复事务和完整性状态；
3. 调用 `novel_project_config_read` 获取项目实际 `writingContract`、`quality`、`enforcement` 与 `genreProfile`；
4. 不把全局默认值当成项目值，不凭聊天记录猜测章节号。

旧项目首次由 0.4.0 读取时会建立迁移边界。迁移边界之前的历史章节可被 grandfathered，但从边界章节开始必须执行 V5 门禁。

## 新项目

先建立 creative brief，明确目标阅读体验、不可改变要求、可探索范围、受众、篇幅、边界和禁用套路。生成多个真正不同的候选，并从 originality、tension、agency、sustainability、emotion、genrePromise 六维筛选。

方向冻结后保存：`creative-brief`、`story-engine`、`novelty-report`、`premise`、`world`、`world-rules`、`characters`、`master-outline`、`writing-rules`、`genre-profile`、卷纲和滚动章纲。主要角色建立 Voice Profile；主要对手、制度、生态或灾害建立 Opposition Clock；初始化 Promise、Relationship 和稳定 Beat ID。

用 `novel_project_configure` 明确项目规格。修改配置时必须使用 `expectedRevision`，避免覆盖其他会话刚完成的设置。

## 单章生产顺序

### 1. Prepare

普通章节调用 `novel_prepare_chapter(profile=compact, role=writer)`；只有关键章或诊断才使用 `profile=full`。精简资料包包含：

- 本章章纲与原创设定；
- 最近章节摘要、连续性变化和上一章末尾；
- Character / Knowledge / Inventory / Location 动态状态；
- short / mid / long 三级记忆候选；
- 因果、伏笔、Promise、关系、Opposition Clock；
- 最近 Chapter Signature；
- 17 项审计契约和项目级篇幅规格。

若返回 `ready:false`，先补齐指定 artifact。若上一章 Closure 未完成且项目要求 Closure，不得绕过。

### 2. Isolated plan and draft

每章创建一个新的 isolated Writer session，主会话只负责编排。Writer 把 `plan.json`、`chapter.md` 和绑定最终正文 Hash 的17类 `writer-audit.json` 写入本章 evidence 目录，返回路径、Hash、汉字数和 Writer session ID；主会话不得自己写正文或再次做一次模型语义审计。

内部比较 2–3 个推进方案。优先选择同时满足以下条件的方案：

- 主角主动选择并承担代价；
- 因果、世界规则、资源和知识边界成立；
- 至少一个关系、信息、Promise 或对手压力发生有效变化；
- 与近期章节的开场、冲突、解法和结尾不机械重复；
- 兑现项目 `genreProfile` 承诺；
- 产生可持续后果，而不是只制造一章热闹。

Scene 和 Beat 数量服从项目实际 writing contract。标题参数只传纯标题；正文参数不得包含 Markdown 章标题或“第N章”。

### 3. Logic audit

Writer 使用 prepare packet 中的审计契约对最终正文执行完整随稿审计。主会话用 `writer_handoff_gate.py` 验证后调用 `novel_chapter_audit_record`，不得为了记录回执再通读正文。至少覆盖：

`facts`、`timeline`、`space`、`motivation`、`knowledge`、`worldRules`、`resources`、`causality`、`foreshadowing`、`originality`、`voice`、`sceneDynamics`、`promiseFairness`、`relationshipContinuity`、`emotionCurve`、`fatigueRisk`、`oppositionPressure`。

正文固定后调用 `novel_chapter_audit_record`。`decision=pass` 时必须覆盖全部项目要求类别，不得含 error、block 或 fatal；服务端会重算汉字数和正文 SHA-256。

### 4. Independent quality

Writer、Continuity Auditor、Reader Editor 必须使用三个不同的隔离会话 ID。两个 reviewer 分别使用 `role=continuity-auditor` 与 `role=reader-editor` 的 compact packet；普通章默认 low thinking。

- Continuity Auditor：只审事实、时间线、空间、动机、知识边界、世界规则、资源、因果、伏笔、公平性、关系连续性和对手压力；
- Reader Editor：只审可读性、重复、节奏、情感、场景动态、人物声音、类型承诺、章节功能和钩子；
- Writer 不得自己替代两个审稿角色。

生成 Genre Gate 与 provisional Chapter Signature 后调用 `novel_chapter_quality_record`。任何正文修改都会使旧 Audit 和 Quality receipt 的 Hash 失效，必须重新生成。

服务端能验证正文 Hash、审稿角色、三会话 ID 不同、结论和阻断问题；它不能仅凭 ID 证明三个会话在物理上确实隔离，因此编排 Agent 必须真实创建独立上下文。

### Stop and cancel

每次 spawn 后登记 taskId/runId/sessionKey。用户要求停止时先把本地 Job 写成 `cancelling`，再用 `subagents(action=cancel, taskId=...)` 取消本会话树内活动任务，最后确认 `cancelled`。每个阶段和迟到 completion 前必须检查 Guard；`cancelling/cancelled` 不得恢复、重试或创建后台任务。主聊天中的 `/stop` 用于立即级联急停，持久化取消用于阻止重连后复活。

### 5. Commit

使用稳定且唯一的 `requestId` 调用 `novel_commit_chapter`。服务端重新执行：

- 项目级汉字硬下限；
- 标题/正文 Payload 纯净性；
- 17 项审计覆盖；
- Audit 与正文 SHA-256 一致；
- Independent Quality 与正文 SHA-256 一致；
- 期望章节号；
- requestId 与完整 Payload 指纹绑定；
- 多文件事务 CAS。

若网络断开、投递不确定或 UI 提示无法确认，先调用 `novel_commit_status`，按同一个 `requestId` 或章节号对账。只有明确 `not_found` 才可重新提交；不得盲目重复 commit。

### 6. Closure

Commit 成功后，按正文真实变化更新：

- `novel_causal_event_record`；
- `novel_foreshadowing_upsert`；
- `novel_story_ledger_upsert`：Promise、Relationship、Opposition Clock、Chapter Signature、Arc Audit、Outline Drift；
- `novel_dynamic_state_update`：人物、知识、物品、地点；
- `novel_memory_record`：short、mid、long 记忆。

这些更新必须绑定本章当前 `contentSha256`。然后调用 `novel_chapter_closure_record`，为适用操作提交 durable evidence；最后用 `novel_chapter_closure_status` 确认 complete。不要在台账实际未更新时把操作标为 completed。

### 7. Integrity

多章任务每章结束后进行轻量状态核对；每 5 章、卷边界、修订后或异常恢复后调用 `novel_project_integrity_check`。`repair:true` 只用于安全修复元数据和状态进度，不会替你自动重写正文、审稿结论或过期记忆。

## 修订章节

1. `novel_read_chapter` 获取当前 `contentSha256` 和 `revision`；
2. 分析对后续章节、状态、记忆、伏笔、Promise 和关系的影响；
3. 对新正文重新执行 Audit 与 Independent Quality；
4. 调用 `novel_revise_chapter`，同时传 `expectedBodySha256`、`expectedRevision` 和稳定 `requestId`；
5. 更新受影响的动态状态、记忆、Signature 和 Closure；
6. 调用完整性检查。若报告 `DYNAMIC_STATE_STALE_BINDING`、`MEMORY_STALE_BINDING` 或 `LEDGER_STALE_BINDING`，必须重建对应派生索引，不能忽略。

## 长线控制

每 5 个 committed 章节或卷/阶段边界执行 Arc Audit、Narrative Fatigue 和 Outline Drift。优先调整未来 3–8 章；除非用户明确要求，不静默改写历史章节。

三级记忆用途：

- short：最近 3–5 章、当前场景和紧邻行动；
- mid：当前卷、最近 20–50 章、人物状态和阶段任务；
- long：旧事件、历史关系、地点、物品、关键选择、伏笔和对白证据。

`novel_memory_search` 是本地词法/中文 n-gram 检索，不等于语义真相。召回结果必须与当前 engine 状态、正文 Hash 和时间线交叉核对。

## 多章任务

每章独立执行 Prepare → Draft → Audit → Independent Quality → Commit → Closure → Integrity。不得先写完多章再集中提交。已确认 committed 的章节永不重复生成或覆盖。

多章默认汇报章节号、标题、汉字数、Audit、Quality、Commit、Closure、Integrity 和下一章号；用户要求完整全文时再读取或导出，避免把所有正文反复塞入父会话。
