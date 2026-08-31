# Prompt Protocol Reference

本文件供 `deepwhite-scene-pack-builder` 在需要详细结构时参考。

## 1. 最终单图 Prompt 模板

```text
【STYLE LOCK】
整体视觉风格：
{style}

表现媒介：
{medium}

写实程度：
{realism}

材质逻辑：
{materials}

色彩与光影：
{color_lighting}

世界观限制：
{world_constraints}

【ASPECT RATIO LOCK】
画面比例：{aspect_ratio}
构图：{composition}
用途：连续场景资产 / AI短剧 / 视频分镜。

【SCENE DNA】
SCENE ID：{scene_id}
SCENE NAME：{scene_name}

这是同一个固定存在的真实物理场景。

整体空间结构：
{scene_structure}

固定地标：
{landmarks}

时间：{time}
季节：{season}
天气：{weather}
物理主光方向：{light_direction}
物理阴影方向：{shadow_direction}

【SPATIAL RELATION LOCK】
{spatial_relations}

【CONTINUITY LOCK】
必须保持：
{continuity_items}

这是同一个地点，不是相似地点。
只允许摄影机位置、摄影机方向、合理遮挡和移动主体位置变化。

【CURRENT TASK】
资产编号：{asset_id}
资产名称：{asset_name}
本图任务：{task}

【CAMERA SETUP】
摄影机位置：{camera_position}
摄影机朝向：{camera_direction}
摄影机高度：{camera_height}
景别：{shot_size}
焦段/透视要求：{lens}

【VISIBLE LANDMARKS】
必须出现：{must_visible}
建议出现：{optional_visible}
与上一视角共享：{shared_landmarks}

【REFERENCE INHERITANCE】
永久空间参考：Top-down Layout
永久视觉参考：Scene Master Shot
上一视角参考：{previous_view}
移动主体参考：{subject_reference}

如果模型支持多图参考，以上参考图优先用于保持同一物理地点。

【MOVING SUBJECT】
{moving_subject_or_none}

【NEGATIVE / RESTRICTIONS】
{negative}

The exact same physical environment.
Do not redesign the scene.
Do not relocate fixed landmarks.
Do not alter the road/path geometry.
Only camera and subject placement may change.
```

## 2. 资产队列默认设计

无移动主体：

01 Top-down Layout
02 Scene Master Shot
03 Key Asset A
04 Key Asset B
05 Key Asset C
06 Key Asset D
07 V01
08 V02
09 V03
10 V04
11 V05
12 V06

有移动主体：

再增加：
13 Moving Subject Reference
14 Movement Route
15-20 SHOT 01-06

## 3. 默认 Camera View 规划逻辑

不是机械套用，而应根据具体场景动态规划：

- V01：起点附近建立空间
- V02：第一个关键门槛/出入口
- V03：运动通道初段
- V04：中段回望或侧向证明来路
- V05：关键地标/转折处
- V06：终点或总结性高位远景

室内场景可以替换成：
- 房间入口
- 主空间
- 走廊
- 楼梯/转角
- 回望
- 高位/尽端

## 4. 风格与世界观

STYLE LOCK 是变量，不允许写死。

如果用户只说：
“仙侠风”
可以补成：
东方仙侠 + 用户指定媒介；若未指定媒介，默认高质量半写实环境设计。

如果用户只说：
“中国古代破落房子”
风格与空间可推断为：
中国古代民居 + 破败生活感；
但具体朝代不要无依据强行锁死。

如果用户只说：
“中国现代农村”
不要继承古代场景的禁止项。
现代村路、电线杆、太阳能热水器、现代农宅等是否出现，应根据用户剧情和视觉要求合理决定。

## 5. 连续性检查

后续用户提供生成图时，可以辅助检查：

### 一级错误（必须重做）
- 主建筑换位置
- 道路方向变了
- 主要出入口移动
- 场景镜像
- 固定地标消失/复制
- 室内房间拓扑改变

### 二级错误（建议重做）
- 关键建筑造型明显漂移
- 古树/桥/雕像外观变化过大
- 光源方向物理矛盾
- 远山轮廓大幅变化

### 三级误差（通常可接受）
- 草叶
- 小石块
- 云细节
- 微小杂物
- 非关键植被纹理
