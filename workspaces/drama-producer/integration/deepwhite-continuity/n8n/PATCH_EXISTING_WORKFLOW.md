# 给现有 n8n 生图流程增加真实参考图注入

推荐直接导入同目录下的：

```text
OpenClaw连续资产依赖生图_参考图注入版_v2.json
```

如果希望保留现有“失败图单独保存版”的全部质检分支，至少完成以下修改：

1. Webhook 接收的每个 `assets[]` 对象保留 `depends_on` 与 `reference_inputs`；
2. “展开并校验资产”改为拓扑排序，而不是只按数组顺序；
3. 用 `snippets/准备Gemini请求_参考图注入.js` 替换“准备 Gemini 请求”；
4. 生成通过后运行 `snippets/保存通过图片并更新reference_registry.js`；
5. 项目级 registry 固定写到：

```text
/data/openclaw-assets/{project_id}/reference_registry.json
```

6. 必需参考图找不到或不是 `approved` 时，必须阻塞当前资产，不得退化为纯文本生成；
7. n8n 容器必须能读取项目图片目录；
8. Code 节点使用 `fs/path` 时，按自托管安全设置允许内置模块。

参考图注入请求的核心结构：

```json
{
  "contents": [{
    "parts": [
      {"text": "参考图1只负责空间拓扑"},
      {"inline_data": {"mime_type": "image/png", "data": "BASE64"}},
      {"text": "完整PORTABLE HARD LOCK Prompt"}
    ]
  }]
}
```


输出画幅使用 `generationConfig.responseFormat.image.aspectRatio/imageSize`。
