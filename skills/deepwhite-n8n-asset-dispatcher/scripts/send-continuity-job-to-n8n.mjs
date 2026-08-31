#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { payloadSha256, validateJob } from './validate-continuity-job.mjs';

const args = process.argv.slice(2);
const file = args.find(arg => !arg.startsWith('--'));
const dryRun = args.includes('--dry-run');
const wait = args.includes('--wait');
const option = name => args.find(arg => arg.startsWith(`--${name}=`))?.slice(name.length + 3);
const timeoutMs = Number(option('timeout') || 3_600_000);
const requestTimeoutMs = Number(option('request-timeout') || 60_000);
const snapshotArg = option('registry-snapshot');

if (!file) {
  console.error('Usage: send-continuity-job-to-n8n.mjs <job.json> [--dry-run] [--wait] [--timeout=ms] [--request-timeout=ms] [--registry-snapshot=path]');
  process.exit(2);
}

let job;
try {
  job = JSON.parse(fs.readFileSync(file, 'utf8'));
} catch (error) {
  console.error(`Cannot read job: ${error.message}`);
  process.exit(2);
}

const validation = validateJob(job);
if (!validation.valid) {
  console.error(JSON.stringify(validation, null, 2));
  process.exit(2);
}
const payloadHash = payloadSha256(job);
const payload = { ...job, payload_sha256: payloadHash };

if (dryRun) {
  console.log(JSON.stringify({
    dry_run: true,
    project_id: job.project_id,
    job_id: job.job_id,
    asset_count: job.assets.length,
    payload_sha256: payloadHash,
    validation: 'passed',
  }, null, 2));
  process.exit(0);
}

const webhook = process.env.N8N_ASSET_WEBHOOK_URL;
const secret = process.env.N8N_ASSET_WEBHOOK_SECRET;
if (!webhook || !secret) {
  console.error('N8N_ASSET_WEBHOOK_URL / N8N_ASSET_WEBHOOK_SECRET missing');
  process.exit(2);
}

let response;
try {
  response = await fetch(webhook, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-openclaw-secret': secret,
      'x-openclaw-payload-sha256': payloadHash,
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(requestTimeoutMs),
  });
} catch (error) {
  console.error(`n8n request failed: ${error.message}`);
  process.exit(1);
}

const bodyText = await response.text();
if (!response.ok) {
  console.error(`n8n HTTP ${response.status}: ${bodyText}`);
  process.exit(1);
}
console.log(JSON.stringify({
  submitted: true,
  http_status: response.status,
  payload_sha256: payloadHash,
  status: 'webhook_accepted_unverified',
  response: bodyText.slice(0, 2000),
}, null, 2));
if (!wait) process.exit(0);

const root = path.resolve(process.env.OPENCLAW_ASSET_SHARED_ROOT || '/data/openclaw-assets');
const projectDir = path.resolve(root, job.project_id);
if (projectDir !== root && !projectDir.startsWith(`${root}${path.sep}`)) {
  console.error('Resolved project directory escapes OPENCLAW_ASSET_SHARED_ROOT');
  process.exit(2);
}
const registryPath = path.join(projectDir, 'reference_registry.json');
const deadline = Date.now() + timeoutMs;
const assetById = new Map(job.assets.map(asset => [asset.asset_id, asset]));

function fileSha256(target) {
  return `sha256:${crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex')}`;
}

function bindingMatches(entry, asset) {
  return entry?.job_id === job.job_id
    && entry?.payload_sha256 === payloadHash
    && entry?.lock_hash === asset.lock_hash;
}

