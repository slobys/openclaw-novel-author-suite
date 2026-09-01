# Novel Engine 0.4.8 / Novel Author V5.4.1

本版本修复隔离 Writer 在 OpenClaw 叶子子会话中因缺少文件、命令、Novel Engine 和会话工具而无法启动的问题。

## 主要变化

- Writer 与两个 Reviewer 不再直接写 Workspace、执行命令、调用 `novel_*` 或创建子会话；
- Writer 只返回 `novel-writer-return-v1` JSON，包含标题、计划、正文和17类随稿审计；
- Reviewer 只返回 `novel-review-return-v1` JSON；
- 父会话新增 `materialize_session_handoff.py`，用真实 child session ID 与 canonical SHA-256 生成 evidence 文件；
- 子会话缺少文件、命令、`novel_*` 或 session 工具不再被启动 Gate 误判为运行时故障；
- Engine `commit_status=not_found` 时，旧会话草稿只作为候选稿交给新的 Writer session，不恢复已经取消或失去控制权的旧任务；
- 保留逐章 Writer 隔离、三个不同 session ID、17类随稿审计、两个独立审稿和完整服务端闭环。

## 更新

```bash
curl -fsSL https://raw.githubusercontent.com/slobys/openclaw-novel-author-suite/v0.4.8/install.sh | bash
```

安装器会备份即将覆盖的 Workspace 文件，不删除小说项目、正文、`memory/`、会话、导出或 `.novel-runtime/`。

更新后建议新建一个 `novel-author` 主会话，使新的 `AGENTS.md`、`TOOLS.md` 和工作流完整生效。历史中未提交的草稿不要删除，可按 `tool-limited-sessions.md` 的恢复规则交给新 Writer 使用。
