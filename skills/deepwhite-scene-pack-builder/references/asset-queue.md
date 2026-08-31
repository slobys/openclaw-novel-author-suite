# 资产队列与进度规则

## 1. 队列状态不可混淆

Prompt 已输出、图片已生成、图片已审核是三件不同的事。

建议数据：

```json
{
  "prompt_status": "GENERATED",
  "image_status": "NOT_GENERATED",
  "review_status": "UNREVIEWED"
}
```

## 2. 用户语句映射

- “提示词做好了” → prompt_status=GENERATED
- “图片生成了” → image_status=GENERATED
- “这张通过” → review_status=APPROVED
- “这张失败，道路反了” → review_status=FAILED，并记录 failure_reason
- “这张不用了” → review_status=SKIPPED

不要根据上下文擅自宣布通过。

## 3. 队列表格建议

| # | 代码 | 标题 | 区域 | 依赖 | Prompt | 图片 | 审核 | 当前 |
|---|---|---|---|---|---|---|---|---|

可附摘要：
- 总数
- 已通过
- 待生成Prompt
- 图片未生成
- 待审核
- 失败
- 阻塞

## 4. 筛选命令

- 只看待生成：prompt_status=NOT_STARTED
- 只看失败：review_status=FAILED
- 只看待审核：image_status=GENERATED 且 review_status=UNREVIEWED
- 只看已通过：review_status=APPROVED
- 查看当前：current=true

## 5. 队列指针

`current_asset_series_id` 保存资产系列ID，不含版本号，例如：

`SC001-ST01-V04`

临时“输出V04”不必修改指针。
“跳转到V04并从这里继续”才修改指针。
