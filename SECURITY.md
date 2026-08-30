# Security

不要把 API Key、Webhook 密钥、OpenClaw 配置、小说正文、项目目录、会话、memory 或 n8n 凭证提交到公开仓库。

安装脚本只部署公开模板，并在覆盖同名文件前创建备份。它不会删除 `projects/`、`memory/`、`output/`、`.learnings/` 或会话数据。

发现安全问题时，请通过 GitHub Security Advisory 私下报告，不要在公开 Issue 中粘贴密钥或完整运行日志。

