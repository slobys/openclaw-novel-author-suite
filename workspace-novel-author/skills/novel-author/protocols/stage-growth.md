# 可选阶段成长与世界展开

这是创作支撑，不是新增生产状态机。使用既有 `novel_artifact_write/read` 的 `artifactType=stage-plan`，路径 `blueprint/stage-plan.json`；更新使用实际 artifact SHA 的 CAS。无计划旧书无需迁移。

最小格式：

```json
{"schemaVersion":"novel-stage-plan-v1","stages":[{"id":"local","startChapter":1,"endChapter":12,"goal":"理解故障并承担修复后果"}]}
```

最多50阶段；id唯一safe key，整数章范围合法、不重叠，允许不完整覆盖。goal非空，单叙述字符串最多1000字符。可选叙述字段 `worldExpansion`；可选叙述数组 `growthDimensions/newRules/obstacles/costs`，每项非空、最多1000字符、每数组最多12项。可选ID数组 `foreshadowingIds/carryForwardPromiseIds/carryForwardRelationshipIds` 每组最多12项，关系ID沿用 `from::to`。`nextStageId` 必须指向计划中的后续阶段。可选 `bridgeToNext` 含非空 condition及foreshadowingIds/promiseIds；未知字段、坏JSON、重复id/重叠/坏引用均在写历史或state前拒绝。不要用大纲自由文本替代严格JSON。

Prepare 仅选当前阶段、一个next摘要及前一阶段的旧债/桥梁，返回实际plan path/SHA。`plannedStage` 的章范围只代表计划；`latestObservedStageId` 仅来自最近窗口中Hash绑定的committed signature，不由章号伪造。没有观察证据则null。

桥梁/继承IDs在真实伏笔、Promise、Relationship台账匹配，保留status、来源path/chapter/正文Hash；missing为没有记录，unresolved为尚无有效已提交证据。未来ID可合法规划，但本轮不自动建台账，不把planned当occurred/paid。到城市不清零村落关系、损失和未兑现承诺；世界展开可为知识、制度、关系或责任，不强制换地图/每章升级。

Writer看目标/成长/阻力/代价及桥梁旧债；Continuity看证据与旧债；Reader看功能/成长体验与来源，不接收Writer创作理由。必要ID/Hash、解析规格、完整审计和本章outline受保护；若角色预算装不下则明确返回预算错误，不靠总尾截断假装ready。使用既有窄查询或精简规划后再准备，不增加模型检查员或循环重写。
