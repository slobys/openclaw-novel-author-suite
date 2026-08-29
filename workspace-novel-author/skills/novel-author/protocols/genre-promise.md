# Genre Promise / Reader Experience Protocol V5.0

目标：防止作品越写越“逻辑正确”，却越来越不像读者最初点开的那本书。

## 项目级画像

从冻结企划提取读者体验，而不是每章机械配额：

```json
{
  "primaryExperiences": {
    "comedy": {"target": 7, "floor": 5},
    "adventure": {"target": 5, "floor": 3}
  },
  "secondaryExperiences": ["mystery", "growth"]
}
```

## Chapter Signature 增补

```yaml
experienceScores:
  comedy: 7
  adventure: 5
  mystery: 4
plannedBeatIds: [V1-C21-B1, V1-C21-B2]
fulfilledBeatIds: [V1-C21-B1]
deferredBeatIds: [V1-C21-B2]
newBeatIds: []
bodySha256: "..."
```

分值 0–10 表示“本章给读者的实际体验强度”，不是质量分。不要为了过 Gate 硬塞笑点、战斗或反转。

`genre_promise.py` 看最近 5 章滚动体验。一般低于 floor 只报警；连续 3 章严重低于 floor 或窗口整体崩塌才硬阻断，并要求调整当前章或未来规划。
