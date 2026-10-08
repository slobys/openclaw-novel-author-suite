# Precommit Gate Protocol V5.0

目标：把最终正文、篇幅、Writer 本地审计、独立审稿、类型承诺和 payload 绑定到同一个 SHA-256。

顺序：

```bash
python3 {baseDir}/scripts/chapter_payload_gate.py --chapter 7 --title "纯标题" --body-file chapter.md --receipt payload-receipt.json
python3 {baseDir}/scripts/independent_audit_gate.py --body-file chapter.md --writer-session WRITER --continuity-review continuity.json --reader-review reader.json --receipt independent.json
python3 {baseDir}/scripts/genre_promise.py --profile genre-profile.json --signature-ledger signatures.jsonl --current-signature current-signature.json --receipt genre.json
python3 {baseDir}/scripts/quality_gate.py --body-file chapter.md --independent-receipt independent.json --genre-receipt genre.json --receipt quality.json
python3 {baseDir}/scripts/precommit_gate.py chapter.md audit.json --payload-receipt payload-receipt.json --quality-receipt quality.json --receipt gate-receipt.json
```

通过条件：

- 汉字数达到 resolved hard minimum；
- 17 类 Hash 绑定 Writer precommit audit 全部存在并通过；
- blocking issue 为 0；
- 本地 audit `bodySha256` 等于最终正文；
- Payload Gate 通过；
- Independent Audit 通过；
- Genre Promise 无 severe hard block；
- Quality receipt、Payload receipt、Audit、最终正文 Hash 完全一致。

正文任何修改都会使 audit、independent review、genre current signature、quality receipt 和 precommit receipt 全部失效，必须重新生成。

所有脚本阈值参数从同一次 project config read 的 resolved writingContract 传入（`--hard-min`/`--target-min`/`--target-max`），不要套另一工作区间。`targetRangePass` 为旧兼容字段；新增 `preferredTargetRangePass` 表示真正目标区间，`belowPreferredTarget`/warnings 非阻断，不触发第二轮扩写。

默认验证 `writer-audit.json` 与本地质量回执后，一次 Finalize 服务端记录 Audit→Quality→Commit→Closure→Integrity；本地 Gate 不要求未发生的 Engine receipt。只有 Finalize 不可用才先真实记录 Audit/Quality 后 Commit。取消 Guard、正文Hash变化与原失败/恢复规则不变。
