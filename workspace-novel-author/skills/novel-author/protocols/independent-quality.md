# Independent Quality Gate Protocol V5.4.1 Tool-Safe Isolation

目标：用两个真实隔离审稿上下文降低作者自证偏差，同时限制重复审稿、无效重试和 Token 消耗。

## 审计层级不可混用

`requiredAuditCategoryCount=17` 只属于 `novel_chapter_audit_record` 的章节总审计，不属于 `novel_chapter_quality_record` 中任何一个 reviewer 的 `checks`。

最终正文 Hash 固定后，使用两个与 Writer 不同的真实隔离 session：

### Continuity Auditor

只接收最终正文、正文 Hash 与必要事实包，不接收 Writer 的创作理由。`reviewerRole` 必须是 `continuity-auditor`，`checks` 必须覆盖且只需覆盖：

`facts`、`timeline`、`knowledgeBoundary`、`stateContinuity`、`causality`、`promiseContinuity`、`relationshipContinuity`。

### Reader Editor

只接收最终正文、正文 Hash 与类型体验要求。`reviewerRole` 必须是 `reader-editor`，`checks` 必须覆盖且只需覆盖：

`readability`、`pacing`、`repetition`、`genreExperience`、`hookQuality`、`characterAgency`。

两个结果都必须包含：`reviewerRole`、真实 `reviewerSessionId`、`bodySha256`、`conclusion`、`issues`、`checks`。Writer 与两个 reviewer 的 session ID 必须两两不同。

## 非阻断建议

- `note`、`warning` 不自动触发正文修改；放在 `issues` 中供后续章节或世界观确认使用。
- required `checks` 推荐用 `pass` 表示该维度没有阻断问题；兼容 `note`/`warning`/`not_applicable`，但不得省略必需检查项。
- 只有 `error`、`block`、`fatal`，或 `conclusion=revise/block` 才阻断 Quality。
- 不得为了达到机械比例、消除主观 warning 或美化评分而修改已经合格的正文。

## Reviewer checks 的精确结构

`checks` 的每个值只能是“状态”，不能是审稿说明。标准写法为对象：

```json
{
  "checks": {
    "facts": {
      "status": "pass",
      "evidence": "人物、器具与既有事实一致"
    }
  }
}
```

`status` 只允许 `pass`、`note`、`warning`、`not_applicable`。也兼容仅传精确状态字符串，例如 `"facts": "pass"`，但禁止以下格式：

- `"facts": "人物与前文一致"`；
- `"facts": "pass：人物与前文一致"`；
- `"facts": "pass: consistent"`；
- 缺少角色所需的任一检查项。

说明文字放在对象的 `evidence`；非阻断建议放在 `issues`。不得把状态与说明拼接成一个字符串。

## 会话生命周期与复用

普通章节默认 `context=isolated`、`thinking=medium`。用户明确要求、卷末、重大转折或终局等关键章才使用 `high`。

首次审核：

1. 分别调用 `sessions_spawn`；
2. 保存每次返回的 `runId` 与 `childSessionKey`；
3. 两次均为 `accepted` 后调用 `sessions_yield`，等待推送事件；
4. 恢复后用 `subagents`/`sessions_list` 对账，用 `sessions_history` 读取最终结论；
5. 保存真实 session 标识和绑定正文 Hash 的审稿 JSON。

同章修订：

- 旧审稿内容因 Hash 改变而失效，但原 reviewer session 不失效；
- 优先用 `sessions_send` 把新正文、新 Hash 和必要事实包交回原两个 reviewer，要求忽略旧结论并重新完整审核；
- 只有原会话不可访问、失败、超时或角色错误时才新建替代 session；
- 每章最多一轮自动定点修订，第二轮必须等待用户决定。

## Payload 错误不是语义失败

首次调用 `novel_chapter_quality_record` 前，一次完成以下结构检查：

- `content` 的 canonical SHA-256；
- `continuityReview.bodySha256`；
- `readerReview.bodySha256`；
- `genreGate.bodySha256`；
- `signature.bodySha256`；

五处必须完全相同。`genreGate` 必须显式包含 `pass: true` 或 `genrePass: true`；本地 `genreGatePass: true` 不能替代 Engine 字段。`signature` 除 `bodySha256` 外至少保留一个真实章节体验或结构字段。推荐直接使用 `genre_promise.py` 的完整回执作为 `genreGate`，使用绑定当前 Hash 的 provisional Chapter Signature 作为 `signature`。

若 `novel_chapter_quality_record` 返回 Schema、参数或 Payload 错误：

1. 保留已经完成且 Hash 匹配的审稿结果；
2. 根据原始 error code、message、details 修正结构化 Payload；
3. 只允许重提一次同一 Quality 记录；
4. 禁止重新调用 `novel_logic_audit_prepare`、重跑 17 类语义审计或重新创建 reviewer；
5. 第二次仍失败则进入 `blocked`，向用户报告原始错误和去敏后的 Payload。

## 本地 Gate

运行：

```bash
python3 {baseDir}/scripts/independent_audit_gate.py \
  --body-file chapter.md --writer-session WRITER_SESSION \
  --continuity-review continuity.json --reader-review reader.json \
  --receipt independent-receipt.json
```

本地 Gate 与 Novel Engine 0.4.8 使用相同的 canonical reviewer roles、7/6 项检查范围、非阻断状态和正文 Hash 绑定规则。

Gate 成功后会在 `independent-receipt.json.engineReviews` 中生成标准化的 `continuityReview` 与 `readerReview`。调用 `novel_chapter_quality_record` 时必须原样使用这两个对象；Gate 之后禁止再次改写、补写或拼接 `checks`。若原始值是 `pass：说明` 或只有说明，本地 Gate 会在调用 Engine 前直接拒绝。
