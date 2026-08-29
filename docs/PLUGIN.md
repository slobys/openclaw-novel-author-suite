# Novel Engine 0.4.4 — Public Deployment Edition

面向 OpenClaw 长篇小说 Agent 的持久化工具插件。0.4.4 保留 0.4.3 的项目写锁有限等待、租约心跳和陈旧锁安全回收，并与 Novel Author V5.3.2 Workspace 一起提供公开部署。新项目默认使用 2000 硬下限、2600 理想目标、3200 建议上限；项目数据格式不变。

## 核心能力

- **项目级 Writing Contract**：每本书独立设置 `minHanChars`、目标区间和质量规则；
- **17 项逻辑审计**：从 facts 到 oppositionPressure，passing audit 必须完整覆盖；
- **Independent Quality Receipt**：Writer、Continuity Auditor、Reader Editor 三个不同 session ID，正文 Hash 全链路绑定；
- **Crash-recoverable Commit**：提交先持久化事务清单，再逐项 CAS 写入；中断后可继续应用；
- **Commit Reconciliation**：通过 `requestId` 或章节号查询不确定投递结果；
- **Revision CAS**：按正文 Hash / revision 防止并发覆盖，自动保留旧版本；
- **动态状态**：Character、Knowledge、Inventory、Location 四类状态；
- **三级记忆**：short / mid / long，本地中文 n-gram + TF-IDF 检索；
- **长期台账**：Causal Event、Foreshadowing、Promise、Relationship、Opposition Clock、Chapter Signature、Arc Audit、Outline Drift；
- **Closure**：记录每章提交后各类台账是否真正更新，并附持久化证据；
- **Integrity Check**：检查章节、摘要、Delta、Meta、Audit、Quality、Closure、Receipt、状态、记忆和台账 Hash；
- **旧项目懒迁移**：历史章节不会因为新门禁被追溯性判死，新门禁从升级时的 `nextChapter` 起生效。

## 33 个工具

### 项目与配置

- `novel_project_create`
- `novel_project_list`
- `novel_project_status`
- `novel_project_configure`
- `novel_project_config_read`

### 参考资料与规划

- `novel_reference_import`
- `novel_reference_next_batch`
- `novel_reference_analysis_batch`
- `novel_reference_record_batch`
- `novel_artifact_write`
- `novel_artifact_read`
- `novel_idea_bank_write`
- `novel_creativity_review`

### 长线故事状态

- `novel_causal_event_record`
- `novel_foreshadowing_upsert`
- `novel_foreshadowing_due`
- `novel_story_ledger_upsert`
- `novel_story_ledger_query`
- `novel_dynamic_state_update`
- `novel_dynamic_state_context`
- `novel_memory_record`
- `novel_memory_search`

### 审计、提交与修订

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

## 推荐生产链路

```text
project_status + project_config_read
              ↓
       prepare_chapter
              ↓
        Writer 正文
              ↓
  17项 logic audit record
              ↓
Continuity Auditor + Reader Editor
              ↓
   chapter_quality_record
              ↓
 commit_chapter(requestId)
              ↓
不确定结果 → commit_status
              ↓
ledgers + dynamic state + memory
              ↓
       closure_record
              ↓
      integrity_check
```

## 持久化目录

默认项目数据在：

```text
~/.openclaw/data/novels/<projectId>/
```

插件升级不会删除该目录。新增主要文件：

```text
project-config.json
chapters/meta/
story/quality/
story/closures/
story/dynamic/state.json
story/memory/index.json
story/ledgers/
requests/
receipts/
transactions/
versions/chapters/
```

## 旧项目升级策略

若旧项目没有 `project-config.json`，首次访问时插件读取当前 `state.nextChapter`，将其保存为 enforcement boundary：

- 之前章节：允许缺少 V5 新增的 Meta、Quality、Closure 等，只在完整性报告中给出 grandfathered warning；
- 边界章节及以后：执行完整 V5 门禁；
- 旧章节一旦被修订：新正文必须经过当前 Revision Audit / Quality / Hash 规则。

因此不要手动把 boundary 改成 1，除非已经为全部历史章节补齐相应凭证。

## 开发验证

```bash
npm run verify
npm run pack:check
```

`verify` 会重新构建 `dist/`、运行真实 Node 测试并检查 package / manifest / tool registration 是否一致。

在安装到 OpenClaw 后，再运行：

```bash
openclaw plugins inspect novel-engine --runtime --json
```

确认 33 个工具成功注册后重启 Gateway。

## 已知边界

- 本地 memory search 是 n-gram + TF-IDF，不是向量数据库；
- 服务端能验证三份 reviewer receipt 使用不同 session ID，但无法仅凭 ID 证明编排层真的启动了三个物理隔离上下文；
- 语义审稿仍由模型判断，插件负责结构、Hash、门禁、事务和持久化；
- 文件型存储采用项目级串行写锁，优先保证可靠性，不适合多个写入者同时高频修改同一项目；
- `repair:true` 只做安全修复，不会猜测或自动改写小说事实。
