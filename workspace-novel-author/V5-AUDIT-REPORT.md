# workspace-novel-author V5.0 审计报告

> 本文件保留 V5.0 历史审计记录。当前配套版本为 Novel Author V5.4.3 Codex Tool Projection / Novel Engine 0.4.10；默认篇幅为硬下限 2000、理想目标 2600、建议上限 3200，并增加逐章隔离 Writer、父会话确定性落盘、具体工具 ID 投射校验、幂等取消、自动修订次数、正文 Hash 变化和同稿循环阻断测试。

## 基线判断

本次以用户提供、经 Codex 优化的 V4.1 为基线。V4.1 已经具备：

- `TOOLS.md` 运行能力预检；
- `novel-author-workflow.yaml` 单一机器流程；
- 严格串行 job state；
- revision/CAS 防并发覆盖；
- `reconciling` 处理 commit 投递不确定；
- Payload Gate；
- Precommit Hash 绑定；
- Durable closure outbox；
- runtime file lock / atomic write；
- 基础单元测试。

这些改动全部保留，没有回退。

## 发现的剩余缺口

1. `narrative_fatigue.py` 仍会把连续 False 当作连续 True，导致低强度章节误报“持续高强度”。
2. 工作流声明“项目写作规格覆盖默认值”，但 `chapter_length.py` 仍写死 2600 / 3000–3400。
3. 缺少 Character / Knowledge / Inventory / Location 四类动态状态。
4. 缺少 short / mid / long 三级长期记忆与历史检索。
5. Writer 仍可在同一认知上下文里完成审稿，缺少独立 Continuity Auditor / Reader Editor。
6. 缺少 Genre Promise / Reader Experience 的滚动门禁。
7. V4.1 已加入 reconciling，此项无需重复实现，只需保留并与新 Quality Gate 对齐。
8. 缺少章纲稳定 Beat ID 和计划/实际 Drift Report。
9. 服务端硬门禁补丁不在 workspace 内，运行时无法自带安装材料。

## V5.0 已补齐

- 修复 Narrative Fatigue 高强度连续检测；
- `chapter_length.py` 支持 `--hard-min / --target-min / --target-max`；
- `dynamic_state.py`；
- `memory_index.py`，中文 2–3 字 n-gram + TF-IDF 轻量向量检索；
- `independent_audit_gate.py`；
- `genre_promise.py`；
- `quality_gate.py`；
- `outline_drift.py`；
- `server_capability_gate.py`；
- Job state 新增 `quality_gate`；
- Precommit Gate 强制绑定 Quality receipt；
- Closure 默认增加 `dynamic_state` 与 `memory_index`；
- 新增 5 个 V5 协议和 3 个模板；
- 历史版本曾以 companion patch 交付服务端门禁；公开版已由根目录 Novel Engine 0.4.10 直接提供，不再携带旧 ZIP 补丁。

## 权威边界

新增 state / memory 都放在 `.novel-runtime/derived` 的设计范围内，只是可重建检索缓存。`novel-engine` 与已提交正文继续是唯一业务事实源；发生冲突时派生缓存必须失效并重建。

## 测试结果

当前测试目录包含 25 个测试。已分组执行并确认通过，覆盖：

- 2000–3200 灵活区间、2600 理想目标 / 自定义 writing contract；
- Payload Gate；
- Precommit Hash / Required Checks / Quality receipt；
- 严格状态机、CAS、单 job、串行、多次失败熔断；
- closure outbox；
- concurrent signature upsert；
- Narrative Fatigue 误报回归；
- Dynamic State 最新状态合并；
- 三级记忆检索；
- 独立审稿 session 约束；
- Genre severe drift 阻断；
- Quality Gate；
- Outline Drift；
- Server capability gate。

另外完成了一次 2600 汉字的端到端本地 Smoke Gate：Payload → Independent Audit → Genre → Quality → Precommit，最终 `gatePass=true` 且正文 SHA-256 全链路一致。

## 推荐使用方式

公开版请使用仓库根目录的 `install.sh`。安装器只更新公共控制文件与 Skill，覆盖前自动备份同名文件，并保留 `memory/`、`exports/`、`.novel-runtime/`、会话和小说项目数据。
