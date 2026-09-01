# OpenClaw 小说转 AI 短剧生产套件组件清单

更新时间：2026-09-02  
目标仓库：`slobys/openclaw-novel-author-suite`  
目标分支：`drama-pipeline`

## 1. 端到端职责链

```text
novel-author（原创小说，可选上游）
  -> novel-producer（整书解析、系列规划、逐集交接）
  -> drama-producer（单集剧本、连续性、按需资产、分镜、视频、合成与闭环）
  -> n8n 图片/视频执行器
  -> NAS/shared-root 资产与回调
  -> 最终 MP4 + Pipeline Evidence + Series Commit
```

`novel-producer` 只传递用户锁定风格与故事视觉上下文；`drama-producer` 是单集视觉实现、实际时长、图片提示词和生产执行的唯一权威。

## 2. 必装 Agent 工作区

### novel-producer

目标目录：`~/.openclaw/workspace-novel-producer/`

| 类别 | 必需文件 |
|---|---|
| Agent 定义 | `AGENTS.md`、`SOUL.md`、`IDENTITY.md`、`HEARTBEAT.md` |
| 流程权威 | `novel-workflow.yaml` |
| 上下游合同 | `contracts/style-handoff-contract.md`、`RULES_PROGRESS_LIFECYCLE.md` |
| 核心脚本 | `build_source_segments.py`、`record_user_episode_advance.py`、`validate_adaptation_capacity.py`、`validate_duration_handoff.py`、`validate_source_preservation.py`、`validate_style_handoff.py` |
| 工作区 Skill | `resumable-workflow-handoff` |
| 测试 | 分段保全、容量、风格交接、用户逐集推进测试 |

不要分发本机的 `projects/`、`memory/`、`MEMORY.md`、`DREAMS.md`、`.learnings/` 或用户填充后的 `USER.md`。

### drama-producer

目标目录：`~/.openclaw/workspace-drama-producer/`

| 类别 | 必需文件 |
|---|---|
| Agent 定义 | `AGENTS.md`、`SOUL.md`、`IDENTITY.md`、`HEARTBEAT.md` |
| 流程权威 | `drama-workflow.yaml` |
| Skill 索引 | `drama-skill-map.yaml` |
| 状态与 Gate | `pipeline_state.py`、`ingest_asset_evidence.py`、所有 `validate_*.py` |
| 按需资产 | `resolve_asset_demand.py`、`deepwhite-asset-demand-resolver/SKILL.md` |
| 图片派发 | `submit_asset_job.py`、`send_asset_job_to_n8n.mjs`、`asset_retry_guard.py` |
| 视频派发 | `submit_video_job.py`、`deepwhite-n8n-video-dispatcher` |
| 生产闭环 Skills | `episode-production-closure`、`external-job-dispatch-recovery`、`pre-dispatch-production-session`、`short-drama-video-pacing`、`video-reference-asset-safety` |
| n8n 契约 | `integration/deepwhite-continuity/` 与 `integration/n8n-production/` |
| 测试 | workflow、Demand Resolver、派发、重试预算、QA evidence、连续性和视频参考安全测试 |

`openclaw-missing-reply-diagnosis` 属于 OpenClaw 运维诊断工具，不是成片关键路径，可作为可选组件安装。

## 3. 必装共享 Skills

### novel-producer 侧

1. `deepwhite-00-novel-series-orchestrator`
   - 小说导入：TXT、Markdown、DOCX、EPUB；
   - 系列数据合同、队列、逐集派发、系列资产 Gate、Pipeline Evidence；
   - 关键脚本：`ingest_novel.py`、`validate_series.py`、`series_orchestrator.py`、`series_asset_gate.py`、`validate_episode_pipeline.py`。

### drama-producer 侧

1. `deepwhite-screenwriting-v1`
2. `deepwhite-continuity-worldstate-zh`
3. `deepwhite-scene-asset-planner`
4. `deepwhite-asset-demand-resolver`
5. `deepwhite-scene-pack-builder`
6. `deepwhite-image-prompt-builder`（生产中固定 `PACKAGER_ONLY`）
7. `deepwhite-n8n-asset-dispatcher`
8. `deepwhite-shotlist-builder-zh-user`
9. `deepwhite-shot-transition-builder-zh`（按需）
10. `deepwhite-n8n-video-dispatcher`

每个 Skill 的 `SKILL.md`、其直接引用的 `references/`、`templates/`、`assets/`、`scripts/` 和 `agents/openai.yaml` 必须一起安装；排除 `.openclaw/source-origin.json`、`__pycache__/`、`*.pyc`、备份文件和 Git 元数据。

## 4. drama-producer 强制阶段

