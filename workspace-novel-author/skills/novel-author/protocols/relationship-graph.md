# Relationship Graph Protocol

人物关系不是静态标签，而是会被事件改变的状态边。

## 建议结构

```yaml
relationshipGraph:
  edges:
    - a: "顾禾"
      b: "林满仓"
      stage: stranger|contact|ally|fragile-alliance|friend|intimate|rival|enemy|broken
      trust: 62
      respect: 71
      affection: 48
      fear: 8
      dependency: 35
      resentment: 17
      powerBalance: 5
      secretDebt: 2
      unresolved:
        - "顾禾隐瞒了矿洞真相"
      publicFace: "公开合作"
      privateReality: "互相试探"
      lastChangedChapter: 5
      evidence: "第5章共同承担后果"
```

## 数值说明
0–100 仅用于连续性和变化方向辅助，不是心理学精确测量。

一般单章变化建议：
- 轻微事件：±1–5；
- 明显事件：±6–15；
- 重大背叛、救命、牺牲、公开决裂：可更大，但必须有正文证据。

## 使用规则
- 只有正文实际发生足以改变关系的事件才更新。
- 写关键对话前读取当前 stage、unresolved 和 powerBalance。
- 关系变化不能只靠一句“他们更信任彼此了”；必须在选择、资源、秘密、牺牲、风险或行为中留下证据。
- 关系可以多轴矛盾：信任下降但尊重上升、依赖上升但怨恨也上升，这比简单“好感度”更真实。
- Voice Profile 与 Relationship Graph 联动：同一个角色面对不同关系对象，说话方式允许不同，但不能违背其稳定人格。
