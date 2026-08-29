# Emotional Arc + Narrative Fatigue Protocol

目标：防止“每章都有事发生，但连续读情绪和功能完全同质”。

## Chapter Signature
每章规划/提交后维护：

```yaml
chapterSignature:
  chapterNo: 21
  function: investigation|confrontation|recovery|reveal|decision|travel|training|heist|battle|relationship|aftermath|setup
  sceneTypes: [dialogue-confrontation, exploration, chase]
  conflictMode: social|physical|mystery|resource|moral|internal|political
  openingEmotion: {name: unease, intensity: 4}
  midpointEmotion: {name: hope, intensity: 6}
  closingEmotion: {name: shock, intensity: 9}
  emotionalTurn: "希望被代价反转"
  hookType: question|threat|reveal|choice|deadline|arrival|loss|payoff
  promiseActions: ["P003:touch"]
  relationshipActions: ["顾禾-林满仓:trust_down"]
  informationAction: reveal|conceal|reinterpret|confirm|misdirect|none
  irreversibleChange: ""
  experienceScores: {comedy: 7, adventure: 5, mystery: 4}
  plannedBeatIds: [V1-C21-B1]
  fulfilledBeatIds: [V1-C21-B1]
  deferredBeatIds: []
  droppedBeatIds: []
  newBeatIds: []
  bodySha256: "..."
```

## 情绪规则
- 情绪不是越高越好；高强度必须有低谷、缓冲或反差才能保持效果。
- 连续 3 章 closingEmotion 强度都 >=8，通常应检查是否“持续喊高潮”。
- 连续 3–4 章同一 dominant emotion 或同一 emotionalTurn，视为疲劳风险。
- 一章至少应有一次可感知的情绪方向变化，但不要求机械三段式。

## Narrative Fatigue
`narrative_fatigue.py` 读取最近章节 Signature，检测：
- function 重复率和连续 run；
- hookType 重复；
- conflictMode 重复；
- sceneTypes 多样性；
- closingEmotion 强度过于单一；
- Promise 只 open/touch、缺少 payoff；
- Relationship action 长期为空；
- irreversibleChange 长期为空。

脚本输出是预警，不自动判定正文质量。语义层最终由 Arc Audit 决定。
