# 系列风格交接合同

本合同确保 `novel-producer` 到 `drama-producer` 的交接不会改写或丢失用户风格要求。

## 权威与边界

- `authority` 固定为 `drama-producer`。
- `novel-producer` 原样传递用户要求，只能补充 `story_visual_context`。
- `story_visual_context` 只描述时代、地域、情绪、环境、叙事锚点和可选色彩，不能改变 2D/3D、写实度、线条、笔触或明确禁用方向。
- `drama-producer` 是唯一具体风格解释、图片提示词编译与生产执行权威。

## 新项目字段

`plan/format_strategy.json` 使用 `schema_version: 1.2`，并包含 `style_handoff` 与 `style_handoff_sha256`。

```json
{
  "style_handoff": {
    "contract_version": "1.0",
    "authority": "drama-producer",
    "mode": "user_locked",
    "raw_user_request": "国风半写实厚涂 2D",
    "source": "user_explicit_request",
    "must_preserve": ["2D", "国风", "半写实人物比例", "厚涂绘画材质"],
    "must_not_transform_to": ["3D", "2.5D", "真人摄影", "PBR游戏CG", "赛璐璐平涂"],
    "story_visual_context": {
      "tone": ["克制", "紧张"],
      "environment": "东方幻想荒原与废弃苗圃",
      "suggested_palette": ["灰青", "土褐", "暗金"]
    },
    "reference_assets": []
  },
  "style_handoff_sha256": "canonical JSON SHA256"
}
```

哈希按 UTF-8 canonical JSON 计算：`sort_keys=true`、`ensure_ascii=false`、`separators=(',', ':')`。

## 模式

- `user_locked`：用户明确指定风格。`raw_user_request`、`source=user_explicit_request`、`must_preserve`、`must_not_transform_to` 必填。
- `downstream_auto`：用户没有指定风格。具体实现由 `drama-producer` 决定；不得写 `user_confirmed=true`。
- `reference_locked`：用户明确确认参考图。`reference_assets` 必须包含稳定 `asset_id`、正整数 `file_size` 与 64 位 SHA256。

只有实际用户消息明确选择方案或参考图时，才能写 `user_confirmed=true`，并同时保存 `confirmation_evidence.type=user_explicit_selection` 与非空 `source_excerpt`。

## 分集继承

每个 `episodes/episode_XXX.json` 必须写 `style_handoff_sha256`，并与系列合同一致。单集不得复制后自行改写合同。用户后续明确变更风格时，先升级系列合同版本，再更新尚未派发分集；不得回写已完成历史。

## 资产任务 Gate

- 顶层携带 `style_contract` 与 `style_contract_sha256`。
- 每个 `prompt_zh` 前置 `【系列风格硬约束】`。
- 每个资产填写 `negative_prompt`，覆盖 `must_not_transform_to`。
- 回调后做整批并列风格审核；核心人物或主场景任一漂移，不进入视频。

Schema 1.1 及以前且没有 `style_handoff` 的历史项目只读兼容，不得把旧自动决策重新标记为用户确认。
