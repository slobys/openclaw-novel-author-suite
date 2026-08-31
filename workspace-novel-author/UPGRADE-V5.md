# Novel Author V5.0 升级说明

本版本以 Codex 优化后的 V4.1 为基线，保留其 CAS/revision、payload gate、reconciling、closure outbox 和 runtime guard，再补齐长篇小说生产缺口。

## 本次新增

1. 修复 `narrative_fatigue.py`：低强度连续章节不再误报“连续高强度”。
2. `chapter_length.py` 改为接受 resolved hard/target 参数，项目级字数规则真正覆盖默认值。
3. 新增人物 / Knowledge / Inventory / Location 四类动态派生状态 `dynamic_state.py`。
4. 新增 short / mid / long 三级记忆与中文 n-gram TF-IDF 检索 `memory_index.py`。
5. 新增两个独立审稿上下文的 deterministic receipt：`independent_audit_gate.py`。
6. 新增 Genre Promise / Reader Experience 滚动门禁：`genre_promise.py` + `quality_gate.py`。
7. 保留并强化 V4.1 的 `reconciling`，Quality Gate 进入 Precommit 前也绑定正文 Hash。
8. 新增稳定 Beat ID 与 `outline_drift.py`，每 5 章检查计划/实际偏移。
9. Closure 默认加入 `dynamic_state` 与 `memory_index` 两个派生闭环动作。
10. 附带 `companion/novel-engine-v0.3.0-patch-only.zip`，用于服务端 2600 汉字/Hash/requestId 硬门禁。

## 安装建议

- 先备份当前 workspace。
- 用本包内容替换小说 Agent workspace；不要删除 novel-engine 的项目数据目录。
- 若尚未安装 server-gate，单独备份 novel-engine 插件后，再使用 `companion/novel-engine-v0.3.0-patch-only.zip` 覆盖对应插件文件并重启 OpenClaw。
- 重启后先检查 novel-engine runtime 能力；只有真实验证后才能把服务端 Gate 标记为已启用。

## 测试

在 workspace 根目录运行：

```bash
python3 -m unittest discover -s skills/novel-author/tests -p 'test_*.py' -v
python3 -m py_compile skills/novel-author/scripts/*.py
```
