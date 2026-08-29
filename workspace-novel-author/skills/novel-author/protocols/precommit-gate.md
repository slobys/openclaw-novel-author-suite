# Precommit Gate Protocol V5.0

目标：把最终正文、篇幅、engine 审计、独立审稿、类型承诺和 payload 绑定到同一个 SHA-256。

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
- 17 类 engine precommit audit 全部存在并通过；
- blocking issue 为 0；
- engine audit `bodySha256` 等于最终正文；
- Payload Gate 通过；
- Independent Audit 通过；
- Genre Promise 无 severe hard block；
- Quality receipt、Payload receipt、Audit、最终正文 Hash 完全一致。

正文任何修改都会使 audit、independent review、genre current signature、quality receipt 和 precommit receipt 全部失效，必须重新生成。
