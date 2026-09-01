# Novel Engine 0.4.10 / Novel Author V5.4.3

本版本修复 OpenClaw `/tools verbose` 显示文件与命令能力、但 Codex Harness 实际会话仍返回 `exec tool unavailable` 的工具投射问题。

## 根因

`v0.4.9` 只保证 `group:fs` 与 `group:runtime` 出现在 Agent 工具白名单。Gateway 策略层能够展开工具组，因此工具列表看起来正常；Codex Harness 的有限运行时白名单还需要具体工具 ID，只有组名时可能不会建立原生执行环境或 shell fallback。

## 修复

- 安装器同时保留工具组并显式加入：`read`、`write`、`edit`、`apply_patch`、`exec`、`process`；
- 安装器继续保留用户原有 allow 条目并做去重；
- 测试同时断言工具组和六个具体 Codex 工具 ID；
- Workspace 明确 OpenClaw 命令工具 ID 为 `exec`，不是 `exec_command`；
- `/tools verbose` 后还必须实际执行一次 `exec`/`pwd` 探针，避免策略层与运行时层状态不一致；
- 不修改小说项目、正文、审稿、Closure、记忆或会话数据。

## 更新

```bash
curl -fsSL https://raw.githubusercontent.com/slobys/openclaw-novel-author-suite/v0.4.10/install.sh | bash
```

更新并重启 Gateway 后应新建 `novel-author` 会话，再执行实际 `exec` 探针。
