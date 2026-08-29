# Promise / Payoff Ledger Protocol

Promise 是作品已经让读者主动产生的期待或问题，不等于所有伏笔。

## 建议结构

```yaml
promisePayoffLedger:
  items:
    - id: P001
      type: mystery|goal|relationship|threat|reward|identity|world|moral-choice
      promise: "读者被承诺的东西"
      readerQuestion: "读者现在最想知道什么"
      createdChapter: 3
      owner: "主线/人物/势力"
      strength: 8
      status: open|touched|partial|reinterpreted|paid|cancelled
      lastTouchedChapter: 7
      plannedTouches: [7, 11]
      payoffWindow: [13, 16]
      fairEvidence: ["已给出的公平证据"]
      payoffRequirement: "怎样的兑现才配得上承诺强度"
      notes: ""
```

## 使用规则
- `strength >= 8` 的 Promise 属于高强度承诺，不能长期无触碰。
- Promise 的动作只有：open、touch、partial-payoff、reinterpret、payoff、cancel。
- 不机械每章开新坑；当 OPEN 高强度 Promise 过多时，优先兑现或推进旧承诺。
- `cancel` 只能用于作品明确撤销该方向，并给读者足够解释；不能把忘记回收伪装成取消。
- Payoff 要与承诺强度匹配：强承诺需要事件、人物选择、代价或认知变化，不用一句解释草草结账。
- Arc Audit 检查 Promise Debt：高强度、超出 payoffWindow、长期未触碰的项优先进入未来 3–8 章规划。

## 与伏笔区别
- 伏笔：作者为了未来事件预先留下证据。
- Promise：读者已经意识到“这里会有答案/结果/兑现”。

一条内容可以同时是伏笔和 Promise，但必须分别管理“证据公平性”和“读者期待债务”。
