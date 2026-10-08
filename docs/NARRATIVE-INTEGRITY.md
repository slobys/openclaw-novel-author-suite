# 叙事台账确定性门禁（M1）

本轮补强的是小说事实的结构底线，不是“任意长篇永远没有语义矛盾”的保证。17 项 Writer 审计、独立 Continuity / Reader、正文 Hash、CAS、Closure、取消与恢复流程仍然必须执行。

## 因果图

- `causes`：前置事件 → 本事件。
- `enables`：本事件 → 后续事件。与 `causes` 使用相同图方向，不能通过换字段绕过检查。
- `occurred` 事件所依赖的 cause 必须存在、已经 `occurred`，且其章节正文绑定仍有效。不存在、仅计划、已取消、陈旧 Hash 的原因不是既成事实证据。
- `planned` 可以引用尚未登记的将来计划；尚未解析的引用在 Integrity 中是 warning，不是已验证事实。
- 已知节点之间不允许有向环，包括 `causes` 与 `enables` 混合构成的环。诊断包含 cycle path。
- 更新既有 cause 的状态，也会检查关联的 occurred dependents；不能把原因改回计划后留下“已发生结果”。
- **来源章号不等于故事世界时间。** 第 2 章回溯揭示的 occurred 事件可以作为第 1 章事件补录的原因；只要证据有效，不凭章号大小拒绝。同章先后、倒叙、人物动机与事件真正发生时间仍需语义审稿。

写入前检查变更关联的图，不因为无关旧坏组件就强迫全库迁移。完整项目 Integrity 仍报告所有明确矛盾，不自动删事件或改正文。环检测为迭代实现，避免长链递归栈溢出。

## 伏笔生命周期

| 当前状态 | 可以写入的状态 |
| --- | --- |
| 未登记 / planned | planned、open、cancelled |
| open | open、advanced、paid、cancelled |
| advanced | advanced、paid、cancelled |
| paid | paid（相同终态的恢复/重放） |
| cancelled | cancelled（相同终态的恢复/重放） |

- 未埋设的 ID 不能 advance / payoff / close；填写一个自称的 `plantedChapter` 不能代替已经登记的 open / advanced。
- `continuityDelta.foreshadowing` 和 `novel_foreshadowing_upsert` 共用同一状态机。整个 delta 先在副本上验证，失败不创建章节、事务或新台账。
- 同章的 `open → payoff` 合法；已回收/取消的条目不能被静默重新打开。新方向应使用新的稳定 ID，而不是改写旧线索历史。
- paid/cancelled 只接受相同**规范化业务载荷**重放：未提供字段继承旧值，字符串空白与 Hash 大小写按原规则规范化；notes、source/body、类型、解释、计划等终态事实不能借相同 status 重写。自动 updatedAt 不参与业务比较，显式原埋设证据重建有下述单独边界。
- 部分更新继承 `status`、`type`、`plantedChapter`、原解释与计划；不再把未给出的埋设章写成 null。
- 新 open 的实际埋设章默认是当前 source 章；planned 的预定埋设日期可以随实际写作调整。已经实际埋下的来源锚点不允许静默移位。
- 新 payoff 绑定本次来源章，之后不能悄悄改回收章。埋设不能晚于供读者接收的更新/回收来源章；这里约束发表证据次序，而非故事世界时间。

### 两份独立证据

当新 open 在其埋设来源章登记时，engine 自动保存 `plantedBodySha256`：

```json
{
  "id": "blood-key",
  "status": "paid",
  "plantedChapter": 1,
  "plantedBodySha256": "第一章原始正文的 SHA-256",
  "payoffChapter": 8,
  "sourceChapter": 8,
  "bodySha256": "第八章回收正文的 SHA-256"
}
```

推进/回收的最新 `bodySha256` 不覆盖原埋设 Hash；原埋设章修订后，Integrity 可以发现独立的 `FORESHADOW_PLANT_STALE_BINDING`。这两个 Hash 证明记录对应哪个正文版本，并不证明正文里真的出现公平线索；对应语义要由审稿判断。

旧合法条目没有新增可选 Hash 或旧 payoff 字段时不强制改写。已知埋设章但缺失历史 Hash 返回 `FORESHADOW_PLANT_PROVENANCE_LEGACY` warning，保留 unknown；不能用最新回收 Hash 伪造旧埋设证据。旧 paid 且明确无 plant 的矛盾则报错。

