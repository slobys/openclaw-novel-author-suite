# Upgrade 0.4.6

Novel Engine 0.4.6 与 Novel Author V5.4.0 Balanced-Lite 重点解决两类问题：长篇主会话不断膨胀，以及停止前台回合后后台子任务继续运行。

## 主要变化

- `novel_prepare_chapter` 默认返回按角色裁剪的 compact packet；`profile=full` 仅用于关键章或诊断。
- 每章创建全新的 isolated Writer；主会话只编排，不再写正文或重复做一次17类语义审计。
- Writer 通过文件交接正文和随稿审计，`writer_handoff_gate.py` 校验正文 Hash、汉字数和17类覆盖。
- 普通章 Reviewer 默认使用 low thinking，并分别只读取 Continuity/Reader 所需资料。
- Job 状态机增加 `cancelling/cancelled`、任务登记、阶段 Guard 和幂等两阶段取消。
- 用户停止时先建立持久化取消屏障，再用 OpenClaw `subagents(action=cancel)` 取消活动 taskId；迟到完成事件不能恢复流水线。

## 数据兼容

项目、正文、台账、Closure 和现有 Job 文件均保留。旧 Job 在首次读取时会补充空 `taskRegistry`；只有新版本登记过的子任务才能被精确列入取消目标。运行时急停仍可在主聊天发送 `/stop`。
