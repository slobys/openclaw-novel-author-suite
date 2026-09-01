const fs = require('fs');
const path = require('path');
const asset = $json;
const root = asset.shared_asset_root || '/data/openclaw-assets';
const projectDir = path.join(root, asset.project_id);
const jobDir = path.join(projectDir, asset.job_id);
const registryPath = path.join(projectDir, 'reference_registry.json');
fs.mkdirSync(jobDir, { recursive: true });
let registry = { schema_version: '2.0', project_id: asset.project_id, updated_at: new Date().toISOString(), assets: {} };
if (fs.existsSync(registryPath)) registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
const parts = [];
const refsUsed = [];
for (const ref of (asset.reference_inputs || [])) {
  const entry = registry.assets?.[ref.asset_id];
  if (!entry || entry.status !== 'approved') {
    if (ref.required) throw new Error(`${asset.asset_id} 缺少已通过参考图：${ref.asset_id}`);
    continue;
  }
  if (!fs.existsSync(entry.path)) {
    if (ref.required) throw new Error(`${asset.asset_id} 参考图文件不存在：${entry.path}`);
    continue;
  }
  const mime = entry.mime_type || (entry.path.toLowerCase().endsWith('.jpg') || entry.path.toLowerCase().endsWith('.jpeg') ? 'image/jpeg' : 'image/png');
  const data = fs.readFileSync(entry.path).toString('base64');
  parts.push({ text: `[REFERENCE ${refsUsed.length + 1}] asset_id=${ref.asset_id}; role=${ref.role}. 只按该职责使用，不复制其摄影机角度。` });
  parts.push({ inline_data: { mime_type: mime, data } });
  refsUsed.push({ asset_id: ref.asset_id, role: ref.role, path: entry.path });
}
let prompt = String(asset.prompt_zh || asset.prompt_en || '').trim();
if (asset.negative_prompt) prompt += `\n\n【补充负面约束】\n${asset.negative_prompt}`;
if (asset.qa_feedback) prompt += `\n\n【上轮质检修复要求】\n${asset.qa_feedback}`;
parts.push({ text: prompt });
const requestBody = {
  contents: [{ role: 'user', parts }],
  generationConfig: {
    responseModalities: ['TEXT', 'IMAGE'],
    responseFormat: {
      image: {
        aspectRatio: asset.aspect_ratio,
        imageSize: asset.image_size
      }
    }
  }
};
return [{ json: { ...asset, project_dir: projectDir, job_dir: jobDir, registry_path: registryPath, output_path: path.join(jobDir, asset.filename), refs_used: refsUsed, requestBody } }];