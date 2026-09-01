# Server-Side Gate Protocol V5.4.2 / Novel Engine 0.4.9

Agent 侧 Gate 不能替代服务端持久化前校验。正式配套版本为 Novel Engine `0.4.9`。

服务端能力预检以 `novel_project_status.serverCapabilities` 和 `storyLedgers.chapterLengthGate` 为准，至少验证：

- 项目级 `minHanChars` 已解析并由服务端执行；
- commit 服务端重新计算正文 Han 字符数和 SHA-256；
- passing Audit 完整覆盖项目要求类别并绑定最终正文 Hash；
- Independent Quality receipt 绑定同一正文 Hash，Writer/Auditor/Editor session ID 不同；
- Reviewer 检查项、Genre Gate 与 Chapter Signature 均为非空且绑定同一正文 Hash；
- `requestId` 幂等且与完整 Payload 指纹绑定；
- 提交使用可恢复 prepared transaction；
- `novel_commit_status` 能对账不确定投递；
- 修订使用正文 Hash/revision CAS；
- Closure 默认启用，skipped 必须有理由，completed evidence 必须绑定当前章节正文；
- 动态状态、三级记忆、因果、伏笔和长期台账写入均有正文来源绑定；
- 项目完整性检查已启用。

可把 `novel_project_status` 的完整 JSON 保存后运行：

```bash
python3 {baseDir}/scripts/server_capability_gate.py status.json --hard-min 2000 --receipt server-gate.json
```

`--hard-min` 应使用项目实际 resolved hard minimum；默认新规格为 2000，但项目可单独覆盖。

若 `serverGateVerified=false`，可继续创作草稿和本地质量检查，但不得提交为 V5 正式章节，也不得向用户声称服务端硬门禁已启用。
