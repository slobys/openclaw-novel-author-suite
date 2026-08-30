#!/usr/bin/env node

import fs from 'node:fs/promises';
import process from 'node:process';

const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const fileArg = args.find((arg) => !arg.startsWith('--'));
const ALLOWED_CATEGORIES = new Set(['character', 'location', 'prop', 'style', 'storyboard', 'other']);
const ALLOWED_RATIOS = new Set(['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9']);
const ALLOWED_IMAGE_SIZES = new Set(['1K', '2K', '4K']);
const SAFE_ID = /^[A-Za-z0-9_-]+$/;
const SAFE_FILENAME = /^[A-Za-z0-9_-]+\.png$/;

function fail(message, code = 1) {
  console.error(`[asset-dispatcher] ${message}`);
  process.exit(code);
}

function assertString(value, field) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`${field} 必须是非空字符串`);
  }
}

function validateJob(job) {
  if (!job || typeof job !== 'object' || Array.isArray(job)) {
    throw new Error('任务根节点必须是 JSON 对象');
  }

  assertString(job.schema_version, 'schema_version');
  assertString(job.job_id, 'job_id');
  assertString(job.project_id, 'project_id');
  assertString(job.source, 'source');
  if (!SAFE_ID.test(job.job_id)) throw new Error('job_id 只能包含字母、数字、下划线和短横线');
  if (!SAFE_ID.test(job.project_id)) throw new Error('project_id 只能包含字母、数字、下划线和短横线');
  if (!job.defaults || typeof job.defaults !== 'object' || Array.isArray(job.defaults)) {
    throw new Error('defaults 必须是 JSON 对象');
  }
  assertString(job.defaults.model, 'defaults.model');
  if (job.defaults.aspect_ratio !== undefined && !ALLOWED_RATIOS.has(job.defaults.aspect_ratio)) {
    throw new Error(`defaults.aspect_ratio 不受支持：${job.defaults.aspect_ratio}`);
  }
  if (!ALLOWED_IMAGE_SIZES.has(job.defaults.image_size)) {
    throw new Error(`defaults.image_size 不受支持：${job.defaults.image_size}`);
  }
  if (job.defaults.model === 'gemini-3.1-flash-lite-image' && job.defaults.image_size !== '1K') {
    throw new Error('gemini-3.1-flash-lite-image 只允许 1K');
  }

  const isSeriesJob = job.style_contract !== undefined || job.style_contract_sha256 !== undefined;
  if (isSeriesJob) {
    if (!job.style_contract || typeof job.style_contract !== 'object' || Array.isArray(job.style_contract)) {
      throw new Error('系列任务必须提供 style_contract 对象');
    }
    assertString(job.style_contract_sha256, 'style_contract_sha256');
  }

  if (!Array.isArray(job.assets) || job.assets.length === 0) {
    throw new Error('assets 必须是非空数组');
  }

  const ids = new Set();
  const filenames = new Set();

  for (const [index, asset] of job.assets.entries()) {
    const prefix = `assets[${index}]`;
    assertString(asset.asset_id, `${prefix}.asset_id`);
    assertString(asset.category, `${prefix}.category`);
    assertString(asset.name, `${prefix}.name`);
    assertString(asset.filename, `${prefix}.filename`);
    if (!SAFE_ID.test(asset.asset_id)) {
      throw new Error(`${prefix}.asset_id 只能包含字母、数字、下划线和短横线`);
    }
    if (!ALLOWED_CATEGORIES.has(asset.category)) {
      throw new Error(`${prefix}.category 不受支持：${asset.category}`);
    }
    if (!SAFE_FILENAME.test(asset.filename)) {
      throw new Error(`${prefix}.filename 必须是 ASCII 安全的 .png 文件名`);
    }

    const zh = typeof asset.prompt_zh === 'string' ? asset.prompt_zh.trim() : '';
    const en = typeof asset.prompt_en === 'string' ? asset.prompt_en.trim() : '';
    if (!zh && !en) {
      throw new Error(`${prefix} 至少需要 prompt_zh 或 prompt_en`);
    }
    if (isSeriesJob && (typeof asset.negative_prompt !== 'string' || !asset.negative_prompt.trim())) {
      throw new Error(`${prefix}.negative_prompt 是系列任务必填字段`);
    }
    const ratio = asset.aspect_ratio ?? job.defaults.aspect_ratio;
    if (!ALLOWED_RATIOS.has(ratio)) {
      throw new Error(`${prefix}.aspect_ratio 不受支持：${ratio}`);
    }
    const imageSize = asset.image_size ?? job.defaults.image_size;
    if (!ALLOWED_IMAGE_SIZES.has(imageSize)) {
      throw new Error(`${prefix}.image_size 不受支持：${imageSize}`);
    }
    const model = asset.model ?? job.defaults.model;
    if (model === 'gemini-3.1-flash-lite-image' && imageSize !== '1K') {
      throw new Error(`${prefix}: gemini-3.1-flash-lite-image 只允许 1K`);
    }
    if (asset.reference_images !== undefined && !Array.isArray(asset.reference_images)) {
      throw new Error(`${prefix}.reference_images 必须是数组`);
    }

    if (ids.has(asset.asset_id)) {
      throw new Error(`重复 asset_id：${asset.asset_id}`);
    }
    if (filenames.has(asset.filename)) {
      throw new Error(`重复 filename：${asset.filename}`);
    }
    ids.add(asset.asset_id);
    filenames.add(asset.filename);
  }
}

