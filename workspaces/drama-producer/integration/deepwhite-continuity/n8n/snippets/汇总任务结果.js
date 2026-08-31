const fs = require('fs');
const path = require('path');
const first = $('校验任务并拓扑排序').first().json;
const registryPath = path.join(first.shared_asset_root, first.project_id, 'reference_registry.json');
let registry = { assets: {} };
if (fs.existsSync(registryPath)) registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
const requested = $items('校验任务并拓扑排序').map(item => item.json);
const assets = requested.map(asset => {
  const entry = registry.assets?.[asset.asset_id];
  const binding_valid = Boolean(entry && entry.job_id === first.job_id && entry.payload_sha256 === first.payload_sha256 && entry.lock_hash === asset.lock_hash);
  return { asset_id: asset.asset_id, status: binding_valid ? entry.status : 'unknown', binding_valid };
});
const approved_count = assets.filter(asset => asset.status === 'approved' && asset.binding_valid).length;
const failed_count = assets.length - approved_count;
const ok = assets.length > 0 && failed_count === 0;
return [{ json: {
  ok,
  project_id: first.project_id,
  job_id: first.job_id,
  payload_sha256: first.payload_sha256,
  registry_path: registryPath,
  approved_count,
  failed_count,
  all_required_assets_approved: ok,
  assets,
} }];
