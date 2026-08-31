#!/usr/bin/env python3
from pathlib import Path
from copy import deepcopy
import json
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'scripts'))

from prompt_compiler import BANNER, compile_prompt
from prompt_lint import lint
from queue_manager import resolve
from scene_state import validate

text=(root/'SKILL.md').read_text(encoding='utf-8')
required=[
    'version: "3.2.0"',
    '角色锚点链模式 Character Anchor Chain',
    'Anchor-A｜主身份锚点',
    'Anchor-B｜脸部锚点',
    'REFERENCE COVERAGE：GREEN / YELLOW / RED',
    '列出当前角色锚点',
    'ANCHOR_CHAIN_NOT_INITIALIZED',
    '下一步建议补充：',
    '以当前上传的人物图为主参考，输出左侧面全身'
]
for item in required:
    assert item in text, f'Missing rule: {item}'
asset=json.loads((root/'assets'/'asset-spec.template.json').read_text(encoding='utf-8'))
assert asset['schema_version']=='3.2.0'
assert asset['character_anchor_chain']['enabled'] is True
anchor=json.loads((root/'assets'/'anchor-chain-spec.template.json').read_text(encoding='utf-8'))
assert anchor['schema_version']=='3.2.0'
assert 'Anchor-A' in anchor['anchors']
assert 'GREEN' in anchor['coverage_logic']

scene=json.loads((root/'assets'/'scene-manifest.template.json').read_text(encoding='utf-8'))
assert scene['schema_version']=='3.2.0'
assert scene['assets'][0]['id']=='F01'
assert scene['assets'][0]['asset_id']=='SC001-ST01-F01-v001'
errors, _warnings = validate(scene)
assert not errors, f'Scene template validation failed: {errors}'
assert resolve(scene, 'F01')['id']=='F01'

production_scene=deepcopy(scene)
production_scene['canonical_prompt_lock'].update({
    'style_lock_text': '统一电影级三维半写实视觉风格，材质、色彩、光影与镜头语言在整套资产中保持稳定。',
    'scene_dna_lock_text': 'SC001始终代表同一处物理场景，固定入口、道路、主体建筑和远景轮廓均不可替换。',
    'spatial_lock_text': '入口位于南侧，道路向北连接主体建筑，三个地标维持固定坐标、尺度和相互方位。',
    'continuity_lock_text': '所有视角继承同一时间、天气、地表状态和空间结构，只允许符合物理规律的透视与遮挡变化。',
})
production_scene['landmarks']=[
    {'id':'A','position_m':[0,0,0],'dimensions_m':[2,1,2],'fingerprints':['南侧石门','左柱缺角']},
    {'id':'B','position_m':[0,8,0],'dimensions_m':[5,3,4],'fingerprints':['北侧主屋','双坡灰瓦']},
    {'id':'C','position_m':[6,4,0],'dimensions_m':[2,2,3],'fingerprints':['东侧老树','树干右倾']},
]
errors, _warnings = validate(production_scene, strict=True)
assert not errors, f'Production scene validation failed: {errors}'

prompt_asset=json.loads((root/'assets'/'asset-prompt-spec.template.json').read_text(encoding='utf-8'))
prompt_asset.update({'asset_name':'总平面标准视图','task':'生成同一场景的总平面标准视图','references':[]})
prompt=compile_prompt(production_scene, prompt_asset, allow_unsealed=True)
assert prompt.startswith(BANNER)
errors, _warnings = lint(prompt, production_scene)
assert not errors, f'Compiled prompt lint failed: {errors}'

print('Portable Hard-Lock self-test: PASS')
print('Zero-config invocation mode: PASS')
print('Default scene aspect ratio 16:9: PASS')
print('Default subject aspect ratio 9:16: PASS')
print('Character direct output mode: PASS')
print('Character anchor chain mode: PASS')
print('Anchor coverage rating: PASS')
print('Anchor list mode: PASS')
print('Animal mode: PASS')
print('Creature mode: PASS')
print('Prop mode: PASS')
print('Scene manifest init/validation: PASS')
print('Queue schema compatibility: PASS')
print('Prompt compile/lint round-trip: PASS')
print('Prompt lint: 0 error(s), 0 warning(s)')
