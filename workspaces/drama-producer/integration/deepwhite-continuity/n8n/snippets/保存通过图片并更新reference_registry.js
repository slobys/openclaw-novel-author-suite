const fs = require('fs');
const path = require('path');
const meta = $('提取生成图片').item.json;
if (!meta.base64) throw new Error('缺少生成图片 Base64');
fs.mkdirSync(path.dirname(meta.output_path), { recursive: true });
fs.writeFileSync(meta.output_path, Buffer.from(meta.base64, 'base64'));
let registry = { schema_version: '2.0', project_id: meta.project_id, updated_at: new Date().toISOString(), assets: {} };
if (fs.existsSync(meta.registry_path)) registry = JSON.parse(fs.readFileSync(meta.registry_path, 'utf8'));
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
  generated_at: new Date().toISOString()
};
const tmp = `${meta.registry_path}.tmp-${process.pid}`;
fs.writeFileSync(tmp, JSON.stringify(registry, null, 2), 'utf8');
fs.renameSync(tmp, meta.registry_path);
return [{ json: { ...meta, final_status: 'approved', registry_path: meta.registry_path } }];