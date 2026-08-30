# 从 v2.7 升级到 v2.8

v2.8 保留 v2.7 的人工 Gate、空间阻挡、提示词结构、HTML 模板和全部参考文件，不删除原功能。

新增：

1. `handoffs/scene_asset_handoff.json` 的 AUTO 强制输入；
2. `verified_reuse_asset_ids` 合并进入 `assets/actual_asset_manifest.json`；
3. `shots/shot_scene_bindings.json`；
4. `gates/shot_scene_binding_gate.json`；
5. `video_prompts/video_prompt_manifest.json`；
6. `scripts/validate_shot_scene_bindings.py`；
7. AUTO 生成 clip 时长统一为 4–15 秒；1–3 秒仅作为内部镜头；
8. prompt group 不得跨 Scene / location asset。

原有 text-only 输出和 HTML 输出仍然保留。

## 安装

直接用整个 v2.8 目录内容覆盖：

```text
${OPENCLAW_SKILLS_DIR}/deepwhite-shotlist-builder-zh-user
```

不要多套一层目录。
