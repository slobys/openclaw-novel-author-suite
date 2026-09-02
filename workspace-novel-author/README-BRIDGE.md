# Novel Author V6.1 Balanced-Fast ↔ Novel Engine 0.6.0

本包覆盖 Agent 控制文档、工作流、Novel Author Skill、独立审稿协议、`independent_audit_gate.py` 及对应测试；不会覆盖你的小说项目、`memory/` 或 `exports/`。

## 使用顺序

1. 先安装并验证 Novel Engine `0.6.0` 完整目录；
2. 备份当前 `workspace-novel-author`；
3. 将本包目录结构覆盖到 Agent workspace 根目录；
4. 运行 Agent Skill 测试；
5. 重启/重新打开 Agent，使新的 `AGENTS.md` 和工作流生效。

只覆盖 Workspace 文件时不需要重启 Gateway，新建 `novel-author` 会话即可。若同时修改 Novel Engine 的全局默认配置，则先执行配置校验，再安全重启 Gateway。

## 篇幅配置

已有项目不会因覆盖 Workspace 自动改变项目配置。对需要迁移的项目，先调用 `novel_project_config_read` 取得当前 `revision`，再用同一 revision 调用 `novel_project_configure`，仅更新：

```json
{
  "writingContract": {
    "minHanChars": 2000,
    "targetMinHanChars": 2600,
    "targetMaxHanChars": 3200
  }
}
```

修改后必须重新读取配置确认。`targetMinHanChars=2600` 在 Agent 流程中表示理想目标，不是强制扩写线；只有 `minHanChars=2000` 是服务端提交硬下限。

若希望以后新建的所有小说默认采用此规格，还需把 `openclaw.json` 中 `plugins.entries.novel-engine.config` 的三个默认值设为：

```json
{
  "minChapterHanChars": 2000,
  "targetChapterHanChars": 2600,
  "targetChapterHanCharsMax": 3200
}
```

## 主要变化

- dynamic state、三级 memory、Signature、Closure 不再只存本地派生缓存，而由 Novel Engine 0.6.0 持久化；
- 工具受限 Writer/Reviewer 只返回严格 JSON，由父会话使用真实 session ID、正文与 `materialize_session_handoff.py` 落盘并绑定 Hash；
- reviewer checks 在本地 Gate 中标准化为 Engine 可识别的状态对象，禁止 `pass：说明` 导致的重复 Quality 失败；
- 默认篇幅改为硬下限 2000、理想目标 2600、建议上限 3200；达到 2000 后不再为了凑目标字数自动扩写；
- 自动扩写仅允许一次，并通过修订前后正文 Hash 防止重复粘贴相同正文。
- Independent Quality 必须调用 `novel_chapter_quality_record`；
- 不确定提交必须调用 `novel_commit_status`；
- commit 后必须执行服务端 Closure 和 `novel_project_integrity_check`；
- 修订必须使用正文 Hash + revision CAS。
- 17 类章节总审计与两个 reviewer 的 7/6 项检查已明确分离；
- 普通章节审稿默认 medium，同章修订优先复用原审稿会话；
- note/warning 不自动修订，Schema/Payload 错误不触发语义重审；
- 每章最多一轮自动定点修订，避免无限重试与 Token 浪费。
- Genre Gate、Signature 与两个 reviewer 的正文 Hash 在首次 Quality 提交前一次对齐；本地 Genre Gate 回执可直接满足 Engine 的 `pass/bodySha256` 契约。
- Closure evidence 固定为逐 operation 的项目相对 JSON 路径；格式纠错不会重复写入已经成功的派生台账。
