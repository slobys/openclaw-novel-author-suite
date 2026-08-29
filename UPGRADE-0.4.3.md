# Novel Engine 0.4.3 升级说明

## 修复内容

- 项目锁发生短暂重叠时，默认有限等待最多 15 秒，不再立即返回 `PROJECT_WRITE_LOCKED`。
- 活动写操作定期刷新锁租约，避免合法长操作被误判为陈旧锁。
- 同一 NAS 上已经退出的锁持有进程会被立即识别并回收，无需等待十分钟。
- 超过 `lockStaleMs` 且租约未刷新的锁可安全回收，包括 Gateway 进程仍存活但旧调用未清理锁文件的情况。
- 锁超时错误增加 owner、age 与 waited 等诊断字段。

## 兼容性

- 不修改小说项目、章节、审稿、Closure、台账或记忆数据格式。
- 保留 0.4.2 的 Closure 对象 Schema 修复。
- 新增可选配置 `lockAcquireTimeoutMs`，默认 `15000`；现有配置无需修改。

## 部署

使用 `npm-pack:` 安装后重启 Gateway，并用 `openclaw plugins inspect novel-engine --runtime --json` 确认运行版本为 0.4.3。