```text
00 初始化
10 稳定 Scene-ID 剧本
20 连续性世界状态
25 Scene Asset Planner
27 生图前 Shot Intent
28 Asset Demand Resolver + Demand Coverage Gate
30 STRICT 图片提示词
35 Location Prompt Gate
37 条件式独立多视角 Gate
40 缺失资产派发
45/48 Registry 与结构化 QA evidence 接收
50 基于实际图片的最终分镜
52 环境路线连续性 Gate
55 Shot Scene Binding Gate
60 可选 Transition Bridge
65 视频提示词 Gate
70 Video Scene Binding + 派发
80 视频片段结果
90 FFmpeg 最终合成验证
95 系列证据
100 系列提交
```

按需资产规则：每个单集生成项必须有 `consumer_shot_ids[]`；只有明确的 `series_core + series_library=true` 才可脱离本集消费镜头回填八方向系列资产包。

## 5. 系统和命令行依赖

| 组件 | 用途 | 当前验证版本/要求 |
|---|---|---|
| OpenClaw | Agent、会话、Hook、回调与 Skill 运行时 | 当前环境 `2026.7.1-2`；公开安装器应做最低版本检查 |
| Python 3 | 状态机、Gate、队列和验证脚本 | 已验证 Python 3.11 |
| Node.js | n8n sender、工作流契约测试 | 已验证 Node 24；建议声明 Node 20+ |
| n8n | 图片/视频异步执行、结构化 QA 和回调 | 需支持 Code、HTTP Request、文件系统和并发 Worker |
| FFmpeg/ffprobe | 最终合成与 MP4 可读性验证 | 安装器必须检测 |
| jq | JSON 运维与诊断 | 建议 1.6+ |
| Git/GitHub CLI | 源码安装、升级和维护发布 | 运行短剧本身不强制 `gh` |
| 共享文件系统 | OpenClaw 与 n8n 交换图片、manifest、状态和视频 | 宿主机与容器路径必须显式映射 |

当前 Python 关键路径只使用标准库；Node sender 只依赖 Node 内置模块。n8n 本身及其数据库/凭据不应被仓库脚本静默创建或覆盖。

## 6. 环境变量与受保护配置

只提交变量名和 `.env.example`，不得提交真实值：

- `OPENCLAW_HOME`
- `OPENCLAW_ASSET_SHARED_ROOT`
- `OPENCLAW_ASSET_HOOK_TOKEN`
- `N8N_ASSET_WEBHOOK_URL`
- `N8N_ASSET_WEBHOOK_SECRET`
- `N8N_VIDEO_WEBHOOK_URL`
- `N8N_VIDEO_WEBHOOK_SECRET`

n8n 内部的图片模型、视频模型、数据库和对象存储凭据必须由用户在目标环境的凭据管理器中配置。

## 7. 一键安装器必须参数化的本机路径

部分生产源仍包含部署现场路径，不能原样作为跨机器默认值：

- `<openclaw-home>`
- `<host-shared-asset-root>`
- `<n8n-container-shared-root>`

安装器应把它们转换为 `OPENCLAW_HOME`、宿主机共享根和 n8n 容器共享根参数，并在安装后运行路径可读写和目录穿越检查。

## 8. 一键安装前仍需补齐的公开发行组件

1. **视频 n8n 工作流模板**：本地可分发源目前只有视频 job schema、绑定 Gate 和 webhook sender，没有可供新用户直接导入的视频生成工作流 JSON。
2. **统一最终合成入口**：流程要求 FFmpeg 最终 MP4、大小和 SHA256 验证，但当前工作区没有通用的 `compose_episode.py` 或等价脚本。
3. **无环境依赖的配置渲染**：工作流与脚本仍有上述硬编码路径；安装器需要生成目标机配置，而不是修改 Git 中的源文件。
4. **安装后 smoke test**：至少验证 Agent/Skill 可发现、两个 webhook dry-run、共享目录、Demand Gate、Scene/Video Binding Gate 和 ffprobe。

在这四项完成前，仓库可以作为“生产源代码与合同包”共享，但不应宣传为“任意机器一键安装后即可完整出片”。

## 9. 同步白名单与排除项

本次 GitHub 同步只允许：

- 已在 `drama-pipeline` 分支存在且能映射到本地同源文件的安全生产文件；
- 本次新增的按需资产 Skill、Resolver、必要运行依赖和测试；
- 本组件清单及机器清单。

始终排除：

- `.env`、凭据、Token、Cookie、认证缓存；
- `projects/`、生成图片、视频、小说原文和回调产物；
- `MEMORY.md`、`memory/`、`DREAMS.md`、`.learnings/`、用户个性化 `USER.md`；
- `.git/`、`__pycache__/`、`*.pyc`、备份和临时文件；
- 本机日志、数据库、n8n credential export。
