# Upgrade 0.4.7

Novel Engine 0.4.7 / Novel Author V5.4.0 是安装兼容性修复版，业务数据结构、章节流程和 Agent 行为不变。

## 修复内容

- 兼容 OpenClaw 2026.8.1 新增的插件能力授权：安装和启用 `novel-engine` 时显式传入 `--accept-capabilities`。
- 插件授权在读取 Agent roster 之前完成，可恢复“插件已经更新、但 CLI 因尚未授权而拒绝启动”的半完成安装。
- 兼容不支持该参数的旧版 OpenClaw：只有在 CLI 明确报告参数不存在时，安装器才回退一次旧命令；其他失败不会自动重试。
- 重复安装继续复用既有 `novel-author` Workspace，并保留 `memory/`、`exports/`、`.novel-runtime/`、会话及小说项目数据。

## 更新命令

```bash
curl -fsSL https://raw.githubusercontent.com/slobys/openclaw-novel-author-suite/v0.4.7/install.sh | bash
```

OpenClaw 2026.8.1 及以上会显示第三方 Git 插件的信任提示。`--accept-capabilities` 表示安装者明确接受该版本清单中声明的 Novel Engine 工具能力；请只从你信任的仓库和固定标签安装。
