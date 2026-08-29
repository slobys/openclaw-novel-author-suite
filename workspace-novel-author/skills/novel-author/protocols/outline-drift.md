# Outline Drift Protocol V5.0

目标：知道“实际写出来的故事”与“冻结章纲/滚动章纲”偏离了多少，而不是等几十章后才发现主线变形。

## 稳定 Beat ID

规划阶段对必须兑现的 Beat 使用稳定 ID，例如：`V2-C37-B3`。实际章节 Signature 记录：

- `fulfilledBeatIds`：已完成；
- `deferredBeatIds`：明确延期；
- `droppedBeatIds`：明确取消；
- `newBeatIds`：写作中新增；
- `plannedBeatIds`：本章原计划。

每 5 章或卷/阶段边界运行 `outline_drift.py`。高/中风险只调整未来 3–8 章，禁止为了让报表好看而静默重写已提交历史。