function qaEvidenceProblem(entry, asset) {
  const qa = entry?.qa_evidence;
  if (!qa || qa.review_authority !== 'n8n_structured_visual_qa') return 'qa_evidence missing or wrong authority';
  if (qa.pass !== true) return 'qa_evidence.pass is not true';
  if (!Array.isArray(qa.hard_requirement_failures) || qa.hard_requirement_failures.length) {
    return 'qa_evidence hard failures are missing or non-empty';
  }
  const safety = qa.production_safety;
  if (!safety || typeof safety !== 'object' || Array.isArray(safety)) return 'production_safety missing';
  const requiredReferences = (asset.reference_inputs || []).filter(item => item?.required !== false);
  if (requiredReferences.length && safety.reference_consistency_checked !== true) {
    return 'reference consistency was not checked';
  }
  const category = String(asset.category || '').toLowerCase();
  if (requiredReferences.length && ['character','animal','creature'].includes(category)) {
    if (safety.identity_consistency_applicable !== true || safety.identity_consistent !== true) {
      return 'identity continuity did not pass';
    }
  }
  if (requiredReferences.length && ['location','scene','environment','shot','storyboard'].includes(category)) {
    if (safety.scene_topology_applicable !== true || safety.scene_topology_consistent !== true) {
      return 'scene topology continuity did not pass';
    }
  }
  if (asset.asset_role === 'video_reference') {
    if (safety.single_view_clean !== true) return 'video reference is not a clean single view';
    if (safety.contains_multiple_independent_assets !== false) return 'video reference contains multiple assets';
    if (safety.contains_text_or_annotations !== false) return 'video reference contains text or annotations';
  }
  return null;
}

function safeAssetPath(rawPath) {
  const resolved = path.resolve(String(rawPath || ''));
  if (resolved !== projectDir && !resolved.startsWith(`${projectDir}${path.sep}`)) return null;
  return resolved;
}

function snapshotPath() {
  if (!snapshotArg) return null;
  if (path.isAbsolute(snapshotArg) || snapshotArg.split(/[\\/]+/).includes('..')) {
    throw new Error('--registry-snapshot must be a relative path inside the current workspace');
  }
  return path.resolve(process.cwd(), snapshotArg);
}

while (Date.now() < deadline) {
  if (fs.existsSync(registryPath)) {
    try {
      const registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
      const entries = registry.assets || {};
      let approved = 0;
      let failed = 0;
      let currentTerminal = 0;
      const problems = [];
      for (const [id, asset] of assetById.entries()) {
        const entry = entries[id];
        if (!entry || !bindingMatches(entry, asset)) continue;
        if (!['approved','rejected','failed','superseded'].includes(entry.status)) continue;
        currentTerminal += 1;
        if (entry.status !== 'approved') {
          failed += 1;
          problems.push(`${id}: status=${entry.status}`);
          continue;
        }
        const target = safeAssetPath(entry.path);
        if (!target || !fs.isFileSync(target)) {
          failed += 1;
          problems.push(`${id}: output path missing or outside project root`);
          continue;
        }
        const actualSize = fs.statSync(target).size;
        const actualSha = fileSha256(target);
        if (!Number.isInteger(entry.file_size) || entry.file_size !== actualSize) {
          failed += 1;
          problems.push(`${id}: file_size mismatch`);
          continue;
        }
        if (entry.sha256 !== actualSha) {
          failed += 1;
          problems.push(`${id}: sha256 mismatch`);
          continue;
        }
        const qaProblem = qaEvidenceProblem(entry, asset);
        if (qaProblem) {
          failed += 1;
          problems.push(`${id}: ${qaProblem}`);
          continue;
        }
        approved += 1;
      }
      if (currentTerminal === assetById.size) {
        if (failed || approved !== assetById.size) {
          console.error(JSON.stringify({
            registry_complete: true,
            all_required_assets_approved: false,
            registry_path: registryPath,
            approved,
            failed,
            total: assetById.size,
            problems,
          }, null, 2));
          process.exit(3);
        }
        const targetSnapshot = snapshotPath();
        if (targetSnapshot) {
          fs.mkdirSync(path.dirname(targetSnapshot), { recursive: true });
          const temp = `${targetSnapshot}.tmp-${process.pid}-${Date.now()}`;
          fs.writeFileSync(temp, `${JSON.stringify(registry, null, 2)}\n`, 'utf8');
          fs.renameSync(temp, targetSnapshot);
        }
        console.log(JSON.stringify({
          registry_complete: true,
          all_required_assets_approved: true,
          registry_path: registryPath,
          registry_snapshot: targetSnapshot,
          approved,
          failed: 0,
          total: assetById.size,
          payload_sha256: payloadHash,
        }, null, 2));
        process.exit(0);
      }
    } catch (error) {
      if (error?.code !== 'ENOENT') console.error(`registry read warning: ${error.message}`);
    }
  }
  await sleep(3000);
}

console.error(JSON.stringify({
  registry_complete: false,
  error: 'REGISTRY_WAIT_TIMEOUT',
  registry_path: registryPath,
  payload_sha256: payloadHash,
}, null, 2));
process.exit(4);