async function loadInput() {
  if (fileArg) {
    return fs.readFile(fileArg, 'utf8');
  }

  if (!process.stdin.isTTY) {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    return Buffer.concat(chunks).toString('utf8');
  }

  fail('请传入 JSON 文件路径，或通过 stdin 输入 JSON');
}

async function postWithRetry(url, secret, body, maxAttempts = 4) {
  let lastError;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30_000);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'x-openclaw-secret': secret,
          'user-agent': 'openclaw-n8n-asset-dispatcher/1.0'
        },
        body,
        signal: controller.signal
      });

      const text = await response.text();
      if (response.ok) {
        return { status: response.status, text };
      }

      const retryable = response.status === 429 || response.status >= 500;
      const httpError = new Error(`HTTP ${response.status}: ${text.slice(0, 1000)}`);
      httpError.retryable = retryable;
      throw httpError;
    } catch (error) {
      lastError = error;
      if (error?.retryable === false || attempt === maxAttempts) throw error;
    } finally {
      clearTimeout(timeout);
    }

    const delayMs = Math.min(1000 * 2 ** (attempt - 1), 8000);
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }

  throw lastError ?? new Error('未知提交错误');
}

try {
  const raw = await loadInput();
  const job = JSON.parse(raw);
  validateJob(job);

  if (!job.created_at) job.created_at = new Date().toISOString();
  const body = JSON.stringify(job);

  if (dryRun) {
    console.log(JSON.stringify({
      ok: true,
      dry_run: true,
      job_id: job.job_id,
      project_id: job.project_id,
      asset_count: job.assets.length
    }, null, 2));
    process.exit(0);
  }

  const url = process.env.N8N_ASSET_WEBHOOK_URL;
  const secret = process.env.N8N_ASSET_WEBHOOK_SECRET;
  if (!url) fail('缺少环境变量 N8N_ASSET_WEBHOOK_URL');
  if (!secret) fail('缺少环境变量 N8N_ASSET_WEBHOOK_SECRET');

  const result = await postWithRetry(url, secret, body);
  let responseJson = {};
  try {
    responseJson = result.text.trim() ? JSON.parse(result.text) : {};
  } catch {
    responseJson = {};
  }
  const executionId = responseJson.execution_id
    ?? responseJson.executionId
    ?? responseJson.task_id
    ?? responseJson.taskId
    ?? responseJson.provider_task_id
    ?? null;
  console.log(JSON.stringify({
    ok: true,
    http_status: result.status,
    status: executionId ? 'execution_confirmed' : 'webhook_accepted_unverified',
    execution_id: executionId,
    job_id: job.job_id,
    project_id: job.project_id,
    asset_count: job.assets.length,
    response: result.text.slice(0, 2000)
  }, null, 2));
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
