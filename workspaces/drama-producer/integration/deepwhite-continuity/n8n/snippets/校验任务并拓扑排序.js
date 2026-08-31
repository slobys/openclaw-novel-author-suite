const crypto = require('crypto');
const path = require('path');
const req = $input.first().json ?? {};
const payload = req.body ?? req;
const headers = Object.fromEntries(Object.entries(req.headers ?? {}).map(([key, value]) => [String(key).toLowerCase(), Array.isArray(value) ? String(value[0] ?? '') : String(value ?? '')]));
const secret = String($env.N8N_ASSET_WEBHOOK_SECRET || '').trim();
if (!secret) throw new Error('环境变量 N8N_ASSET_WEBHOOK_SECRET 未配置');
if (String(headers['x-openclaw-secret'] || '').trim() !== secret) throw new Error('Webhook 鉴权失败');
if (!payload || !Array.isArray(payload.assets) || payload.assets.length === 0) throw new Error('assets 必须是非空数组');

const safeId = /^[A-Za-z0-9_-]+$/;
const safeFilename = /^[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp)$/i;
const shaPattern = /^sha256:[a-f0-9]{64}$/;
const allowedRatios = new Set(['1:1','2:3','3:2','3:4','4:3','4:5','5:4','9:16','16:9','21:9']);
const lockHeadings = [
  ['style_lock_text', '【STYLE LOCK｜固定原文】'],
  ['scene_or_subject_lock_text', '【SCENE DNA / SUBJECT DNA｜固定原文】'],
  ['spatial_or_structure_lock_text', '【SPATIAL LOCK / STRUCTURE LOCK｜固定原文】'],
  ['continuity_lock_text', '【CONTINUITY LOCK｜固定原文】'],
];
const stable = value => Array.isArray(value)
  ? value.map(stable)
  : value && typeof value === 'object'
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])]))
    : value;
const sha = value => `sha256:${crypto.createHash('sha256').update(JSON.stringify(stable(value))).digest('hex')}`;
const payloadCopy = JSON.parse(JSON.stringify(payload));
delete payloadCopy.payload_sha256;
const computedPayloadSha = sha(payloadCopy);
if (!shaPattern.test(String(payload.payload_sha256 || '')) || payload.payload_sha256 !== computedPayloadSha) throw new Error('payload_sha256 缺失或不匹配');
if (String(headers['x-openclaw-payload-sha256'] || '') !== computedPayloadSha) throw new Error('请求头 Payload SHA256 不匹配');
if (!safeId.test(String(payload.project_id || '')) || !safeId.test(String(payload.job_id || ''))) throw new Error('project_id/job_id 只能包含 ASCII 字母、数字、下划线和连字符');
if ('shared_asset_root' in payload || 'shared_asset_root' in (payload.defaults || {})) throw new Error('shared_asset_root 禁止由 Payload 指定');

const extractLocks = prompt => {
  const text = String(prompt || '');
  const result = {};
  for (const [key, heading] of lockHeadings) {
    const startAt = text.indexOf(heading);
    if (startAt < 0) throw new Error(`缺少四锁标题：${heading}`);
    const contentStart = startAt + heading.length;
    let contentEnd = text.length;
    for (const [, nextHeading] of lockHeadings) {
      const candidate = text.indexOf(nextHeading, contentStart);
      if (candidate >= 0 && candidate < contentEnd) contentEnd = candidate;
    }
    const nextAny = text.slice(contentStart).match(/\n【[^】]+】/);
    if (nextAny) contentEnd = Math.min(contentEnd, contentStart + nextAny.index);
    const value = text.slice(contentStart, contentEnd).trim();
    if (!value) throw new Error(`四锁内容为空：${heading}`);
    result[key] = value;
  }
  return result;
};