修订后，如果审稿确认新版本仍保留该线索，可以在 entry 显式传 `plantedBodySha256` 重建这一条来源绑定；两个公开工具的共享 entry schema 均声明此可选 SHA-256 字段。engine 验证它确实等于同一个 plantedChapter 的当前 committed Hash，并在 `plantedEvidenceHistory` 保留先前锚点。paid/cancelled 的明确 provenance 修订只可改变这一条 Hash 及自动历史，不能同时改 notes/source/payoff 等作品事实。若最新 source 本身也被修订，其独立绑定仍需有效，不能只重绑 plant 隐藏错误。自动部分更新不会重建；错误 Hash 会被拒绝。是否仍有公平线索、正文 span 的精确定位由语义审稿与后续证据模型负责，不由这个 Hash 重绑证明。

## 提交前预检与可恢复收尾

`novel_finalize_chapter` 在写正文前投影本次因果、伏笔 delta 和完整伏笔更新；明确无效的记录先失败，不让正文先提交再卡在 Closure。`commitChapter` 持锁再次检查相同 proposal。因果批次在项目锁下验证最终图并一次写入 graph 文件，避免逐节点执行时把尚未更新的旧边误判成环；新节点反向排列、已有 a→b 合法替换为 b→a 均可完成。步骤回执保持拓扑顺序，但顺序不是代替整批校验的安全条件。

伏笔 delta 实际涉及条目与显式 upsert 使用同一来源/plant Hash 检查；旧埋设章经真实修订后，advance/payoff 在正文、request、state 事务创建前拒绝。无关 legacy 条目不被强制全库迁移，本章尚未提交正文仅允许与精确 projected Hash 匹配的绑定。

已经 committed 的相同 requestId / 正文仍走原恢复路径：不重写正文、不重新做语义审稿，只继续剩余派生记录。已经执行的伏笔 delta 不再次降级已 paid 的状态；同一章同一正文的终态恢复不会被误判为 reopen。

这是**可恢复、非跨文件原子事务**，不是数据库事务。跨操作并发修改仍可能在实际写入时失败；继续遵守单项目单活动 Writer 与串行章节约束。旧 engine adapters 没有预检方法时只保留原兼容行为；本说明中的新增门禁由同步构建的 engine/finalizer 实现，不能仅更新 finalizer 后宣称获得能力。

## 常见错误

| code | 含义 / 处理 |
| --- | --- |
| CAUSAL_REFERENCE_NOT_FOUND | occurred 的 cause 没有台账事件；补充真实已提交事实，不编造原因 |
| CAUSAL_CAUSE_NOT_OCCURRED | 原因仅 planned 或 cancelled；检查场景与发生状态 |
| CAUSAL_SELF_REFERENCE / CAUSAL_CYCLE | 因果自引用/环；检查诊断的路径与真实因果方向 |
| SOURCE_BODY_HASH_MISMATCH | 消费了旧版本正文证据；依据修订后的真实审稿与证据重建 |
| FORESHADOW_TRANSITION_INVALID | 未埋设便回收，或终态倒退；修正本次计划/正文，不静默改历史 |
| FORESHADOW_TERMINAL_PAYLOAD_MISMATCH | paid/cancelled 不是相同业务载荷恢复；保留原终态事实，不借 request/body 重放修改说明或来源 |
| FORESHADOW_PLANT_IMMUTABLE | 试图改变已有真实埋设章 |
| FORESHADOW_PLANT_AFTER_SOURCE / FORESHADOW_PAYOFF_INVALID | 线索来源与回收锚点矛盾 |
| FORESHADOW_PLANT_STALE_BINDING | 原埋设正文已变；不要以新的 payoff Hash 洗白 |

失败时保留原 requestId，区分输入修正与已提交恢复；本次版本不会替作者自动改写作品事实。`repair=true` 仍只修可确定元数据，不伪造因果或伏笔。

## 验证与仍未完成的方向

回归覆盖公共 engine / real finalizer：未埋设回收、失败不落盘、部分继承、正常及同章生命周期、终态重放、missing/planned/cancelled 原因、混合环、长链、合法非线性叙述、原因陈旧 Hash、反向批次、commit 后中断恢复、历史诊断与 legacy 兼容。

本轮不声称完成：角色获知来源、世界时间模型、正文引用/spans、回收语义公平性、主线 Beat 的真实履行、快档检索必要旧事实、台账 revision 缓存失效、声明后 skipped 的全量 Closure 覆盖、跨文件批次原子性。下一阶段按研究与质量评测继续收紧这些具体缺口。
