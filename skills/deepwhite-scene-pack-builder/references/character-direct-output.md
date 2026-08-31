# 人物指定直出模式

## 目标

人物建立后直接输入：

- 输出正面
- 输出左侧面
- 输出背面
- 输出头部特写
- 输出正面惊讶表情头部特写

系统解析为单张 `CPxx` 资产。

## 解析字段

```yaml
view_angle:
framing:
focus_part:
expression:
pose:
held_prop:
gaze_direction:
background:
aspect_ratio: 9:16
```

## 标准角度

- FRONT
- LEFT_PROFILE
- RIGHT_PROFILE
- BACK
- LEFT_FRONT_45
- RIGHT_FRONT_45
- LEFT_BACK_45
- RIGHT_BACK_45

## 标准景别

- FULL_BODY
- THREE_QUARTER_BODY
- KNEE_UP
- WAIST_UP
- BUST
- HEAD_SHOULDERS
- HEAD_CLOSEUP
- FACE_CLOSEUP

## 默认补全

- 正面 → FRONT + FULL_BODY + NEUTRAL_STANDING
- 侧面 → LEFT_PROFILE + FULL_BODY
- 背面 → BACK + FULL_BODY
- 头部特写 → FRONT + HEAD_SHOULDERS
- 惊讶表情 → FRONT + HEAD_SHOULDERS + SURPRISED

## 连续性重点

- 五官间距、鼻口、耳朵、发际线与发型不变
- 头身比、肩宽、腹部、腿长和手掌尺寸不变
- 服装层级、扣子、口袋、鞋帽与随身装饰不变
- 表情变化不能造成换脸
- 侧面与背面不能重新设计发型、帽子和服装背部
