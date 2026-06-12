# 鲁班「先体验导学」Onboarding Motion 升级设计

> Status: Approved design / pending implementation plan
> Date: 2026-06-12
> Parent authority:
> [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)（产品契约）
> / [2026-06-11-luban-mobile-ui-ux-design-system-and-screen-spec.md](2026-06-11-luban-mobile-ui-ux-design-system-and-screen-spec.md)（设计系统）
> 视觉语言源头: `artifacts/remotion-luban-motion/design-prompt.md`（AI 实务诊断仪概念）

## 0. 背景与现状

用户希望「先体验导学」页达到参考视频级的高级 motion 质感。参考素材为两支
Pinterest 动效视频（已逐帧分析）：

1. **Kinetic typography + 产品演示**（16:9, ~31s）：浅色全息渐变光斑底，
   大字号文案逐词浮现、关键词原位高亮替换，产品界面以 3D 透视倾斜飞入，
   文字幕与产品幕交替推进，结尾 CTA。
2. **手机样机色浪转场**（1:1, ~25s）：固定 iPhone 样机内屏幕连续过渡，
   全屏渐变色浪冲刷转场，渐进式清单逐项打勾，绿勾收束。

代码现状（branch `codex/wechat-entitlement-paywall-trial`）：

- `yousenwebview/packageDeeptutor/pages/onboarding/` 已存在三幕翻页式导学页：
  文案三幕（诊断 / 判分 / 错因闭环）+ 产品样机（chat 气泡、判分卡
  命中/漏/改 rows、weak-bar、task-box）+ 示例问题 + CTA。
  已有入场动画（titleIn/copyIn/productLand/rowIn/barGrow），但本质是
  手动「下一步」翻页，无自动叙事、无 kinetic typography、无转场。
- 登录页 guest-entry「先体验导学」入口已存在（本分支未提交的 paywall
  并行工作，`handleGuestPreview` → `wx.reLaunch(route.onboarding(...))`）。
- `artifacts/remotion-luban-motion/` 是同需求的 Remotion 视频原型，
  其 design-prompt.md 已定调视觉方向：深蓝 / 石墨灰 / 青绿 / 少量琥珀，
  专业、克制、高端诊断仪感；拒绝游戏化与廉价题库感。

**结论：本任务是把现有 onboarding 页从「带入场动画的翻页 PPT」升级为
「自动播放的电影化 motion 叙事」，不新建页面，沿用现有三幕文案权威。**

## 1. 目标体验：六幕自动播放时间轴（总长约 30s）

| 幕 | 内容 | 动效语言 |
|---|---|---|
| 0 转场入场 | 从登录页点击「先体验导学」进入 | 登录页色浪冲刷出场（~400ms）→ onboarding 色浪退潮入场（~600ms），视频 2 风格 |
| 1 文字 Hook | 「题刷了很多，分数却不涨？」 | kinetic typography：逐词 stagger 浮现，「分数却不涨」关键词原位高亮变色，视频 1 风格 |
| 2 诊断对话 | 现有幕一：chat 样机 | 学员气泡滑入 → AI 气泡打字机逐字吐出 → bullets 逐条点亮 |
| 3 判分揭晓（高潮） | 现有幕二：判分卡 | answer-paper 逐句扫描标记（命中绿 / 漏写红）→ point-row 逐条点亮 + 「+6 / -5」飘分上浮 → score-pill 12/20 数字滚动 |
| 4 错因沉淀 | 现有幕三：训练闭环 | weak-bar 依次生长 → task-box 弹入 → 「错因画像 / 同类再练」标签吸附浮动（Remotion 原型的证据节点语言） |
| 5 CTA 收束 | 「让每一分都有据可依」+ 行动区 | 文字聚合收束 → 「开始体验」主按钮 + 「快速登录」次链接 + 示例问题列表浮入（tryExample 保留） |

交互规则：

- 默认自动播放推进；任何手动操作（上滑 / 点进度点 / 点「下一步」）立即
  接管并暂停自动推进，保留现有手动导航完整可用。
- 「跳过」直达幕 5 CTA（不是直接 reLaunch 离开，让 CTA 承接转化）。
- 示例问题、startExperience、quickLogin、entry_source 链路行为不变。
- `onHide`/`onUnload` 暂停并清理所有定时器。

