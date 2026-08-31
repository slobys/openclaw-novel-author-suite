#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const workflowPath = path.join(here, 'OpenClaw连续资产依赖生图_参考图注入版_v2.json');
const mapping = {
  '校验任务并拓扑排序': '校验任务并拓扑排序.js',
  '解析依赖并构建Gemini请求': '准备Gemini请求_参考图注入.js',
  '保存通过图片并更新Registry': '保存通过图片并更新reference_registry.js',
  '保存最终拒绝结果': '保存最终拒绝结果.js',
  '记录空图片失败': '记录空图片失败.js',
  '汇总任务结果': '汇总任务结果.js',
};
const workflow = JSON.parse(fs.readFileSync(workflowPath, 'utf8'));
for (const [nodeName, snippetName] of Object.entries(mapping)) {
  const node = workflow.nodes.find(item => item.name === nodeName);
  if (!node) throw new Error(`Workflow node not found: ${nodeName}`);
  node.parameters.jsCode = fs.readFileSync(path.join(here, 'snippets', snippetName), 'utf8').trim();
}
const responseNode = workflow.nodes.find(item => item.name === '返回结果');
if (!responseNode) throw new Error('Workflow node not found: 返回结果');
responseNode.parameters.options = { responseCode: '={{ $json.ok ? 200 : 422 }}' };
workflow.name = 'OpenClaw连续资产依赖生图_参考图注入版_v2.1';
fs.writeFileSync(workflowPath, `${JSON.stringify(workflow, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({ updated: workflowPath, nodes: Object.keys(mapping), response_code_is_dynamic: true }, null, 2));
