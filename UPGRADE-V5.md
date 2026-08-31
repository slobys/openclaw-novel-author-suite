# 从 Novel Engine 0.3.0 升级到 0.4.0

> 本文件仅用于历史上的 0.3.0→0.4.0 升级。当前 0.4.1 请使用 `UPGRADE-0.4.1.md`。

## 1. 备份当前插件

```bash
stamp=$(date +%Y%m%d-%H%M%S)
cp -a "${HOME}/.openclaw/plugins/novel-engine" \
  "${HOME}/.openclaw/plugins/novel-engine.backup-${stamp}"
```

项目正文通常位于 `~/.openclaw/data/novels`，建议另做一次数据备份：

```bash
cp -a "${HOME}/.openclaw/data/novels" \
  "${HOME}/.openclaw/data/novels.backup-${stamp}"
```

## 2. 解压到临时目录并替换

假设升级包上传到 `~/novel-engine-v0.4.0-full.zip`：

```bash
rm -rf /tmp/novel-engine-v040
mkdir -p /tmp/novel-engine-v040
unzip "${HOME}/novel-engine-v0.4.0-full.zip" -d /tmp/novel-engine-v040

rm -rf "${HOME}/.openclaw/plugins/novel-engine"
cp -a /tmp/novel-engine-v040/novel-engine \
  "${HOME}/.openclaw/plugins/novel-engine"
```

## 3. 本地校验

```bash
cd "${HOME}/.openclaw/plugins/novel-engine"
npm run verify
npm run pack:check
```

预期结果：

- 16 个测试全部通过；
- package check 显示 33 tools；
- `npm pack --dry-run` 包含 `dist/`、manifest、Skill 和文档。

## 4. 重启并检查 OpenClaw Runtime

```bash
openclaw gateway restart
openclaw plugins inspect novel-engine --runtime --json
```

确认：

- version 为 `0.4.0`；
- runtime 加载成功；
- 33 个 `novel_*` 工具已注册；
- 没有 manifest contract mismatch 或 dependency error。

## 5. 检查旧项目

先在 Agent 中调用：

```text
novel_project_list
novel_project_status
novel_project_config_read
novel_project_integrity_check(repair=false)
```

旧项目会自动生成 `project-config.json`，enforcement boundary 默认等于升级时的 `nextChapter`。历史章节出现 grandfathered warning 属于兼容提示，不等于正文损坏。

需要补齐安全元数据时：

```text
novel_project_integrity_check(repair=true)
```

`repair=true` 不会自动伪造 Audit、Quality、Closure 或小说事实。

## 6. 与 Novel Author V5 配合

Agent 必须在 commit 前新增：

```text
novel_chapter_quality_record
```

commit 后新增：

```text
novel_story_ledger_upsert
novel_dynamic_state_update
novel_memory_record
novel_chapter_closure_record
novel_project_integrity_check
```

投递状态不确定时使用：

```text
novel_commit_status
```

修订时必须先读取章节，再把 `contentSha256` 和 `revision` 作为 CAS 条件传给 `novel_revise_chapter`。

## 7. 回滚

停止 Gateway 后恢复插件备份：

```bash
rm -rf "${HOME}/.openclaw/plugins/novel-engine"
cp -a "${HOME}/.openclaw/plugins/novel-engine.backup-<时间戳>" \
  "${HOME}/.openclaw/plugins/novel-engine"
openclaw gateway restart
```

0.4.0 新增的数据目录不会妨碍 0.3.0 读取原有正文，但回滚期间不要让旧插件修改同一个正在由 0.4.0 写入的项目。
