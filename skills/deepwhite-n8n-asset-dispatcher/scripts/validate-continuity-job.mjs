#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const SAFE_ID = /^[A-Za-z0-9_-]+$/;
const SAFE_FILENAME = /^[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp)$/i;
const SHA256 = /^sha256:[a-f0-9]{64}$/;
const ALLOWED_RATIOS = new Set(['1:1','2:3','3:2','3:4','4:3','4:5','5:4','9:16','16:9','21:9']);
const LOCK_HEADINGS = [
  ['style_lock_text', '【STYLE LOCK｜固定原文】'],
  ['scene_or_subject_lock_text', '【SCENE DNA / SUBJECT DNA｜固定原文】'],
  ['spatial_or_structure_lock_text', '【SPATIAL LOCK / STRUCTURE LOCK｜固定原文】'],
  ['continuity_lock_text', '【CONTINUITY LOCK｜固定原文】'],
];

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])]));
  }
  return value;
}

export function stableStringify(value) {
  return JSON.stringify(stable(value));
}

export function payloadSha256(job) {
  const copy = structuredClone(job);
  delete copy.payload_sha256;
  return `sha256:${crypto.createHash('sha256').update(stableStringify(copy)).digest('hex')}`;
}

export function extractHardLocks(prompt) {
  const text = String(prompt || '');
  const result = {};
  for (const [key, heading] of LOCK_HEADINGS) {
    const startAt = text.indexOf(heading);
    if (startAt < 0) throw new Error(`prompt missing hard-lock heading: ${heading}`);
    const contentStart = startAt + heading.length;
    let contentEnd = text.length;
    for (const [, nextHeading] of LOCK_HEADINGS) {
      const candidate = text.indexOf(nextHeading, contentStart);
      if (candidate >= 0 && candidate < contentEnd) contentEnd = candidate;
    }
    const anyHeading = text.slice(contentStart).match(/\n【[^】]+】/);
    if (anyHeading) contentEnd = Math.min(contentEnd, contentStart + anyHeading.index);
    const value = text.slice(contentStart, contentEnd).trim();
    if (!value) throw new Error(`empty hard-lock block: ${heading}`);
    result[key] = value;
  }
  return result;
}

export function lockSha256(prompt) {
  const payload = extractHardLocks(prompt);
  return `sha256:${crypto.createHash('sha256').update(stableStringify(payload)).digest('hex')}`;
}

