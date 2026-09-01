#!/usr/bin/env node
import fs from 'node:fs';

const file = process.argv[2];
if (!file) {
  console.error('Usage: validate-continuity-job.mjs <asset-job.json>');
  process.exit(2);
}
const job = JSON.parse(fs.readFileSync(file, 'utf8'));
const errors = [];
if (!job || typeof job !== 'object') errors.push('job must be object');
if (!Array.isArray(job.assets) || job.assets.length === 0) errors.push('assets must be non-empty array');
const ids = new Set();
const filenames = new Set();
const assetMap = new Map();
for (const [index, a] of (job.assets || []).entries()) {
  const p = `assets[${index}]`;
  for (const k of ['asset_id','category','name','filename','prompt_zh','aspect_ratio','generation_stage']) {
    if (!a[k]) errors.push(`${p}.${k} missing`);
  }
  if (ids.has(a.asset_id)) errors.push(`duplicate asset_id: ${a.asset_id}`);
  ids.add(a.asset_id);
  if (filenames.has(a.filename)) errors.push(`duplicate filename: ${a.filename}`);
  filenames.add(a.filename);
  assetMap.set(a.asset_id, a);
  if (!String(a.prompt_zh || '').includes('PORTABLE HARD LOCK')) errors.push(`${a.asset_id}: prompt missing PORTABLE HARD LOCK`);
  if (!a.lock_id || !a.lock_hash) errors.push(`${a.asset_id}: lock_id/lock_hash missing`);
  for (const ref of (a.reference_inputs || [])) {
    if (!ref.asset_id || !ref.role) errors.push(`${a.asset_id}: invalid reference input`);
    if (ref.required && ref.approved_only !== true) errors.push(`${a.asset_id}: required ref must be approved_only=true`);
  }
}
// Graph cycle check for dependencies that are in this job.
const state = new Map();
function visit(id, stack=[]) {
  const s = state.get(id) || 0;
  if (s === 1) { errors.push(`dependency cycle: ${[...stack,id].join(' -> ')}`); return; }
  if (s === 2) return;
  state.set(id,1);
  const a = assetMap.get(id);
  for (const dep of (a?.depends_on || [])) if (assetMap.has(dep)) visit(dep,[...stack,id]);
  state.set(id,2);
}
for (const id of assetMap.keys()) visit(id);
if (errors.length) {
  console.error(JSON.stringify({valid:false, errors}, null, 2));
  process.exit(1);
}
console.log(JSON.stringify({valid:true, asset_count:job.assets.length}, null, 2));
