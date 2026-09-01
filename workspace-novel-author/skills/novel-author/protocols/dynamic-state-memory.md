# Dynamic State + Three-Tier Memory Protocol V5.2

目标：让 100–1000 章长篇仍能回答“谁在哪里、谁知道什么、物品归谁、旧伏笔何时出现”，同时只有一个权威事实源。

## 权威原则

- Novel Engine 0.4.9 的 `story/dynamic/state.json`、`story/memory/index.json` 和已提交正文是权威来源。
- `.novel-runtime/derived/` 仅是可删除的本地镜像；与 engine 冲突时立即丢弃并重建。
- 所有服务端派生记录必须绑定 `chapter/bodySha256` 或可追溯 `sourceRef/sourceSha256`。

## 四类动态状态

每章 commit 后根据实际变化调用 `novel_dynamic_state_update`：

- `characters`：位置、健康、目标、身份、能力、情绪、限制；
- `knowledge`：谁知道什么、通过何种证据、可信度与来源；
- `inventory`：物品持有者、位置、状态、数量、权限；
- `locations`：环境、控制权、可达性、危险、资源和变化。

`knowledgeKey` 应稳定，推荐 `{knowerId}::{factId}`。更新必须绑定本章当前 `contentSha256`，并使用 `expectedRevision` 做 CAS。

## 三级记忆

- short：最近 3–5 章、上一章行动、当前场景入口；
- mid：当前卷、最近 20–50 章、人物/关系/任务/地点阶段状态；
- long：早期事件、旧伏笔、关键对白、历史选择、地点、物品和长期 Promise。

用 `novel_memory_record` 记录，用 `novel_memory_search` 召回。服务端使用中文 2–3 字 n-gram + TF-IDF，是候选检索而非语义真相；召回内容必须与当前正文 Hash、时间线和动态状态交叉核对。

## Prepare

`novel_prepare_chapter` 已包含当前动态状态、三级记忆候选、最近 Signature、Promise、关系、对手时钟、因果和伏笔。只有资料包不足时再做窄查询，不要无条件重复加载全量状态。

## Existing-project bootstrap

升级旧项目时采用渐进回填：

1. short：最近 3–5 章；
2. mid：当前卷纲、最近 Arc Audit 和当前状态；
3. long：优先从因果、伏笔、Promise、Relationship、关键角色/地点回填；
4. dynamic state：以当前确定状态为基线，从最近章节补变化证据；
5. 更早章节按查询命中逐步回填。

没有来源的聊天印象不得进入服务端索引。

## 修订后的失效处理

章节修订后运行 `novel_project_integrity_check`。若出现 `DYNAMIC_STATE_STALE_BINDING`、`MEMORY_STALE_BINDING` 或 `LEDGER_STALE_BINDING`，必须按新正文 Hash 重建相关记录和 Closure，不能只修改本地镜像。
