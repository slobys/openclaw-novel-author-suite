# 异步视频与进度卡闭环规则

> 这是供 OpenClaw Control UI 查看器使用的审阅页。原始规则仍以两个 Agent 的 `AGENTS.md` 为准；本页不替代源文件。

## novel-producer 规则摘要

来源：`${OPENCLAW_STATE_DIR}/workspace-novel-producer/AGENTS.md`

- n8n Webhook 返回 HTTP 200/201/202/204 只代表入口接收，不能据此报告任务正在生成。
- 必须取得 n8n execution/task ID、供应商 task ID、固定 job 输出目录或可信 manifest/回调，才能标记为实际执行。
- 异步派发后保存检查点并结束前台回合，不使用长期轮询、watcher 或 heartbeat 占用会话。
- 最终 MP4 验证成功后，回调必须将原制作会话的进度卡闭环为完成，并清除等待状态。
- 项目已经 `final_video_ready` 时，任何关联会话不得继续显示“等待最终 MP4”；若状态不一致，先修复进度卡再报告完成。
- 用户明确说“继续下一集”时，上一集人工验收等待立即闭环并记录用户已验收；但下一集派发前仍须验证上一集最终 MP4、SHA256、画幅和系列完成提交。
- 每集使用独立持久 Hook 会话 `hook:drama:episode:{episode_project_id}`；禁止多集复用 `drama-producer:main`。

## drama-producer 规则摘要

来源：`${OPENCLAW_STATE_DIR}/workspace-drama-producer/AGENTS.md`

### 派发前

1. 在 `project.json` 写入：
   - `progress_card_owner_session_key`
   - `progress_waiting_step`
   - `progress_state: awaiting_callback`
2. `progress_card_owner_session_key` 不得为空。
3. 运行：

   ```bash
   python3 scripts/validate_progress_lifecycle.py \
     --project projects/{project_id}/project.json \
     --phase pre-dispatch
   ```

4. 校验失败时禁止提交异步任务。
5. 新项目的 `progress_card_owner_session_key` 必须等于 `agent:drama-producer:hook:drama:episode:{project_id}`；共享 main 会话会被 Gate 拒绝。

### 用户推进下一集

1. 将上一集写入 `user_review_accepted: true`、目标集数、用户原话与记录时间。
2. 验证上一集最终 MP4 后，关闭上一集进度卡/等待态并结束其制作会话。
3. 下一集使用新的分集专属会话；状态报告不得再说上一集仍在运行。
4. 异步任务取得权威执行证据后，当前 Agent 回合立即结束；项目可显示“生成中”，会话不得为等待回调持续运行。

### 最终 MP4 验证成功后

1. 把当前回调会话进度卡全部标记为 `completed`。
2. 若原制作会话不同，向其发送幂等闭环任务，把“等待最终 MP4”改为完成。
3. 写入：
   - `progress_state: completed`
   - `progress_closed_at`
   - `progress_card_closed: true`
4. 清除 `progress_waiting_step`、watcher 和定时轮询。
5. 运行：

   ```bash
   python3 scripts/validate_progress_lifecycle.py \
     --project projects/{project_id}/project.json \
     --phase final
   ```

6. 项目状态、最终 MP4、进度卡三者一致后，才允许报告完成。

## 验证器

源文件：`${OPENCLAW_STATE_DIR}/workspace-drama-producer/scripts/validate_progress_lifecycle.py`

验证器会检查：

- 派发前是否已登记进度卡所属会话及等待步骤；
- 派发前是否使用与 `project_id` 匹配的分集专属 Hook 会话；
- 完成后项目是否为 `final_video_ready`；
- 视频生成与合成状态是否均为 `completed`；
- 进度状态是否完成、关闭时间是否存在、等待步骤是否清空；
- `progress_card_closed` 是否为 `true`。

## 查看器兼容说明

当前 Control UI 的会话文件接口只接受当前工作区内的相对路径。聊天消息中的绝对本地路径会被原样传给接口，从而返回 `session file not found`；跨 Agent 工作区文件也不能通过当前会话根目录直接打开。

因此，当前会话中的规则链接应使用相对路径。本页将跨工作区相关规则集中为一个可查看的审阅入口。
