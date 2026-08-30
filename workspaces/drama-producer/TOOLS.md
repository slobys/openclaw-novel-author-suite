# drama-producer 本地运行说明

这些是部署环境约束，不参与生产阶段裁决；阶段与 Gate 以 `drama-workflow.yaml` 为准。

## NAS 图片观察

- OpenClaw `image` 工具不能直接读取 `${OPENCLAW_ASSET_ROOT}/...` 时，先按清单校验文件大小和 SHA256，再复制到当前项目的只读验收目录。
- 单张临时检查可使用支持本地绝对路径的图片查看工具。
- 审核副本不替代 NAS 原图和 manifest 的权威性。

## WebChat 图片上传

- OpenClaw `2026.7.1-2` Gateway 单条 WebSocket 消息上限为 25 MiB。
- Base64 和 JSON 会增加体积；原图总量建议控制在约 17 MiB 以下。
- 默认每批最多 3 张、单张建议不超过 5 MiB。
- 出现 `gateway closed (1009)` 或 `Max payload size exceeded` 时，清空附件或刷新页面后分批重传，禁止让旧大消息持续重试。
- 多批上传完成前只接收和映射；用户明确“全部发送完成”后再开始下游工作。

## jq 中文字段

- 中文键使用 `."字段名"` 或 `.['字段名']`。
- 比较数组唯一数量时显式加括号，例如：

```bash
((.assets | map(.asset_id) | unique | length) == (.assets | length))
```
