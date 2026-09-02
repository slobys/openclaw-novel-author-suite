# Tool-Limited Session Protocol V1

## 目的

隔离 Writer 与 Reviewer 是创作/判断角色，不是编排器。叶子会话缺少文件、命令、`novel_*`、`sessions_spawn`、`sessions_history` 或 `sessions_send` 属于正常安全边界，不得因此判定生产环境失效。

父会话负责：读取 Engine、创建/登记/取消会话、保存 completion、落盘、计算 Hash、运行本地 Gate、提交 Quality/Commit/Closure/Integrity。

## Writer 任务边界

父会话只向 Writer 发送：当前 profile 的 writer packet、本章号、篇幅/类型要求和下面的输出 Schema。普通章 packet 不得超过 16000 字符。不得发送本地路径、命令、Engine 提交步骤或“完成整套生产流程”等编排指令。

Writer 的唯一最终回复必须是一个 JSON 对象；允许外层单个 `json` 代码围栏，但不能附带其他说明：

```json
{
  "schemaVersion": "novel-writer-return-v1",
  "chapterNo": 17,
  "title": "不含第N章前缀的纯标题",
  "plan": {
    "alternativesConsidered": 2,
    "selected": "选择理由与推进方案",
    "beats": []
  },
  "body": "正文全文",
  "audit": {
    "decision": "pass",
    "checks": {
      "facts": "pass",
      "timeline": "pass",
      "space": "pass",
      "motivation": "pass",
      "knowledge": "pass",
      "worldRules": "pass",
      "resources": "pass",
      "causality": "pass",
      "foreshadowing": "pass",
      "originality": "pass",
      "voice": "pass",
      "sceneDynamics": "pass",
      "promiseFairness": "pass",
      "relationshipContinuity": "pass",
      "emotionCurve": "pass",
      "fatigueRisk": "pass",
      "oppositionPressure": "pass"
    },
    "issues": []
  }
}
```

Writer 可以省略 `bodySha256` 和 `writerSessionId`。若主动提供，父会话落盘器会严格校验，错误时拒绝落盘，不能口头纠正后继续。

通过项只写精确字符串 `"pass"`。不要为每个通过项写 evidence、description 或分析段落；只有真实问题才进入 `issues`。`plan.selected` 保持一句话，`beats` 只列必要 Beat，避免把正文分析再写一遍。

## 父会话接收 Writer

1. `sessions_spawn` 后登记真实 `taskId/runId/childSessionKey`；
2. completion 到达后先运行 job Guard；
3. 使用 `sessions_history` 读取唯一最终回复，原样写入 `writer-return-source.json`；
4. 执行：

```bash
python3 skills/novel-author/scripts/materialize_session_handoff.py writer \
  --input writer-return-source.json \
  --output-dir .novel-runtime/evidence/JOB/chapter-N \
  --chapter N \
  --writer-session-id REAL_CHILD_SESSION_ID
```

5. 再运行 `writer_handoff_gate.py` 与 `chapter_length.py`；
6. materialize/Schema/权限错误只修编排，不重新写正文；正文低于硬下限才把准确差额发回同一个 Writer 一次。

父会话不得自行润色或补写 `body`，不得自行把失败 audit 改成 pass。它只能补充可确定的 chapter、真实 session ID 和 canonical Hash。

## Reviewer 任务边界

两个 Reviewer 在同一阶段并行启动，接收同一 context snapshot 派生的对应 packet 与最终正文。Continuity packet 不超过 8000 字符，Reader packet 不超过 6000 字符。只返回：

```json
{
  "schemaVersion": "novel-review-return-v1",
  "chapterNo": 17,
  "reviewerRole": "continuity-auditor",
  "conclusion": "pass",
  "checks": {
    "facts": "pass", "timeline": "pass", "knowledgeBoundary": "pass",
    "stateContinuity": "pass", "causality": "pass",
    "promiseContinuity": "pass", "relationshipContinuity": "pass"
  },
  "issues": [],
  "summary": ""
}
```

通过项只写 `"pass"`，说明只放在真实 `issues` 中；`summary` 最多一句。Reader Editor 使用自己的 6 个必需 checks，不得照抄 Continuity 的 7 项。

父会话用真实 reviewer session ID 和当前正文文件执行：

```bash
python3 skills/novel-author/scripts/materialize_session_handoff.py reviewer \
  --input continuity-return-source.json \
  --output continuity-review.json \
  --body-file chapter.md \
  --chapter N \
  --role continuity-auditor \
  --reviewer-session-id REAL_REVIEWER_SESSION_ID
```

Reader Editor 同理。完成后才运行 `independent_audit_gate.py`。

## 历史草稿恢复

若 Engine `commit_status=not_found`，历史会话中的正文只能算候选草稿：

1. 不恢复已取消、被 kill 或已失去控制权的旧任务；
2. 将旧 job 完成取消对账，或标记为人工放弃；
3. 从历史会话只读取候选正文与可用审计，不把它们冒充 Engine 事实；
4. 为同一个 Engine `nextChapter` 创建新的 Writer session，把候选正文放入 compact 任务中要求采用、修订或重写；
5. 最终正文必须绑定新 Writer session，并重新完成两个独立审稿、Quality、Commit、Closure 与 Integrity。

这样既保留旧稿价值，也不会让旧任务、旧 session ID 或过期 Hash 混入正式提交。
