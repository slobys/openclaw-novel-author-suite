#!/usr/bin/env node

import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const argumentsList = process.argv.slice(2);
const file = argumentsList.find((value) => !value.startsWith('--'));
const dryRun = argumentsList.includes('--dry-run');
const waitForRegistry = argumentsList.includes('--wait');
const verifyRegistryOnly = argumentsList.includes('--verify-registry-only');
const timeoutArgument = argumentsList.find((value) => value.startsWith('--timeout='));
const snapshotArgument = argumentsList.find((value) => value.startsWith('--registry-snapshot='));
const timeoutMs = Number(timeoutArgument?.split('=', 2)[1] ?? 3_600_000);
const snapshotPath = snapshotArgument ? snapshotArgument.split('=', 2)[1] : null;

const ALLOWED_CATEGORIES = new Set([
  'character', 'animal', 'creature', 'location', 'prop', 'style', 'storyboard', 'other',
]);
const ALLOWED_RATIOS = new Set(['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9']);
const ALLOWED_SIZES = new Set(['1K', '2K', '4K']);
const SAFE_ID = /^[A-Za-z0-9_-]+$/;
const SAFE_FILENAME = /^[A-Za-z0-9_-]+\.png$/;
const SHA256 = /^[a-f0-9]{64}$/;
const TERMINAL_STATUSES = new Set(['approved', 'rejected', 'failed', 'superseded']);

function fail(message, code = 1) {
  console.error(`[asset-dispatcher] ${message}`);
  process.exit(code);
}

