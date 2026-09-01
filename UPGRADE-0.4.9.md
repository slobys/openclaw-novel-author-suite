# Novel Engine 0.4.9 / Novel Author V5.4.2

本版本修复 `novel-author` 主会话因显式工具白名单缺少文件和命令能力，导致 Writer/Reviewer 已完成后仍无法运行本地 Gate、Quality 与 Commit 的问题。

## 主要变化

- 安装器读取当前 `novel-author` Agent 工具策略；
- 已存在 `tools.allow` 时保留原有条目，并补齐 `group:fs`、`group:runtime` 与套件必需工具；
- 没有显式白名单时使用 `coding`/现有 `full` Profile，并通过 `alsoAllow` 补齐 Novel Engine 与会话编排工具；
- 如用户明确通过 `tools.deny` 禁止文件或运行时能力，安装器停止并报告，不会擅自绕过安全策略；
- 新增首次安装、重复升级以及 deny 冲突三类安装器回归测试；
- 不修改小说项目、正文、审稿、Closure、记忆或会话数据。

## 更新

```bash
curl -fsSL https://raw.githubusercontent.com/slobys/openclaw-novel-author-suite/v0.4.9/install.sh | bash
```

安装后运行：

```text
/tools verbose
```

主会话应同时看到 `Read`、`Write`、`Exec`、`Process`、会话工具和 Novel Engine 工具。
