# Evaluation Cases

Use these after changing the skill. Check routing, compactness, state integrity and exact lock reuse.

## Trigger-positive

1. “做一套仙侠庭院，同一场景六个角度。”
2. “这个村口的道路每张图都变，帮我建立 Scene DNA。”
3. “牛车从门口到远处，先给俯视布局，再一张张出提示词。”
4. “检查刚生成的 V03，房子是不是镜像了？”
5. “继续 SC-old-house-01 的下一张。”
6. “复杂悬崖仙门，先做白模再做母版。”

## Trigger-negative

1. “润色一张人物海报提示词。”
2. “生成一只可爱的猫。”
3. “把这段中文翻成英文。”

## Expected checks

- default output contains one final image prompt;
- description routes “下一张/漂移修复” correctly;
- new scene gets a unique Scene ID;
- complex 3D scenes include B01 before M01;
- Canonical Prompt Lock is character-for-character identical in later prompts;
- world-space light is used, not fixed frame-relative light;
- major landmarks have asymmetric fingerprints and dimensions;
- geometry/master/proof authorities remain in the chain;
- geometry revision invalidates dependent views;
- style revision preserves geometry authorities;
- camera revision does not move world landmarks;
- subject revision invalidates subject/shot outputs only;
- audit rejects mirror/topology failures even if the picture is attractive;
- draft manifests warn, while `seal` requires strict validity.

## Portable-output regression

For every emitted L01/M01/Axx/Vxx/SHxx prompt, verify:

- exact `【STYLE LOCK｜固定原文】` exists and is non-empty;
- exact `【SCENE DNA｜固定原文】` exists and is non-empty;
- exact `【SPATIAL LOCK｜固定原文】` exists and is non-empty;
- exact `【CONTINUITY LOCK｜固定原文】` exists and is non-empty;
- all four texts are character-for-character identical across assets until an explicit revision;
- `参考上一张 / 以上一张为参考 / 如上` never substitutes for the four blocks;
- every asset ID used as a reference is marked as an image that must be actually attached;
- the prompt remains usable in a fresh model chat with no prior messages;
- `scripts/prompt_lint.py` returns zero errors for saved prompts.

## 2.3 Hard-lock fail-closed regression

For AST-01, AST-02 and AST-03:

- the first non-whitespace line is exactly `【PORTABLE HARD LOCK｜独立可用｜禁止删减】`;
- a non-empty `LOCK_ID:` line follows;
- all four exact headings appear once and in order;
- the four bodies are byte-for-byte identical between AST assets;
- all required dynamic sections appear once;
- each symbolic image reference says the image must actually be uploaded;
- a loose paragraph beginning with “连续性锁定：” is not accepted as a substitute;
- bilingual output, when requested, passes the same test separately for both languages;
- if compilation/lint cannot pass, output is `HARD_LOCK_VALIDATION_FAILED`, not a shortened prompt.

Suggested CLI test:

```bash
python3 scripts/prompt_compiler.py --manifest sample/scene.json --asset sample/AST-03.json --output /tmp/AST-03.txt
python3 scripts/prompt_lint.py /tmp/AST-03.txt --manifest sample/scene.json --strict-hardlock
```


## 2.5 Indoor connectivity regression

Required test cases:

1. Single-level graph: RM01 → PT01 → RM02 passes.
2. Wrong connector used for a route fails strict validation.
3. Door/opening crossing different levels fails.
4. Stair connecting the same level fails.
5. Multi-level scene without S01 warns/errors in strict mode.
6. Disconnected required room fails strict validation.
7. TR prompt includes source, destination and connector context.
8. Opposite-side portal prompt preserves dimensions and fingerprints.
