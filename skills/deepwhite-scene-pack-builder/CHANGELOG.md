# Changelog

## 3.3.0
- 新增 PIPELINE_BATCH 模式
- 新增 BASE_ASSET 与 SHOT_ASSET_GAP 双阶段
- 新增逻辑父实体到单图子资产展开
- 新增 lock_hash、依赖图与 reference_plan 输出契约
- 新增 approved-only 参考图门禁
- 保留 v3.2.0 的角色锚点链及全部交互能力

## 3.2.0
- 新增角色锚点链模式 Character Anchor Chain
- 支持把当前上传人物图注册为 Anchor-A / Anchor-B / Anchor-C / Anchor-D
- 支持“以当前上传人物图为主参考，输出侧面 / 背面 / 头部特写”等派生命令
- 新增 REFERENCE COVERAGE：GREEN / YELLOW / RED 评级
- 新增“列出当前角色锚点”与缺图建议
- 保留3.1.0的人物指定直出、主体模式、场景模式和零配置默认

## 3.1.0
- 新增人物指定直出模式 Character Direct Output
- 支持按角度、景别、部位、表情、动作和道具组合输出
- 新增 CPxx 人物直出资产编号
- 新增“列出当前人物可调用视图”
- 新增人物参考覆盖 GREEN / YELLOW / RED 检查
- 人物直出继续默认9:16并强制PORTABLE HARD LOCK
- 保留3.0.0的场景、动物、生物、道具与零配置功能

## 3.0.0
- 新增人物模式 Character Mode
- 新增动物模式 Animal Mode
- 新增生物模式 Creature Mode
- 新增道具模式 Prop Mode
- 默认比例逻辑升级：场景16:9；人物/动物/生物/道具9:16
- 新增人物专用资产队列 C01-C07
- 新增动物专用资产队列 A01-A05
- 新增生物专用资产队列 CR01-CR05
- 新增道具专用资产队列 P01-P04
- 保留零配置、PORTABLE HARD LOCK、逐张输出、位置直出、资产队列与版本管理