function assertString(value, field) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${field} 必须是非空字符串`);
}

function stable(value) {
  if (Array.isArray(value)) return value.map(stable);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, stable(value[key])]));
  }
  return value;
}

function payloadSha256(job) {
  const hashable = structuredClone(job);
  delete hashable.payload_sha256;
  return `sha256:${crypto.createHash('sha256').update(JSON.stringify(stable(hashable))).digest('hex')}`;
}

function normalizedSha(value) {
  return String(value ?? '').replace(/^sha256:/, '');
}

function fileSha256(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function validateJob(job) {
  if (!job || typeof job !== 'object' || Array.isArray(job)) throw new Error('任务根节点必须是对象');
  for (const field of ['schema_version', 'job_id', 'project_id', 'source']) assertString(job[field], field);
  if (!SAFE_ID.test(job.job_id) || !SAFE_ID.test(job.project_id)) throw new Error('project_id/job_id 含不安全字符');
  if (!job.defaults || typeof job.defaults !== 'object' || Array.isArray(job.defaults)) throw new Error('defaults 必须是对象');
  assertString(job.defaults.model, 'defaults.model');
  if (!ALLOWED_SIZES.has(job.defaults.image_size)) throw new Error('defaults.image_size 不受支持');
  if (!Array.isArray(job.assets) || job.assets.length === 0) throw new Error('assets 必须是非空数组');

  const strict = String(job.schema_version).startsWith('2.') || job.assets.some((asset) => asset.reference_inputs !== undefined);
  const ids = new Set();
  const filenames = new Set();
  const assetMap = new Map();
  for (const [index, asset] of job.assets.entries()) {
    const prefix = `assets[${index}]`;
    for (const field of ['asset_id', 'category', 'name', 'filename']) assertString(asset[field], `${prefix}.${field}`);
    if (!SAFE_ID.test(asset.asset_id)) throw new Error(`${prefix}.asset_id 含不安全字符`);
    if (!SAFE_FILENAME.test(asset.filename)) throw new Error(`${prefix}.filename 必须是 ASCII 安全的 .png`);
    if (!ALLOWED_CATEGORIES.has(asset.category)) throw new Error(`${prefix}.category 不受支持：${asset.category}`);
    if (ids.has(asset.asset_id) || filenames.has(asset.filename)) throw new Error(`${prefix} 的 asset_id/filename 重复`);
    ids.add(asset.asset_id);
    filenames.add(asset.filename);
    assetMap.set(asset.asset_id, asset);

    if (!String(asset.prompt_zh ?? '').trim() && !String(asset.prompt_en ?? '').trim()) {
      throw new Error(`${prefix} 至少需要 prompt_zh 或 prompt_en`);
    }
    const ratio = asset.aspect_ratio ?? job.defaults.aspect_ratio;
    const size = asset.image_size ?? job.defaults.image_size;
    if (!ALLOWED_RATIOS.has(ratio)) throw new Error(`${prefix}.aspect_ratio 不受支持`);
    if (!ALLOWED_SIZES.has(size)) throw new Error(`${prefix}.image_size 不受支持`);
    if ((asset.reference_images ?? []).length > 2) throw new Error(`${prefix} 直接参考图超过 2 张`);

    const referenceInputs = asset.reference_inputs ?? [];
    if (!Array.isArray(referenceInputs)) throw new Error(`${prefix}.reference_inputs 必须是数组`);
    let requiredReferences = (asset.reference_images ?? []).length;
    for (const [referenceIndex, reference] of referenceInputs.entries()) {
      if (!reference || typeof reference !== 'object' || Array.isArray(reference)) {
        throw new Error(`${prefix}.reference_inputs[${referenceIndex}] 必须是对象`);
      }
      const hasAsset = typeof reference.asset_id === 'string' && reference.asset_id.length > 0;
      const hasPath = typeof reference.path === 'string' && reference.path.length > 0;
      if (hasAsset === hasPath) throw new Error(`${prefix}.reference_inputs[${referenceIndex}] 必须且只能填写 asset_id 或 path`);
      if (reference.required !== false) {
        requiredReferences += 1;
        if (reference.approved_only !== true) throw new Error(`${prefix} 的必需参考必须 approved_only=true`);
      }
    }
    if (requiredReferences > 2) throw new Error(`${prefix} 的必需参考图超过执行分支上限 2 张`);

    if (strict) {
      for (const field of ['lock_id', 'lock_hash', 'asset_lineage_id', 'revision_reason_code']) {
        assertString(asset[field], `${prefix}.${field}`);
      }
      if (!SHA256.test(String(asset.requirement_sha256 ?? ''))) {
        throw new Error(`${prefix}.requirement_sha256 必须为64位小写SHA256`);
      }
      if (String(asset.acceptance_policy ?? 'strict_only').toLowerCase() !== 'strict_only') {
        throw new Error(`${prefix}.acceptance_policy 必须为 strict_only`);
      }
      if (asset.category === 'location') {
        if (!Array.isArray(asset.scene_ids) || asset.scene_ids.length === 0) {
          throw new Error(`${prefix}.scene_ids 必须是非空数组`);
        }
        for (const field of ['location_id', 'sub_location_id', 'location_asset_id']) {
          assertString(asset[field], `${prefix}.${field}`);
        }
      }
    }
  }

  const visiting = new Set();
  const visited = new Set();
  function visit(assetId, stack = []) {
    if (visiting.has(assetId)) throw new Error(`依赖图存在环：${[...stack, assetId].join(' -> ')}`);
    if (visited.has(assetId)) return;
    visiting.add(assetId);
    for (const dependency of assetMap.get(assetId)?.depends_on ?? []) {
      if (assetMap.has(dependency)) visit(dependency, [...stack, assetId]);
    }
    visiting.delete(assetId);
    visited.add(assetId);
  }
  for (const assetId of assetMap.keys()) visit(assetId);
  return { strict };
}

async function postWithRetry(url, secret, body, digest) {
  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30_000);
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-openclaw-secret': secret,
          'x-openclaw-payload-sha256': digest,
          'user-agent': 'openclaw-asset-dispatcher/2.1',
        },
        body,
        signal: controller.signal,
      });
      const text = await response.text();
      if (response.ok) return { httpStatus: response.status, text };
      const error = new Error(`HTTP ${response.status}: ${text.slice(0, 1000)}`);
      error.retryable = response.status === 429 || response.status >= 500;
      throw error;
    } catch (error) {
      lastError = error;
      if (error.retryable === false || attempt === 3) throw error;
    } finally {
      clearTimeout(timeout);
    }
    await new Promise((resolve) => setTimeout(resolve, Math.min(1000 * 2 ** (attempt - 1), 4000)));
  }
  throw lastError;
}

function sharedRoot() {
  if (process.env.OPENCLAW_ASSET_SHARED_ROOT) return path.resolve(process.env.OPENCLAW_ASSET_SHARED_ROOT);
  throw new Error('OPENCLAW_ASSET_SHARED_ROOT missing');
}

function resolveEntryPath(rawPath, root) {
  const value = String(rawPath ?? '').trim();
  const containerRoot = '/data/openclaw-assets/';
  const resolved = value.startsWith(containerRoot)
    ? path.resolve(root, value.slice(containerRoot.length))
    : path.resolve(value);
  const safeRoot = path.resolve(root) + path.sep;
  if (!resolved.startsWith(safeRoot)) throw new Error('Registry 资产路径超出固定共享根');
  return resolved;
}

function verifyApprovedEntry(entry, asset, job, digest, root) {
  if (entry.job_id !== job.job_id || entry.project_id !== job.project_id) throw new Error(`${asset.asset_id}: Registry job/project 绑定错误`);
  if (entry.payload_sha256 !== digest) throw new Error(`${asset.asset_id}: Registry payload_sha256 不匹配`);
  if (normalizedSha(entry.lock_hash) !== normalizedSha(asset.lock_hash)) throw new Error(`${asset.asset_id}: Registry lock_hash 不匹配`);
  if (entry.asset_lineage_id !== asset.asset_lineage_id || normalizedSha(entry.requirement_sha256) !== normalizedSha(asset.requirement_sha256)) {
    throw new Error(`${asset.asset_id}: Registry 资产血缘不匹配`);
  }
  const assetPath = resolveEntryPath(entry.path, root);
  const stat = fs.statSync(assetPath);
  if (!stat.isFile() || stat.size <= 0 || stat.size !== Number(entry.file_size)) throw new Error(`${asset.asset_id}: Registry 文件大小不匹配`);
  if (fileSha256(assetPath) !== normalizedSha(entry.sha256)) throw new Error(`${asset.asset_id}: Registry 文件 SHA256 不匹配`);
  const qa = entry.qa_evidence ?? {};
  if (qa.review_authority !== 'n8n_structured_visual_qa' || qa.pass !== true || (qa.hard_failures ?? []).length > 0) {
    throw new Error(`${asset.asset_id}: Registry QA 证据不完整`);
  }
  const safety = entry.production_safety ?? {};
  for (const field of ['single_view_clean', 'text_annotations_absent', 'multi_panel_absent', 'subject_count_valid']) {
    if (safety[field] !== true) throw new Error(`${asset.asset_id}: production_safety.${field} 未通过`);
  }
  if ((entry.ambiguity_reasons ?? safety.ambiguity_reasons ?? []).length > 0) throw new Error(`${asset.asset_id}: Registry 仍有歧义`);
  const loadedReferences = Array.isArray(entry.reference_images_loaded) ? entry.reference_images_loaded : [];
  const requiredInputs = (asset.reference_inputs ?? []).filter((reference) => reference.required !== false);
  const minimumLoadedReferences = (asset.reference_images ?? []).length + requiredInputs.length;
  if (loadedReferences.length < minimumLoadedReferences) {
    throw new Error(`${asset.asset_id}: 必需参考图未全部真实注入模型输入`);
  }
  for (const [index, loaded] of loadedReferences.entries()) {
    if (!loaded || typeof loaded !== 'object') throw new Error(`${asset.asset_id}: reference_images_loaded[${index}] 证据无效`);
    const loadedPath = resolveEntryPath(loaded.path, root);
    const loadedStat = fs.statSync(loadedPath);
    if (!loadedStat.isFile() || loadedStat.size <= 0 || loadedStat.size !== Number(loaded.bytes)) {
      throw new Error(`${asset.asset_id}: reference_images_loaded[${index}] 文件大小不匹配`);
    }
    if (fileSha256(loadedPath) !== normalizedSha(loaded.sha256)) {
      throw new Error(`${asset.asset_id}: reference_images_loaded[${index}] SHA256 不匹配`);
    }
  }
  const resolvedInputs = Array.isArray(entry.resolved_reference_inputs) ? entry.resolved_reference_inputs : [];
  for (const required of requiredInputs) {
    const matched = required.asset_id
      ? resolvedInputs.find((reference) => reference?.asset_id === required.asset_id)
      : resolvedInputs.find((reference) => path.resolve(String(reference?.path ?? reference?.source_path ?? '')) === path.resolve(String(required.path ?? '')));
    if (!matched) throw new Error(`${asset.asset_id}: 必需 reference_input 未解析：${required.asset_id ?? required.path}`);
  }
  if (asset.asset_role === 'video_reference' && entry.video_reference_eligible !== true) {
    throw new Error(`${asset.asset_id}: 未通过视频参考安全 Gate`);
  }
}

function atomicJson(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
  fs.renameSync(temporary, filePath);
}

async function waitForVerifiedRegistry(job, digest) {
  const root = sharedRoot();
  const registryPath = path.join(root, job.project_id, 'reference_registry.json');
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (fs.existsSync(registryPath)) {
      let terminalRegistryObserved = false;
      try {
        const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
        const entries = registry.assets ?? {};
        const selected = job.assets.map((asset) => entries[asset.asset_id]).filter(Boolean);
        if (selected.length === job.assets.length && selected.every((entry) => TERMINAL_STATUSES.has(entry.status))) {
          terminalRegistryObserved = true;
          const failures = job.assets.filter((asset) => entries[asset.asset_id].status !== 'approved');
          if (failures.length > 0) {
            return { verified: false, terminal: true, registryPath, failures: failures.map((asset) => asset.asset_id) };
          }
          for (const asset of job.assets) verifyApprovedEntry(entries[asset.asset_id], asset, job, digest, root);
          if (snapshotPath) atomicJson(path.resolve(snapshotPath), registry);
          return { verified: true, terminal: true, registryPath, approved: job.assets.length };
        }
      } catch (error) {
        // Registry is written atomically. Once every requested asset is
        // terminal, any verification failure is authoritative and must not be
        // converted into a misleading wait timeout.
        if (terminalRegistryObserved) throw error;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error(`等待 reference_registry 超时：${registryPath}`);
}

try {
  if (!file) throw new Error('请传入 asset job JSON 文件');
  const job = JSON.parse(fs.readFileSync(file, 'utf8'));
  const { strict } = validateJob(job);
  const digest = payloadSha256(job);
  job.payload_sha256 = digest;
  const body = JSON.stringify(job);
  if (dryRun) {
    console.log(JSON.stringify({ ok: true, dry_run: true, strict, job_id: job.job_id, project_id: job.project_id, asset_count: job.assets.length, payload_sha256: digest }, null, 2));
    process.exit(0);
  }
  if (verifyRegistryOnly) {
    const registry = await waitForVerifiedRegistry(job, digest);
    if (!registry.verified) {
      console.log(JSON.stringify({ ok: false, status: 'terminal_failed', job_id: job.job_id, project_id: job.project_id, ...registry }, null, 2));
      process.exit(3);
    }
    console.log(JSON.stringify({ ok: true, status: 'verified_existing_registry', job_id: job.job_id, project_id: job.project_id, ...registry }, null, 2));
    process.exit(0);
  }
  const url = process.env.N8N_ASSET_WEBHOOK_URL;
  const secret = process.env.N8N_ASSET_WEBHOOK_SECRET;
  if (!url || !secret) throw new Error('N8N_ASSET_WEBHOOK_URL / N8N_ASSET_WEBHOOK_SECRET missing');
  const response = await postWithRetry(url, secret, body, digest);
  let responseJson = {};
  try { responseJson = response.text.trim() ? JSON.parse(response.text) : {}; } catch {}

  let fixedJobVerified = false;
  const root = sharedRoot();
  const fixedJobPath = path.join(root, job.project_id, job.job_id, 'job.json');
  if (fs.existsSync(fixedJobPath)) {
    const fixedJob = JSON.parse(fs.readFileSync(fixedJobPath, 'utf8'));
    fixedJobVerified = fixedJob.job_id === job.job_id && fixedJob.project_id === job.project_id && fixedJob.payload_sha256 === digest;
  }
  if (waitForRegistry) {
    const registry = await waitForVerifiedRegistry(job, digest);
    if (!registry.verified) {
      console.log(JSON.stringify({ ok: false, http_status: response.httpStatus, status: 'terminal_failed', job_id: job.job_id, project_id: job.project_id, ...registry }, null, 2));
      process.exit(3);
    }
    console.log(JSON.stringify({ ok: true, http_status: response.httpStatus, status: 'verified', job_id: job.job_id, project_id: job.project_id, fixed_job_verified: fixedJobVerified, ...registry }, null, 2));
    process.exit(0);
  }
  console.log(JSON.stringify({
    ok: true, http_status: response.httpStatus,
    status: fixedJobVerified ? 'execution_confirmed' : 'webhook_accepted_unverified',
    job_id: job.job_id, project_id: job.project_id, asset_count: job.assets.length,
    fixed_job_verified: fixedJobVerified,
    execution_id: responseJson.execution_id ?? responseJson.executionId ?? null,
  }, null, 2));
} catch (error) {
  fail(error instanceof Error ? error.message : String(error), 2);
}
