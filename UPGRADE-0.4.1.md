# Novel Engine 0.4.1 / Novel Author V5.2 升级说明

## 必须同时替换

- `novel-engine` 整个插件目录；
- `workspace-novel-author` 整个 Workspace 目录。

不要只替换 `AGENTS.md` 或单个脚本。0.4.1 同时修改了工具 Schema、Engine 返回回执、Python Hash 契约和 Agent 状态机证据契约。

## 关键兼容变化

- `novel_commit_chapter` 与 `novel_revise_chapter` 的 `requestId` 现在必填；
- Commit/Revision 回执同时返回 `confirmed`、`chapterNo`、`requestId`、`bodySha256`，可直接交给 `job_state.py`；
- 正文 Hash 统一为：换行规范化为 LF，去除首尾空白，按 UTF-8 计算 SHA-256；
- Reviewer 必须提交正文 Hash、完整角色检查项和 issues 数组；Genre Gate 与 Signature 必须非空并绑定正文 Hash；
- 新项目默认启用 `requireClosureReceipt=true`；每个 Closure 操作必须明确 completed 或带理由 skipped；
- 修订正文的 Audit/Quality 在修订事务完成前只进入 history staging，不再覆盖当前章节指针；
- Engine 内置 Skill 改名为 `novel-engine-operations`，Workspace 继续独占 `novel-author`。

## 旧项目必须检查

已有项目的 `project-config.json` 会保留原设置。如果其中 `quality.requireClosureReceipt=false`，升级后能力 Gate 会阻止正式续写。应先读取 `novel_project_config_read`，再使用当前 revision 调用 `novel_project_configure`，至少确认：

```json
{
  "quality": {
    "requireChapterAudit": true,
    "requireCompleteAuditChecks": true,
    "requireQualityGate": true,
    "requireRevisionAudit": true,
    "requireRevisionCas": true,
    "requireClosureReceipt": true
  }
}
```

随后重新调用 `novel_project_status`，保存完整 JSON 并运行 Workspace 的 `server_capability_gate.py`。

## 重启与验证

上传替换完成后执行：

```bash
openclaw config validate
openclaw gateway restart --safe
openclaw plugins inspect novel-engine --runtime --json
```

若安全重启提示仍有 active/queued operation，应等待排空后确认 Gateway 已重新加载 0.4.1，不要在旧运行继续提交章节。
