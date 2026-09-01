#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

const args = process.argv.slice(2);
const file = args.find(a => !a.startsWith('--'));
const dryRun = args.includes('--dry-run');
const wait = args.includes('--wait');
const timeoutArg = args.find(a => a.startsWith('--timeout='));
const timeoutMs = Number(timeoutArg?.split('=')[1] || 3600000);
if (!file) {
  console.error('Usage: send-continuity-job-to-n8n.mjs <job.json> [--dry-run] [--wait] [--timeout=ms]');
  process.exit(2);
}
const job = JSON.parse(fs.readFileSync(file, 'utf8'));
const webhook = process.env.N8N_ASSET_WEBHOOK_URL;
const secret = process.env.N8N_ASSET_WEBHOOK_SECRET;
if (!webhook || !secret) {
  console.error('N8N_ASSET_WEBHOOK_URL / N8N_ASSET_WEBHOOK_SECRET missing');
  process.exit(2);
}
if (dryRun) {
  console.log(JSON.stringify({dry_run:true, project_id:job.project_id, job_id:job.job_id, asset_count:job.assets?.length || 0}, null, 2));
  process.exit(0);
}
const res = await fetch(webhook, {
  method:'POST',
  headers:{'content-type':'application/json','x-openclaw-secret':secret},
  body:JSON.stringify(job),
});
const bodyText = await res.text();
if (!res.ok) {
  console.error(`n8n HTTP ${res.status}: ${bodyText}`);
  process.exit(1);
}
console.log(JSON.stringify({submitted:true,http_status:res.status,response:bodyText.slice(0,2000)}, null, 2));
if (!wait) process.exit(0);
const root = process.env.OPENCLAW_ASSET_SHARED_ROOT || '/data/openclaw-assets';
const registryPath = path.join(root, String(job.project_id), 'reference_registry.json');
const targets = new Set((job.assets || []).map(a => a.asset_id));
const deadline = Date.now() + timeoutMs;
while (Date.now() < deadline) {
  if (fs.existsSync(registryPath)) {
    try {
      const registry = JSON.parse(fs.readFileSync(registryPath,'utf8'));
      const entries = registry.assets || {};
      let terminal = 0;
      let approved = 0;
      let failed = 0;
      for (const id of targets) {
        const s = entries[id]?.status;
        if (['approved','rejected','failed','superseded'].includes(s)) terminal++;
        if (s === 'approved') approved++;
        if (['rejected','failed','superseded'].includes(s)) failed++;
      }
      if (terminal === targets.size) {
        console.log(JSON.stringify({registry_complete:true,registry_path:registryPath,approved,failed,total:targets.size}, null, 2));
        process.exit(failed ? 3 : 0);
      }
    } catch {}
  }
  await sleep(5000);
}
console.error(`Timed out waiting for registry: ${registryPath}`);
process.exit(4);