## 2. 动效规范

- **easing 统一**：`cubic-bezier(0.16, 1, 0.3, 1)`（页面已有，延续）。
- **文字逐词浮现**：`opacity + translateY(14rpx)` stagger（80–120ms/词）；
  不用 `filter: blur`（小程序渲染性能差），用透明度+位移替代。
- **关键词高亮**：原位颜色过渡 蓝 → 青绿（得分语义）/ 琥珀（警示语义），
  配合 `scale(1.04)` 微弹。
- **样机入场**：`perspective + rotateX(4deg)` 微透视落地（视频 1 产品幕）。
- **飘分**：`+6` 上浮 24rpx + 淡出，绿色；`-5` 同理琥珀色。
- **数字滚动**：score-pill 用 JS 步进 setData（≤8 步），不逐帧。
- **色浪转场**：全屏渐变 overlay 层 `translateY` 冲刷；登录页出场色浪用
  金→蓝渐变（呼应 guest-entry 按钮配色），onboarding 入场退潮露出页面。
- **性能红线**：所有补间只用 `transform` / `opacity`；每幕 setData 次数
  ≤ 该幕步数；演示全程零网络请求。

## 3. 技术架构

```
pages/onboarding/
  onboarding.js      — Page 壳：接线 timeline ↔ setData，手动交互接管
  onboarding.wxml    — 在现有结构上加 step 门控 class（act-N / step-ready 等）
  onboarding.wxss    — 新增 keyframes 与 step 状态样式
  motion-script.js   — 数据文件：六幕 × 步序列 [{at_ms, patch}]，文案沿用 SLIDES
utils/motion-timeline.js — 纯函数时间轴调度器（可单测）：
  createTimeline(script, {onStep, onSceneEnd}) → {start, pause, resume, jumpTo, destroy}
```

- 调度器内部用 `setTimeout` 链推进，状态不可变（每步返回新 state），
  与 wx API 解耦——Node 可直接单测。
- WXML 不重构：现有 product-stage 结构保留，动效通过追加的状态 class
  控制各元素的 animation-play-state / 延迟出现。
- 登录页改动手术刀级：guest-entry tap → 加色浪 overlay + ~400ms 后
  `reLaunch`（现有 `handleGuestPreview` 内加一层，不碰登录主流程）。

## 4. 范围边界（Surgical Changes）

- **只改**：onboarding 四件（js/wxml/wxss/motion-script）、
  `utils/motion-timeline.js`（新增）、login 三件（仅色浪转场层）、
  新增 1 个测试文件。
- **不碰**：登录鉴权主流程、billing/chat/history/profile/report 等
  并行未提交工作（959 行）、app.json、路由、后端、`/api/v1/ws`。
- **提交纪律**：narrow staging，逐文件 `git add`，严禁 `git add -A`
  （本 worktree 存在并行未提交工作）。
- 文案权威：现有 `SLIDES` 三幕文案不重写，只新增幕 1 Hook 与幕 5 收束语。

## 5. 验收标准

1. 微信开发者工具 CLI 打开 `yousenwebview` 项目根 → 进入
   `packageDeeptutor/pages/onboarding/onboarding`（AGENTS 真实入口纪律），
   录屏确认六幕自动播放完整、转场色浪生效。
2. 手动交互回归：上滑/进度点/下一步接管自动播放；跳过直达 CTA；
   示例问题→chat、开始体验、快速登录链路与改动前一致。
3. 真机预览主观流畅（无可感知掉帧/白屏）。
4. `node yousenwebview/tests/test_onboarding_motion_timeline.js` 通过
   （步进顺序、jumpTo、pause/resume、destroy 清理、手动接管）。
5. 演示全程抓包零网络请求。

## 6. 风险与回退

- 自动播放与手动翻页状态打架 → 规则收敛为「手动一票接管」，单测覆盖。
- 低端机动画卡顿 → 所有补间 GPU 合成属性；如仍卡，提供
  `motionReduced` 降级开关（一次性展示终态，结构保留）。
- 与并行 paywall 工作在 login 文件冲突 → 改动叠加在其未提交 diff 之上，
  提交前与用户确认该并行工作的归属与提交顺序。
