const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const asset = $json;
const projectDir = path.resolve(asset.shared_asset_root, asset.project_id);
const jobDir = path.resolve(projectDir, asset.job_id);
const rejectedDir = path.join(jobDir, '_rejected');
fs.mkdirSync(rejectedDir, { recursive: true });
const rejectedPath = path.join(rejectedDir, String(asset.filename).replace(/\.[^.]+$/, '') + `_REJECTED_score_${asset.review_score}.png`);
const bytes = asset.base64 ? Buffer.from(asset.base64, 'base64') : Buffer.alloc(0);
if (bytes.length) fs.writeFileSync(rejectedPath, bytes);
const registryPath = path.join(projectDir, 'reference_registry.json');
const lockDir = `${registryPath}.lock`;
try { fs.mkdirSync(lockDir); } catch (error) { throw new Error(`REGISTRY_WRITE_LOCKED: ${error.message}`); }
try {
  let registry = { schema_version: '2.1', project_id: asset.project_id, updated_at: new Date().toISOString(), assets: {} };
  if (fs.existsSync(registryPath)) registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
  registry.schema_version = '2.1'; registry.project_id = asset.project_id; registry.assets = registry.assets || {}; registry.updated_at = new Date().toISOString();
  registry.assets[asset.asset_id] = {
    asset_id: asset.asset_id, filename: asset.filename, path: bytes.length ? rejectedPath : '', status: 'rejected',
    qa_score: asset.review_score, reason: asset.review_reason, lock_id: asset.lock_id, lock_hash: asset.lock_hash,
    job_id: asset.job_id, payload_sha256: asset.payload_sha256,
    sha256: `sha256:${crypto.createHash('sha256').update(bytes).digest('hex')}`, file_size: bytes.length,
    generated_at: new Date().toISOString(),
  };
  const temp = `${registryPath}.tmp-${process.pid}-${Date.now()}-${crypto.randomUUID()}`;
  fs.writeFileSync(temp, JSON.stringify(registry, null, 2), 'utf8'); fs.renameSync(temp, registryPath);
} finally { fs.rmSync(lockDir, { recursive: true, force: true }); }
return [{ json: { ...asset, final_status: 'rejected', rejected_path: bytes.length ? rejectedPath : '' } }];