const defaults = payload.defaults || {};
const root = path.resolve(String($env.OPENCLAW_ASSET_SHARED_ROOT || '/data/openclaw-assets'));
const ids = new Set();
const filenames = new Set();
const assetMap = new Map();
for (const raw of payload.assets) {
  if (!safeId.test(String(raw.asset_id || '')) || ids.has(raw.asset_id)) throw new Error(`asset_id 缺失、非法或重复：${raw.asset_id}`);
  if (!safeFilename.test(String(raw.filename || '')) || filenames.has(raw.filename)) throw new Error(`filename 缺失、非法或重复：${raw.filename}`);
  if (!String(raw.prompt_zh || '').startsWith('【PORTABLE HARD LOCK｜独立可用｜禁止删减】')) throw new Error(`${raw.asset_id} 缺少 PORTABLE HARD LOCK`);
  const computedLockHash = sha(extractLocks(raw.prompt_zh));
  if (!shaPattern.test(String(raw.lock_hash || '')) || raw.lock_hash !== computedLockHash) throw new Error(`${raw.asset_id} lock_hash 不匹配`);
  if (!raw.lock_id) throw new Error(`${raw.asset_id} 缺少 lock_id`);
  if (!allowedRatios.has(String(raw.aspect_ratio || ''))) throw new Error(`${raw.asset_id} 画幅不受支持`);
  if (['location','scene','shot'].includes(raw.category)) {
    if (!Array.isArray(raw.scene_ids) || raw.scene_ids.length === 0 || raw.scene_ids.some(id => !safeId.test(String(id)))) throw new Error(`${raw.asset_id} 缺少合法 scene_ids[]`);
    for (const key of ['location_id','sub_location_id','location_asset_id']) if (!safeId.test(String(raw[key] || ''))) throw new Error(`${raw.asset_id} 缺少 ${key}`);
  }
  if (raw.generation_stage === 'shot' && !safeId.test(String(raw.scene_id || ''))) throw new Error(`${raw.asset_id} shot 资产缺少 scene_id`);
  ids.add(raw.asset_id);
  filenames.add(raw.filename);
  assetMap.set(raw.asset_id, {
    ...raw,
    project_id: payload.project_id,
    job_id: payload.job_id,
    source: String(payload.source || 'openclaw'),
    payload_sha256: computedPayloadSha,
    model: String(raw.model || defaults.model || 'gemini-3.1-flash-image'),
    image_size: String(raw.image_size || defaults.image_size || '2K'),
    review_model: String(raw.review_model || defaults.review_model || 'gemini-2.5-flash'),
    review_min_score: Number(raw.review_min_score || defaults.review_min_score || 85),
    review_max_retries: Number(raw.review_max_retries ?? defaults.review_max_retries ?? 2),
    depends_on: Array.isArray(raw.depends_on) ? raw.depends_on : [],
    reference_inputs: Array.isArray(raw.reference_inputs) ? raw.reference_inputs : [],
    retry_count: 0,
    review_retry_count: 0,
    shared_asset_root: root,
  });
}
for (const asset of assetMap.values()) {
  const refs = new Set(asset.reference_inputs.map(ref => ref.asset_id));
  for (const ref of asset.reference_inputs) {
    if (!safeId.test(String(ref.asset_id || '')) || !String(ref.role || '').trim()) throw new Error(`${asset.asset_id} reference_inputs 非法`);
    if (ref.required && ref.approved_only !== true) throw new Error(`${asset.asset_id} 的必需参考必须 approved_only=true`);
  }
  for (const dep of asset.depends_on) {
    if (!safeId.test(String(dep || ''))) throw new Error(`${asset.asset_id} 依赖 ID 非法：${dep}`);
    if (!assetMap.has(dep) && !refs.has(dep)) throw new Error(`${asset.asset_id} 外部依赖未声明为 reference_input：${dep}`);
  }
}
const temporary = new Set();
const done = new Set();
const order = [];
function visit(id, stack = []) {
  if (done.has(id)) return;
  if (temporary.has(id)) throw new Error(`依赖图存在循环：${[...stack, id].join(' -> ')}`);
  temporary.add(id);
  const asset = assetMap.get(id);
  for (const dep of asset.depends_on) if (assetMap.has(dep)) visit(dep, [...stack, id]);
  temporary.delete(id);
  done.add(id);
  order.push(asset);
}
for (const id of assetMap.keys()) visit(id);
return order.map(asset => ({ json: asset }));
