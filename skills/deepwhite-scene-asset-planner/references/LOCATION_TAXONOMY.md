# 地点、子场景与状态版拆分准则

## 目标

用最少但足够的场景资产表达剧情真实空间变化，避免两种极端：

- 整集只用一张万能背景；
- 每个镜头都生成一张几乎相同的新背景。

---

## 1. 什么算新的 Location

创建新 Location 的典型情况：

- 人物从家到集市；
- 从村庄到县城；
- 从现实到梦境/异空间；
- 从客栈到县衙；
- 从地面进入地下遗迹。

不要创建新 Location：

- 同一房间由门边走到桌边；
- 同一街道由左侧机位换右侧机位；
- 同一院子从中景切特写。

---

## 2. 什么算新的 Sub-location

### 必拆

- 卧室 ↔ 堂屋；
- 室内 ↔ 庭院；
- 一楼大厅 ↔ 二楼包间；
- 集市入口 ↔ 盐摊；
- 县衙大门 ↔ 公堂；
- 森林入口 ↔ 溪边 ↔ 山洞。

### 可拆

当剧情在一个大地点停留较久，可以把真实存在且剧情允许进入的区域作为视觉变化：

- 堂屋 → 窗边区域；
- 酒楼大厅 → 柜台区域；
- 集市主街 → 摊位区；
- 院子 → 井边；
- 书房 → 书架侧。

可拆不代表必须生成。先看时长、重复度、后续复用价值和成本。

### 不拆

- 仅景别变化；
- 人物站姿/坐姿变化；
- 仅镜头朝向改变；
- 仅普通照明强弱变化；
- 仅一个小道具加入画面。

---

## 3. 什么算新的 Variant

必须满足“同空间身份 + 状态变化视觉显著”。

### 常见状态

`time_of_day`

```text
dawn / day / dusk / night / interior_lit
```

`weather`

```text
clear / cloudy / rain / storm / snow / fog
```

`environment_state`

```text
normal / abandoned / after_fight / after_fire / flooded / festival / damaged
```

`occupancy_state`

```text
neutral / empty / busy / crowd / closed
```

### 不要过度生成

“晴天上午”和“晴天下午”如果照明差异不承担剧情功能，通常可以共用 `DAY`。

“有三个人”和“有四个人”不是场景 Variant；人物应由角色/关键帧层解决。

---

## 4. 跨集复用

Location 和 Sub-location 是系列级身份，不是单集临时名称。

例如第一集已经有：

```text
LOC-LIN-HOME
SUBLOC-LIN-HOME-COURTYARD
AST-LOC-LIN-HOME-COURTYARD-DAY
```

第三集再次回到同一时间/状态的院子，应复用同一资产，而不是创建：

```text
AST-LOC-LIN-HOME-COURTYARD-DAY-V2
```

除非旧资产正式被新版本取代并通过系列资产注册流程。

---

## 5. 环境身份指纹

场景 identity_fingerprint 应来自稳定视觉事实：

```text
空间布局
建筑时代/风格
固定地标
主要材质
主色关系
固定出入口关系
```

不要把以下内容放进基础身份指纹：

```text
某角色站在哪里
当天具体表情
临时手持道具
偶然路人数量
单镜头机位
```

这样才能让同一空间跨镜头、跨集稳定复用。
