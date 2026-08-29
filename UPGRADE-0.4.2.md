# Novel Engine 0.4.2 升级说明

## 修复内容

- `novel_chapter_closure_record.operations.*` 的公开工具 Schema 改为单一对象结构：`{ status, evidence, reason, note }`。
- 不再向 OpenClaw 暴露容易被错误压缩为字符串枚举的 `string | object` 联合 Schema。
- Engine 内部仍接受旧字符串状态输入，已有项目和历史 Closure 数据不需要迁移。
- `novel_chapter_quality_record` 的 `genreGate` 与 `signature` 改为显式 Hash 绑定 Schema，减少 Payload 猜测和无效重试。

## 部署边界

本次升级只替换插件代码，不修改 `projectsRoot` 下的小说项目数据。替换后必须重启 Gateway，才能刷新已注册的工具 Schema。

## 第一章恢复步骤

1. 读取 `novel_chapter_closure_status`，确认第一章仍为 `pending` 且正文 Hash 一致。
2. 使用 8 个对象分支一次调用 `novel_chapter_closure_record`；`completed` 必须提供真实 JSON 证据路径。
3. 读取 Closure 状态，确认 `status=complete` 与 `closurePass=true`。
4. 调用一次 `novel_project_integrity_check(repair=false)`，确认 `integrityPass=true`。
5. 不重新审稿、不重新提交第一章、不重建派生记录。
