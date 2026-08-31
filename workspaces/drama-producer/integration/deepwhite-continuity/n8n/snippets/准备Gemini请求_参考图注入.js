const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const asset = $json;
const root = path.resolve(String($env.OPENCLAW_ASSET_SHARED_ROOT || '/data/openclaw-assets'));
const projectDir = path.resolve(root, asset.project_id);
if (projectDir !== root && !projectDir.startsWith(`${root}${path.sep}`)) throw new Error('projectDir 越出共享资产根目录');
const jobDir = path.resolve(projectDir, asset.job_id);
if (!jobDir.startsWith(`${projectDir}${path.sep}`)) throw new Error('jobDir 越出项目目录');
const registryPath = path.join(projectDir, 'reference_registry.json');
const outputPath = path.resolve(jobDir, asset.filename);
if (!outputPath.startsWith(`${jobDir}${path.sep}`)) throw new Error('output_path 越出 Job 目录');
fs.mkdirSync(jobDir, { recursive: true });
let registry = { schema_version: '2.1', project_id: asset.project_id, updated_at: new Date().toISOString(), assets: {} };
if (fs.existsSync(registryPath)) registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
if (registry.project_id && registry.project_id !== asset.project_id) throw new Error('reference_registry project_id 不匹配');
const fileSha = target => `sha256:${crypto.createHash('sha256').update(fs.readFileSync(target)).digest('hex')}`;
const parts = [];
const refsUsed = [];
for (const ref of (asset.reference_inputs || [])) {
  const entry = registry.assets?.[ref.asset_id];
  if (!entry || entry.status !== 'approved') {
    if (ref.required) throw new Error(`${asset.asset_id} 缺少已通过参考图：${ref.asset_id}`);
    continue;
  }
  const referencePath = path.resolve(String(entry.path || ''));
  if (!referencePath.startsWith(`${projectDir}${path.sep}`) || !fs.isFileSync(referencePath)) {
    if (ref.required) throw new Error(`${asset.asset_id} 参考图路径非法或不存在：${ref.asset_id}`);
    continue;
  }
  const actualSize = fs.statSync(referencePath).size;
  const actualSha = fileSha(referencePath);
  if (entry.file_size !== actualSize || entry.sha256 !== actualSha) throw new Error(`${asset.asset_id} 参考图完整性失败：${ref.asset_id}`);
  const mime = entry.mime_type || (/\.jpe?g$/i.test(referencePath) ? 'image/jpeg' : 'image/png');
  parts.push({ text: `[REFERENCE ${refsUsed.length + 1}] asset_id=${ref.asset_id}; role=${ref.role}. 只按该职责使用，不复制其摄影机角度。` });
  parts.push({ inline_data: { mime_type: mime, data: fs.readFileSync(referencePath).toString('base64') } });
  refsUsed.push({ asset_id: ref.asset_id, role: ref.role, path: referencePath, sha256: actualSha });
}
let prompt = String(asset.prompt_zh || asset.prompt_en || '').trim();
if (asset.negative_prompt) prompt += `\n\n【补充负面约束】\n${asset.negative_prompt}`;
if (asset.qa_feedback) prompt += `\n\n【上轮质检修复要求】\n${asset.qa_feedback}`;
parts.push({ text: prompt });
const requestBody = {
  contents: [{ role: 'user', parts }],
  generationConfig: { responseModalities: ['TEXT', 'IMAGE'], responseFormat: { image: { aspectRatio: asset.aspect_ratio, imageSize: asset.image_size } } },
};
return [{ json: { ...asset, project_dir: projectDir, job_dir: jobDir, registry_path: registryPath, output_path: outputPath, refs_used: refsUsed, requestBody } }];
