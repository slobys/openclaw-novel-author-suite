# Copy-ready Portable Hard-Lock Asset Card

## {asset_id}｜{asset_name}

**用途：** {purpose}

**输出模式：** `PORTABLE_HARD_LOCK`（可复制到新会话或其他模型）

**本张必须/建议实际上传的参考图：**

- R1 `{layout_id}` — 空间/拓扑权威 — 最高优先级
- R2 `{blockout_id}` — 体块/楼层/高差权威 — 复杂3D时使用
- R3 `{master_id}` — 建筑外观/材质/色彩权威
- R4 `{previous_id}` — 相邻视角共享地标 — 不覆盖当前机位
- R5 `{subject_id}` — 移动主体身份 — 有主体时使用

> 只有在当前目标模型请求中实际上传的图片才是有效参考。资产名称、“上一张图”或聊天记录不会自动把图片内容带到另一个窗口。

```text
【PORTABLE HARD LOCK｜独立可用｜禁止删减】
LOCK_ID: {lock_id}

【STYLE LOCK｜固定原文】
{style_lock_text}

【SCENE DNA｜固定原文】
{scene_dna_lock_text}

【SPATIAL LOCK｜固定原文】
{spatial_lock_text}

【CONTINUITY LOCK｜固定原文】
{continuity_lock_text}

【CURRENT ASSET】
{current_asset}

【WORLD RELATIONSHIPS FOR THIS VIEW】
{world_relationships}

【CAMERA SETUP】
{camera_setup}

【VISIBLE / OCCLUDED LANDMARKS】
{visibility}

【REFERENCE INPUTS｜需实际上传】
{reference_inputs}

【MOVING SUBJECT / TRANSITION】
{moving_subject_transition}

【TARGETED RESTRICTIONS】
{targeted_restrictions}
```

**硬锁预检：** Banner在首行｜LOCK_ID存在｜四锁齐全且逐字一致｜动态段落齐全｜参考图明确要求实际上传｜无“同上/沿用前文”悬空依赖。

生成后可回复：`锁定并下一张`、`检查连续性`、`重做当前图：<问题>`。
