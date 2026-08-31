const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const meta = $('提取生成图片').item.json;
if (!meta.base64) throw new Error('缺少生成图片 Base64');
const bytes = Buffer.from(meta.base64, 'base64');
if (!bytes.length) throw new Error('生成图片为空');
fs.mkdirSync(path.dirname(meta.output_path), { recursive: true });
fs.writeFileSync(meta.output_path, bytes);
const sha256 = `sha256:${crypto.createHash('sha256').update(bytes).digest('hex')}`;
const lockDir = `${meta.registry_path}.lock`;
try {
  fs.mkdirSync(lockDir);
} catch (error) {
  throw new Error(`REGISTRY_WRITE_LOCKED: ${error.message}`);
}
try {
  let registry = { schema_version: '2.1', project_id: meta.project_id, updated_at: new Date().toISOString(), assets: {} };
  if (fs.existsSync(meta.registry_path)) registry = JSON.parse(fs.readFileSync(meta.registry_path, 'utf8'));
  registry.schema_version = '2.1';
  registry.project_id = meta.project_id;
  registry.assets = registry.assets || {};
  registry.updated_at = new Date().toISOString();
  registry.assets[meta.asset_id] = {
    asset_id: meta.asset_id,
    parent_asset_id: meta.parent_asset_id || null,
    filename: meta.filename,
    path: meta.output_path,
    mime_type: meta.mime_type || 'image/png',
    status: 'approved',
    qa_score: Number(meta.review_score || 100),
    anchor_roles: meta.anchor_roles || [],
    lock_id: meta.lock_id,
    lock_hash: meta.lock_hash,
    job_id: meta.job_id,
    payload_sha256: meta.payload_sha256,
    sha256,
    file_size: bytes.length,
    generated_at: new Date().toISOString(),
  };
  const temp = `${meta.registry_path}.tmp-${process.pid}-${Date.now()}-${crypto.randomUUID()}`;
  fs.writeFileSync(temp, JSON.stringify(registry, null, 2), 'utf8');
  fs.renameSync(temp, meta.registry_path);
} finally {
  fs.rmSync(lockDir, { recursive: true, force: true });
}
return [{ json: { ...meta, final_status: 'approved', registry_path: meta.registry_path, sha256, file_size: bytes.length } }];
