# 配置说明

## 必需环境变量

| 变量 | 用途 |
| --- | --- |
| `OPENCLAW_ASSET_ROOT` | n8n 写入图片、视频结果与 manifest 的固定根目录。OpenClaw 必须能读取。 |
| `N8N_ASSET_WEBHOOK_URL` | 图片任务入口。 |
| `N8N_ASSET_WEBHOOK_SECRET` | 图片入口鉴权密钥。 |
| `N8N_VIDEO_WEBHOOK_URL` | 视频任务入口。 |
| `N8N_VIDEO_WEBHOOK_SECRET` | 视频入口鉴权密钥。 |

这些变量必须进入 Gateway 服务环境，只在当前 SSH shell 中 `export` 不会自动传给已经运行的 systemd 服务。

## 可选路径变量

| 变量 | 默认值 |
| --- | --- |
| `OPENCLAW_STATE_DIR` | `$HOME/.openclaw` |
| `OPENCLAW_SKILLS_DIR` | `$OPENCLAW_STATE_DIR/skills` |
| `NOVEL_PRODUCER_WORKSPACE` | `$OPENCLAW_STATE_DIR/workspace-novel-producer` |
| `DRAMA_PRODUCER_WORKSPACE` | `$OPENCLAW_STATE_DIR/workspace-drama-producer` |
| `DRAMA_PRODUCER_PROJECTS_ROOT` | `$OPENCLAW_STATE_DIR/workspace-drama-producer/projects` |

## n8n 对接最低要求

- 回调或结果必须包含可验证的 `project_id`、`job_id`/`video_job_id`；
- 固定输出目录必须位于 `OPENCLAW_ASSET_ROOT` 下；
- HTTP 200/201/202/204 只代表 Webhook 接收，不能当作生成完成；
- 执行确认至少要有 n8n execution/task ID、供应商 task ID、固定结果目录或可信回调之一；
- 最终完成必须有 manifest、可读文件、文件大小和 SHA-256 证据。

本仓库不包含你的 n8n Workflow JSON，因为不同部署的节点 ID、凭证、模型和存储挂载不同。需要让 n8n 的字段与 `deepwhite-n8n-asset-dispatcher`、`deepwhite-n8n-video-dispatcher` 的 schema 对齐。

