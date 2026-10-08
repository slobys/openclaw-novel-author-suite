# M1 叙事约束验收记录

日期：2026-10-08。范围：本开发分支的确定性因果、伏笔生命周期、提交预检及恢复；不是正式版本发布或生产部署批准。

## 已核实结果

| 检查 | 实际结果 |
| --- | --- |
| `npm run verify` | build、57/57 Node tests、package check 通过；34 个原工具保持 |
| Python 本地 Agent Gates | 46/46 通过 |
| 独立基本行为探针 | 31/31 通过（见故障注入适配说明） |
| 独立补充契约 | 8/8 通过 |
| 独立加强契约 | 24/24 通过 |
| 模拟安装器 / selector / shell 语法 | 全部通过；未实际安装插件或重启 Gateway |
| 五个 src/dist 模块 | 字节及 Hash 一致 |
| 空白与公开文件检查 | 本地通过；交付时另对暂存后的完整 tracked 树检查 |

上述探针分组有重叠，不累加成互不重复的小说质量样本或文学正确率。独立验收使用真实 Engine / finalizer 与临时合成项目、明确的合成审稿回执；不调用真实写作/审稿模型。

本地环境：Node v24.21.0、npm 11.20.0、Python 3.11.2。远端 Node 22.22.3 / Python 3.12 矩阵以当前 PR 的 CI 检查为准，不从本地通过推断远端通过。

## 缺陷、合法对照与恢复

- 未知/仅 planned 的伏笔不可直接 advance/payoff；合法同章 open→payoff 通过。
- 部分更新保留埋设章、类别与原 plant Hash；旧来源修订后，delta advance/payoff 在 commit 前拒绝，无正文/request/state/ledger 副作用。
- paid/cancelled 的规范化相同业务载荷可重放，notes/type/source/body/payoff 修改拒绝。明确的 plant provenance 重建仅允许该证据和自动历史变化，不能掩护其他事实修改。
- occurred 原因必须存在、已发生且来源有效；缺失、计划、取消、陈旧证据与混合字段环拒绝。合法倒叙和 planned 前向引用保留。
- 已有 a→b 的合法整批替换 b→a 实际完成；非法最终环在 commit 前拒绝。graph 写入后、Closure 前注入中断，同 request 恢复完成，不重审、不重写正文、不复制事件。
- legacy 普通更新不虚构旧 plant 证据；有效显式补录/修订绑定与历史保存通过。upsert/finalize 公开 schema 均声明可选 plantedBodySha256。

### 故障注入适配

旧独立探针的 Z04 注入单条 `recordCausalEvent`。修复后的 finalizer 使用整批 `recordCausalEvents`，旧注入没有命中，初次原始结果为 30/31，失败是“预期模拟中断未发生”。QA 保留该原始记录，只在隔离脚本把故障注入改挂实际 batch 入口，再验证 commit 后同 payload 恢复；对应 Z04 1/1 通过，组合基本契约为 31/31。没有修改产品来迁就测试。

24 项加强检查另验证合法旧边反转以及 graph 写完、Closure 前的实际中断恢复，未依赖这个旧注入点。

## 所测候选版本

| 源码 | SHA-256 |
| --- | --- |
| engine.js | 0a2b9512bc131198118869f9d4c88a75b481c3c4504407356f2b5d1bea874e9a |
| finalize.js | e1498f8d287324fa86c1de4166c9f6c66464b5d9abfdcb13fd7dbc93b37548c7 |
| index.js | 6e39cc3b9f9d148f3f68efbcb2d49fa5390a5e12d73a1b0534db4c8fad9cbbae |

验收冻结前后、副本与报告时工作树 Hash 一致。测试临时数据由 finally 清理；没有真实作品访问。

## 保证边界与后续

Hash/回执证明版本绑定，不证明原文真的存在公平线索、角色动机合理、知识来源成立或主线语义兑现。没有实际 Gateway 参数归一化、真实模型长篇对照实验或生产升级结论。

因果 batch 是一个 graph 文件内的持锁更新，不是章节与所有派生文件的全局原子事务；保持单项目单 Writer、原 CAS/requestId/Closure/取消恢复边界。

后续仍需解决权威台账变化后的上下文缓存、关键旧事实遗漏、声明与 Closure 一致性、人物知识/信念和带原文证据的长篇评测。见[叙事约束](NARRATIVE-INTEGRITY.md)、[研究报告](RESEARCH-NARRATIVE-CONSISTENCY.md)与[持续优化路线](CONTINUOUS-OPTIMIZATION.md)。
