# 场景视觉多样性策略

## 核心判断

视觉变化优先级：

1. **剧情真实换地点** → 必须换场景资产；
2. **同地点真实换子空间** → 通常换场景资产；
3. **环境状态显著变化** → 生成/切换 Variant；
4. **同空间长时间停留** → 先考虑构图、景别、反应、道具、人物关系；必要时再增加合理 Sub-location；
5. **禁止为了变化而瞬移。**

---

## 默认阈值

### 竖屏漫剧

```text
soft_limit_seconds = 24
hard_limit_seconds = 35
```

### 横屏影视化

```text
soft_limit_seconds = 35
hard_limit_seconds = 50
```

若没有可靠时长，不猜秒数；改用 Scene 数与剧情段落长度做人工/AI 风险判断。

---

## 超过 soft limit 怎么办

按顺序检查：

1. 剧本是否本来就发生了地点变化但未被识别？
2. 同一 Location 是否存在已写入剧本的子空间移动？
3. 是否有建立镜头/门外/窗边/柜台/院落等合理可视区域？
4. 是否可以靠镜头语言解决，而无需新资产？
5. 若仍保持单背景，记录合理性。

不要为了降低秒数机械生成新背景。

---

## 超过 hard limit

必须产生以下之一：

- `sublocation_enrichment`：新增一个合理子场景；
- `state_variant`：剧情确实发生显著环境状态变化；
- `single_location_justification`：明确说明为什么必须保持同背景，并把多样性责任交给 shotlist。

合法理由示例：

```text
整场为密室审讯，人物不能离开；空间限制本身就是戏剧压力来源。
```

不合法理由：

```text
省事。
已有一张图。
模型生成新背景太麻烦。
```

---

## 资产效率

以下情形优先复用：

- 同一房间、同一日夜状态；
- 同一街区的连续镜头且背景身份一致；
- 旧资产完全满足当前剧情；
- 新资产不会带来可见叙事收益。

以下情形值得新增：

- 新地点首次出现；
- 子空间承担新的动作/关系；
- 长期反复出现，能在后续多集复用；
- 重要高潮、身份揭示或世界观地点需要建立稳定视觉身份。

---

## Visual Variety Gate 输出建议

```json
{
  "risk_level": "low|medium|high",
  "long_same_background_runs": [
    {
      "asset_id": "AST-LOC-XXX",
      "scene_ids": ["SC01", "SC02"],
      "estimated_seconds": 31,
      "decision": "keep|split|add_sublocation|add_variant",
      "reason": "..."
    }
  ],
  "over_fragmentation_risks": [],
  "repairs_applied": []
}
```
