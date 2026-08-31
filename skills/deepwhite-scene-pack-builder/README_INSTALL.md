# 安装说明

技能目录名：

`deepwhite-scene-pack-builder`

推荐安装位置（二选一）：

1. OpenClaw 的全局技能目录：
   `${OPENCLAW_STATE_DIR:-$HOME/.openclaw}/skills/deepwhite-scene-pack-builder`

2. 当前 Agent Workspace 的技能目录（优先级更高）：
   `<agent-workspace>/skills/deepwhite-scene-pack-builder`

## 安装

1. 优先使用 Novel-to-Drama Pipeline 的一键安装器；它会自动安装本技能。
2. 手动安装时，解压 ZIP，并把整个 `deepwhite-scene-pack-builder` 文件夹放到上述任一 skills 目录。
3. 执行：

```bash
openclaw skills list
```

4. 如果当前会话没刷新：

```text
/new
```

或：

```bash
openclaw gateway restart
```

## 显式调用示例

```text
/skill deepwhite-scene-pack-builder 仙侠风庭院，3D半写实，16:9
```

自然语言也可以：

```text
帮我做一套中国古代破落宅院的连续场景资产提示词，16:9，有牛车从院子驶出去。
```

由于 `disable-model-invocation: false`，当模型识别到“连续场景资产、多机位、场景DNA、场景连续性”等需求时，也可以自动选择该技能。
