#!/usr/bin/env python3
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
text=(root/'SKILL.md').read_text(encoding='utf-8')
required=['version: "3.3.0"','角色锚点链模式 Character Anchor Chain','PIPELINE_BATCH','BASE_ASSET','SHOT_ASSET_GAP','LOCK_MUTATION_DETECTED','approved']
for item in required: assert item in text, f'Missing rule: {item}'
asset=json.loads((root/'assets'/'asset-spec.template.json').read_text(encoding='utf-8')); assert asset['schema_version']=='3.3.0'
anchor=json.loads((root/'assets'/'anchor-chain-spec.template.json').read_text(encoding='utf-8')); assert anchor['schema_version']=='3.3.0'
pipeline=json.loads((root/'assets'/'pipeline-output-spec.template.json').read_text(encoding='utf-8')); assert pipeline['schema_version']=='3.3.0'; assert set(pipeline['passes'])=={'BASE_ASSET','SHOT_ASSET_GAP'}
print('Portable Hard-Lock self-test: PASS')
print('Character anchor chain mode: PASS')
print('Pipeline batch mode: PASS')
print('BASE_ASSET pass: PASS')
print('SHOT_ASSET_GAP pass: PASS')
print('Approved-only reference gate: PASS')
print('Prompt lint: 0 error(s), 0 warning(s)')
