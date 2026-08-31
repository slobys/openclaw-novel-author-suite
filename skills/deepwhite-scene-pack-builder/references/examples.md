# Invocation Examples

## New scene, minimal

```text
$deepwhite-scene-pack-builder 做一套仙侠风庭院，3D半写实，16:9。
```

Expected: compact summary, queue and L01 only.

## New scene with motion

```text
$deepwhite-scene-pack-builder 中国古代破落宅院，国风写实，16:9。牛车从院内出门，沿土路经过古树后远去。
```

Expected: include SUB01, R01 and continuous shots.

## Full export

```text
$deepwhite-scene-pack-builder 中国现代农村住宅，电影写实，16:9，完整包全部输出。
```

## Continue

```text
继续 SC-xianxia-courtyard-01
```

## Audit

```text
检查这张 V03 是否和前面的宅院一致。
```

## Repair

```text
V04 的路拐反了，其他都不要改，重做当前图。
```

## Restyle only

```text
空间和机位全部不动，改成国风厚涂半写实2D。
```

## Single view

```text
只输出 V05。机位靠近古树，低机位，看向来路。
```


## 跨模型复制（默认）

> 新建：仙侠庭院，3D半写实，16:9。跨模型复制模式，逐张输出。

每一张最终代码块必须完整出现：

- STYLE LOCK
- SCENE DNA
- SPATIAL LOCK
- CONTINUITY LOCK

即使写了“应上传 M01 / V02”，也不能省略四锁。

## 纠正省略四锁的输出

> 重新编译当前资产，启用 PORTABLE_HARD_LOCK。代码块首行必须为【PORTABLE HARD LOCK｜独立可用｜禁止删减】，并逐字内嵌 STYLE LOCK、SCENE DNA、SPATIAL LOCK、CONTINUITY LOCK；禁止用“参考 AST-01”“沿用上一张”代替。未通过硬锁校验时只返回 HARD_LOCK_VALIDATION_FAILED。

## 2.3 Portable Hard Lock 强制测试

```text
/skill deepwhite-scene-pack-builder
新建：仙侠庭院，3D半写实，16:9。逐张输出。
所有AST最终Prompt使用PORTABLE HARD LOCK；不要输出英文版。
```

AST-01、AST-02、AST-03及所有后续 Prompt 的代码块必须从以下内容开始：

```text
【PORTABLE HARD LOCK｜独立可用｜禁止删减】
LOCK_ID: ...

【STYLE LOCK｜固定原文】
...

【SCENE DNA｜固定原文】
...

【SPATIAL LOCK｜固定原文】
...

【CONTINUITY LOCK｜固定原文】
...
```

若输出仍只有“参考上一张”，立即使用：

```text
硬锁自检。当前输出不合格。重新编译当前AST；首行必须为【PORTABLE HARD LOCK｜独立可用｜禁止删减】，并逐字内嵌四锁。未通过校验时只返回 HARD_LOCK_VALIDATION_FAILED，不得输出缩水Prompt。
```


## 2.5 单层多房间测试

```text
/skill deepwhite-scene-pack-builder

新建一套现代中国高端别墅一层室内连续场景资产。
风格：高质量3D半写实现代室内电影感
比例：16:9
空间：玄关、客厅、餐厅、走廊相互连通
路线：人物从玄关进入客厅，再穿过开放门洞进入餐厅
模式：逐张输出
所有最终提示词采用PORTABLE HARD LOCK，只输出中文Prompt。
```

预期优先队列：`F01 → C01 → E01... → M01... → P01... → TR01A/B/C`。

## 2.5 跨楼层测试

```text
/skill deepwhite-scene-pack-builder

新建一套现代中国高端别墅室内连续场景资产。
风格：高质量3D半写实现代室内电影感
比例：16:9
空间：一楼客厅、一楼走廊、折返楼梯、二楼平台、二楼主卧
路线：人物从客厅经过走廊上楼，再进入主卧
模式：逐张输出
所有最终提示词采用PORTABLE HARD LOCK，只输出中文Prompt。
```

预期优先队列：`F01 → F02 → C01 → S01 → E01... → Mxx/Pxx → 楼梯TR序列`。

## 自定义室内机位

```text
继续当前场景。不要进入默认队列，新增CV01：摄影机位于餐厅PT01门洞西侧1米、人眼高度，回看客厅，35毫米；先做机位合法性与参考覆盖检查，再输出完整硬锁Prompt。
```
