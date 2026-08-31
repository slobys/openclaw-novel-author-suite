# Novel Engine 优化审计报告

> 本文件保留 0.4.0 历史审计结论。当前修复版为 0.4.1，部署与兼容变化以 `UPGRADE-0.4.1.md` 为准；当前 Engine 测试为 17 项。

审计对象：用户提供的 `novel-engine(1).zip`

原版本：`0.3.0`

升级版本：`0.4.0`

## 原版保留的优点

- 已有服务端中文汉字计数；
- 已有 precommit audit 与正文 SHA-256 绑定；
- 已有 requestId 幂等与 Payload 指纹；
- 已有项目级写锁、原子写入、因果与伏笔台账；
- 使用 `definePluginEntry` 和独立 manifest，整体插件形态正确。

## 原版确定存在的问题

1. `npm run check` 指向不存在的 `scripts/check-package.js`，会直接失败；
2. `npm test` 虽然返回成功，但测试目录为空，实际执行 0 个测试；
3. 发布包只有 `dist/`，缺少可维护源码；
4. 逻辑审计只有 10 项，不能覆盖 V5 Agent 要求的 voice、sceneDynamics、Promise、公平性、关系、情绪、疲劳和对手压力；
5. Writer 缺少服务端独立质量凭证，仍可能自己审自己；
6. 篇幅值只有插件全局默认，不能按小说项目设置；
7. Commit 依次写正文、摘要、Delta、State 和 request receipt，进程中断可能留下部分状态；
8. request receipt 写在提交末端，出现“正文已经保存、客户端没收到回执”时缺少明确对账工具；
9. 修订没有正文 Hash / revision CAS，也没有 requestId 幂等；
10. 没有 Character、Knowledge、Inventory、Location 动态账本；
11. 没有 short / mid / long 三级记忆；
12. 没有 Promise、Relationship、Opposition、Signature、Arc Audit、Outline Drift 持久化接口；
13. 没有 Closure 和全项目完整性检查；
14. 审计固定路径覆盖上一版，只保留当前文件，缺少审计历史；
15. 原子 rename 前后未对文件和目录做完整 fsync 最佳努力；
16. 服务端未阻止 title/body 重复包含章标题；
17. 旧项目与新门禁之间缺少明确迁移边界。

## 0.4.0 已实施改动

- 完整源码 `src/`、构建脚本、package 检查和真实测试；
- 33 个 manifest 与 runtime 对齐的工具；
- 项目级 Writing / Quality / Enforcement / Genre 配置与 CAS；
- 17 类完整审计；
- Writer + Continuity Auditor + Reader Editor 三会话质量 receipt；
- fsync-backed atomic write；
- Prepared transaction + per-target CAS + crash recovery；
- `novel_commit_status` 对账；
- revision CAS、版本备份、revision idempotency；
- 四类动态状态；
- 三级记忆及本地检索；
- 六类通用故事台账；
- Closure receipt；
- Integrity Check 与安全 repair；
- 旧项目 enforcement boundary 懒迁移；
- 审计和质量历史版本；
- 纯标题/纯正文 Payload Gate。

## 验证结果

- Node 语法检查：通过；
- Runtime registration smoke：33 个工具全部生成，名称、execute 和 parameters 完整；
- Node 测试：16/16 通过；
- Node 原生测试覆盖率：全部文件 line 76.59%、branch 56.39%、functions 72.33%（核心 `engine.js` line 73.02%）；
- 覆盖内容：2599/2600 边界、17项审计、独立会话、幂等、崩溃恢复、状态、记忆、台账、Closure、Revision CAS、旧 Hash 检测、Artifact CAS、Legacy Migration；
- 当前执行容器使用 Node `v22.16.0`，16 个测试均通过；但插件目标运行时声明为 Node `>=22.22.3`，仍需在 NAS 上核对真实 Node 版本；
- 当前执行容器没有安装 `openclaw` CLI，因此不能在这里完成真实 Gateway runtime inspect；必须在用户 NAS 上执行 `openclaw plugins inspect novel-engine --runtime --json` 作为最终环境验证。

## 仍需正确理解的边界

- 三个不同 session ID 是结构化证据，不是密码学上的“隔离上下文证明”；
- 语义审稿质量依赖执行审稿的模型和提示词；
- TF-IDF 记忆检索不是 embedding 向量检索；
- 文件事务能恢复单项目提交，但不是跨多个项目的分布式事务；
- 旧章节 grandfathering 是兼容策略，不能证明历史章节已经达到新质量标准。
