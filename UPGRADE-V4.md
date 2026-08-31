# Novel Engine 0.3.0 V4 服务端硬门禁升级说明

本包基于用户提供的 `novel-engine 0.2.3` 运行包直接修改。原包没有 `src/`、`test/` 或构建脚本源码，只有 `dist/*.js` 编译产物，因此本次是在真实运行文件 `dist/engine.js` / `dist/index.js` 上完成可直接安装的补丁。

## 关键变化

- 新增 `minChapterHanChars`，默认 `2600`。
- 新增 `targetChapterHanChars`，默认 `3000`。
- `novel_chapter_audit_record(precommit)` 由服务端自行统计中文汉字；低于 2600 直接拒绝，无法保存 `pass` 审计。
- 审计文件由服务端保存 `contentHanChars`、`contentSha256` 和 `serverGate` 长度证明。
- `novel_commit_chapter` 在真正写文件之前重新统计汉字并验证：
  - 至少 2600 中文汉字；
  - 必须有 `pass` precommit（默认 requireChapterAudit=true）；
  - audit 不得含 `error` / `block`；
  - commit 正文 SHA-256 必须与审计正文完全一致；
  - audit 的服务端汉字数证明必须与 commit 正文一致。
- 同一个 `requestId` 被用于不同正文/摘要/continuityDelta 时直接拒绝，避免重连时错误复用。
- `novel_revise_chapter` 也执行 2600 中文汉字硬门禁，避免修订后把章节缩短到不合格状态。
- `novel_project_status` 会返回 `storyLedgers.chapterLengthGate`，方便确认服务端门禁是否真正生效。

## 兼容性

- 原来的 `minChapterChars` 仍保留，默认 800，只作为旧版“原始字符串长度”安全检查。
- 已经提交的旧章节不会被扫描、删除或改写。
- 升级前已经保存、但尚未提交的旧版 precommit audit 因没有新的服务端长度证明，commit 会要求重新执行一次 precommit audit。
- 写非中文小说时，可在插件配置中设置 `minChapterHanChars: 0` 关闭汉字硬门禁。

## 替换方法

1. 备份当前 `novel-engine` 插件目录。
2. 停止或重启前暂时不要运行小说写作任务。
3. 用本包内容完整替换原 `novel-engine` 插件目录内容。
4. 重启 OpenClaw Gateway。
5. 执行：

```bash
openclaw plugins inspect novel-engine --runtime --json
```

确认版本为 `0.3.0`。

## 生效验证

在小说 Agent 新会话中查询项目状态。正常应看到类似：

```json
{
  "chapterLengthGate": {
    "legacyMinChars": 800,
    "minHanChars": 2600,
    "targetHanChars": 3000,
    "enforcedServerSide": true
  }
}
```

之后正常写章即可。Agent 侧仍以 3000–3400 汉字为目标；2600 只是服务器最终红线。

## 本地验证结果

已对 `dist/engine.js` / `dist/index.js` 执行 Node 语法检查，并直接实例化 `NovelEngine` 完成以下测试：

- 2599 汉字 precommit：拒绝；
- 2600 汉字 precommit：通过并记录服务端长度证明；
- 2600 汉字 commit：通过；
- 审计后修改正文：SHA-256 不一致，拒绝；
- `pass` audit 含 `error`：拒绝；
- 人工篡改 audit 加入 `block` 后 commit：服务器二次检查并拒绝；
- 同 requestId + 相同载荷：幂等回放；
- 同 requestId + 不同载荷：拒绝。