export function validateJob(job) {
  const errors = [];
  const push = message => { if (!errors.includes(message)) errors.push(message); };
  if (!job || typeof job !== 'object' || Array.isArray(job)) {
    return { valid: false, asset_count: 0, payload_sha256: null, errors: ['job must be an object'] };
  }
  for (const key of ['schema_version','project_id','job_id','source','defaults','assets']) {
    if (job[key] === undefined || job[key] === null || job[key] === '') push(`${key} missing`);
  }
  if (!/^2\./.test(String(job.schema_version || ''))) push('schema_version must start with 2.');
  for (const key of ['project_id','job_id']) {
    if (!SAFE_ID.test(String(job[key] || ''))) push(`${key} must match ${SAFE_ID}`);
  }
  if ('shared_asset_root' in job || (job.defaults && 'shared_asset_root' in job.defaults)) {
    push('shared_asset_root must come from OPENCLAW_ASSET_SHARED_ROOT, not payload');
  }
  if (!job.defaults || typeof job.defaults !== 'object' || Array.isArray(job.defaults)) {
    push('defaults must be an object');
  } else {
    for (const key of ['model','image_size','review_model','review_min_score','review_max_retries']) {
      if (job.defaults[key] === undefined || job.defaults[key] === null || job.defaults[key] === '') push(`defaults.${key} missing`);
    }
  }
  if (!Array.isArray(job.assets) || job.assets.length === 0) push('assets must be non-empty array');

  const ids = new Set();
  const filenames = new Set();
  const assetMap = new Map();
  for (const [index, asset] of (Array.isArray(job.assets) ? job.assets : []).entries()) {
    const label = `assets[${index}]`;
    if (!asset || typeof asset !== 'object' || Array.isArray(asset)) {
      push(`${label} must be an object`);
      continue;
    }
    for (const key of ['asset_id','category','name','filename','prompt_zh','aspect_ratio','generation_stage','lock_id','lock_hash']) {
      if (asset[key] === undefined || asset[key] === null || asset[key] === '') push(`${label}.${key} missing`);
    }
    if (!SAFE_ID.test(String(asset.asset_id || ''))) push(`${label}.asset_id must match ${SAFE_ID}`);
    if (!SAFE_FILENAME.test(String(asset.filename || ''))) push(`${label}.filename must be a safe image filename`);
    if (ids.has(asset.asset_id)) push(`duplicate asset_id: ${asset.asset_id}`);
    if (filenames.has(asset.filename)) push(`duplicate filename: ${asset.filename}`);
    ids.add(asset.asset_id);
    filenames.add(asset.filename);
    assetMap.set(asset.asset_id, asset);
    if (!ALLOWED_RATIOS.has(String(asset.aspect_ratio || ''))) push(`${asset.asset_id}: unsupported aspect_ratio`);
    if (!['anchor','derived','shot'].includes(asset.generation_stage)) push(`${asset.asset_id}: invalid generation_stage`);
    if (['location','scene','shot'].includes(asset.category)) {
      if (!Array.isArray(asset.scene_ids) || asset.scene_ids.length === 0 || asset.scene_ids.some(id => !SAFE_ID.test(String(id)))) {
        push(`${asset.asset_id}: location/scene/shot asset requires safe scene_ids[]`);
      }
      for (const key of ['location_id','sub_location_id','location_asset_id']) {
        if (!SAFE_ID.test(String(asset[key] || ''))) push(`${asset.asset_id}: ${key} is required for scene-bound assets`);
      }
    }
    if (asset.generation_stage === 'shot' && !SAFE_ID.test(String(asset.scene_id || ''))) {
      push(`${asset.asset_id}: shot asset requires scene_id`);
    }
    if (!String(asset.prompt_zh || '').startsWith('【PORTABLE HARD LOCK｜独立可用｜禁止删减】')) {
      push(`${asset.asset_id}: prompt must start with PORTABLE HARD LOCK banner`);
    }
    if (!SHA256.test(String(asset.lock_hash || ''))) {
      push(`${asset.asset_id}: lock_hash must be sha256:<64 lowercase hex>`);
    } else {
      try {
        const expected = lockSha256(asset.prompt_zh);
        if (asset.lock_hash !== expected) push(`${asset.asset_id}: lock_hash mismatch; expected ${expected}`);
      } catch (error) {
        push(`${asset.asset_id}: ${error.message}`);
      }
    }
    if (!Array.isArray(asset.depends_on)) push(`${asset.asset_id}: depends_on must be an array`);
    if (!Array.isArray(asset.reference_inputs)) push(`${asset.asset_id}: reference_inputs must be an array`);
    for (const ref of (Array.isArray(asset.reference_inputs) ? asset.reference_inputs : [])) {
      if (!ref || !SAFE_ID.test(String(ref.asset_id || '')) || !String(ref.role || '').trim()) {
        push(`${asset.asset_id}: invalid reference input`);
      }
      if (ref.required && ref.approved_only !== true) push(`${asset.asset_id}: required ref must be approved_only=true`);
    }
  }

  for (const asset of assetMap.values()) {
    const refs = new Set((asset.reference_inputs || []).map(ref => ref.asset_id));
    for (const dep of (asset.depends_on || [])) {
      if (!SAFE_ID.test(String(dep || ''))) push(`${asset.asset_id}: invalid dependency id ${dep}`);
      if (!assetMap.has(dep) && !refs.has(dep)) {
        push(`${asset.asset_id}: external dependency ${dep} must be declared in reference_inputs`);
      }
    }
  }

  const state = new Map();
  function visit(id, stack = []) {
    const current = state.get(id) || 0;
    if (current === 1) { push(`dependency cycle: ${[...stack,id].join(' -> ')}`); return; }
    if (current === 2) return;
    state.set(id, 1);
    const asset = assetMap.get(id);
    for (const dep of (asset?.depends_on || [])) if (assetMap.has(dep)) visit(dep, [...stack,id]);
    state.set(id, 2);
  }
  for (const id of assetMap.keys()) visit(id);

  const computedPayload = payloadSha256(job);
  if (job.payload_sha256 && job.payload_sha256 !== computedPayload) {
    push(`payload_sha256 mismatch; expected ${computedPayload}`);
  }
  return {
    valid: errors.length === 0,
    asset_count: assetMap.size,
    payload_sha256: computedPayload,
    errors,
  };
}

async function main() {
  const file = process.argv[2];
  if (!file) {
    console.error('Usage: validate-continuity-job.mjs <job.json>');
    process.exit(2);
  }
  let job;
  try {
    job = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (error) {
    console.error(JSON.stringify({ valid: false, errors: [`cannot read job: ${error.message}`] }, null, 2));
    process.exit(2);
  }
  const result = validateJob(job);
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.valid ? 0 : 1);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
