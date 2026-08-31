#!/usr/bin/env node
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateJob } from '../skills/deepwhite-n8n-asset-dispatcher/scripts/validate-continuity-job.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const workflowDir = path.join(root, 'workspaces', 'drama-producer', 'integration', 'n8n-production');
const files = [
  '01 资产任务总控（连续依赖与参考图 v2.0）.json',
  '02 连续资产 Worker（依赖门禁+参考图注入 3并发 v2.0）.json',
  '03 连续资产汇总、参考注册与 OpenClaw 回调 v2.0.json',
];

const workflows = files.map(name => ({
  name,
  value: JSON.parse(fs.readFileSync(path.join(workflowDir, name), 'utf8')),
}));

for (const { name, value } of workflows) {
  assert.equal(value.active, false, `${name}: public workflow must not auto-activate on import`);
  const nodeNames = new Set(value.nodes.map(node => node.name));
  assert.equal(nodeNames.size, value.nodes.length, `${name}: duplicate node name`);
  const nodeIds = new Set(value.nodes.map(node => node.id));
  assert.equal(nodeIds.size, value.nodes.length, `${name}: duplicate node id`);
  for (const node of value.nodes) {
    if (typeof node.parameters?.jsCode === 'string') {
      assert.doesNotThrow(() => new Function(node.parameters.jsCode), `${name}/${node.name}: invalid JavaScript`);
    }
  }
  for (const [source, branches] of Object.entries(value.connections || {})) {
    assert(nodeNames.has(source), `${name}: connection source missing: ${source}`);
    for (const outputs of Object.values(branches)) {
      for (const output of outputs || []) {
        for (const connection of output || []) {
          assert(nodeNames.has(connection.node), `${name}: connection target missing: ${connection.node}`);
        }
      }
    }
  }
}

const [controller, worker, summary] = workflows.map(item => item.value);
const codeOf = (workflow, nodeName) => workflow.nodes.find(node => node.name === nodeName)?.parameters?.jsCode || '';
const controllerCode = codeOf(controller, '校验任务并写入文件队列');
assert(controllerCode.includes('OPENCLAW_ASSET_SHARED_ROOT'));
assert(!controllerCode.includes("const ROOT = '/data/openclaw-assets'"));
assert(controllerCode.includes('computedPayloadSha256'));
assert(controllerCode.includes('x-openclaw-payload-sha256'));
assert(controllerCode.includes("['B', 'C'].includes(referenceImageSlot)"));
assert(controllerCode.includes('configuredGenerationModel'));
for (const field of ['asset_role', 'asset_kind', 'angle_id', 'layout_type', 'contains_multiple_independent_assets']) {
  assert(controllerCode.includes(field), `01 does not preserve ${field}`);
}

const workerCode = worker.nodes.map(node => node.parameters?.jsCode || '').join('\n');
assert(!workerCode.includes("const ROOT = '/data/openclaw-assets'"));
assert(workerCode.includes('OPENCLAW_ASSET_SHARED_ROOT'));
assert(workerCode.includes('`sha256:${hash}`'));
assert(workerCode.includes('payload_sha256'));
assert(workerCode.includes('production_safety'));
assert(workerCode.includes('review_production_safety'));
assert(workerCode.includes("review_authority: 'n8n_structured_visual_qa'"));
assert(workerCode.includes('qa_evidence'));
assert(workerCode.includes("['google_gemini', 'openai_images'].includes(asset.generation_provider)"));
assert(workerCode.includes('inlineData: {mimeType, data: data.toString'));
assert(!workerCode.includes("const ROOT = '/data/openclaw-assets'"));

const summaryCode = codeOf(summary, '扫描任务并生成完成清单');
assert(summaryCode.includes("schema_version: '2.1'"));
assert(summaryCode.includes("status: approved ? 'approved' : 'rejected'"));
assert(summaryCode.includes("'n8n_asset_generation_failed'"));
assert(summaryCode.includes('all_required_assets_approved: complete'));
assert(summaryCode.includes("complete ? '.done' : '.failed'"));
assert(summaryCode.includes("final_status: 'failed_missing_status_after_repair'"));
assert(summaryCode.includes('lock_hash: asset.lock_hash ?? null'));
assert(summaryCode.includes('qa_evidence: item.qa_evidence ?? null'));
assert(summaryCode.includes('qa_evidence: record.qa_evidence ?? null'));
const callback = summary.nodes.find(node => node.name === '回调 OpenClaw');
assert.equal(callback.parameters.url, '={{ $env.OPENCLAW_ASSET_CALLBACK_URL }}');
assert(callback.parameters.jsonBody.includes('failed_assets'));

const sample = JSON.parse(fs.readFileSync(path.join(workflowDir, '示例请求_asset-job-v3.json'), 'utf8'));
const validation = validateJob(sample);
assert.equal(validation.valid, true, validation.errors.join('; '));
assert.equal(sample.assets.length, 3);
for (const asset of sample.assets) {
  assert.equal(asset.aspect_ratio, '9:16');
  assert.equal(asset.asset_role, 'video_reference');
  assert.equal(asset.layout_type, 'single_view_clean');
  assert.equal(asset.contains_multiple_independent_assets, false);
  assert(asset.angle_id);
}

const wrapper = fs.readFileSync(path.join(root, 'workspaces', 'drama-producer', 'scripts', 'submit_asset_job.py'), 'utf8');
assert(wrapper.includes('send-continuity-job-to-n8n.mjs'));
assert(wrapper.includes('"--wait", "--registry-snapshot=assets/reference_registry.json"'));
assert(wrapper.includes('strict_success'));

const strictSender = fs.readFileSync(
  path.join(root, 'skills', 'deepwhite-n8n-asset-dispatcher', 'scripts', 'send-continuity-job-to-n8n.mjs'),
  'utf8'
);
assert(strictSender.includes('function qaEvidenceProblem'));
assert(strictSender.includes("review_authority !== 'n8n_structured_visual_qa'"));

const ingest = fs.readFileSync(
  path.join(root, 'workspaces', 'drama-producer', 'scripts', 'ingest_asset_evidence.py'),
  'utf8'
);
assert(ingest.includes('n8n_semantic_authority_agent_exception_only'));
assert(ingest.includes('asset_review_exceptions.json'));

const agentContract = fs.readFileSync(
  path.join(root, 'workspaces', 'drama-producer', 'AGENTS.md'),
  'utf8'
);
assert(agentContract.includes('n8n Worker 的逐图结构化质检是图片语义审核的唯一权威'));
assert(agentContract.includes('drama-producer 不得对同一批图片再做一次全量语义审核'));
assert(agentContract.includes('只有 `review/asset_review_exceptions.json` 中列出的图片允许由 Agent 打开检查'));

console.log('n8n production workflow contract passed');
