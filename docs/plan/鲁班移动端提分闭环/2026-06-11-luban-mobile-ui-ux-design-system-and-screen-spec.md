# 鲁班移动端 P0A UI/UX 设计系统与核心屏幕规格

> Status: Proposed / Design spec for P0A
> Date: 2026-06-11
> Parent authority: [2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md](2026-06-11-luban-mobile-scoring-loop-ui-ux-product-plan.md)

## 0. Purpose

本文定义 P0A 进入前端实现前必须具备的核心屏幕、组件、状态和视觉验收标准。它不替代最终视觉稿，但定义设计不可违背的产品结构。

## 1. Design Direction

关键词：

- 专业。
- 克制。
- 可信。
- 高效。
- 诊断感。
- 冲刺感。
- 少娱乐化。
- 少炫技。

禁止方向：

- 聊天框首页。
- 功能宫格首页。
- 营销 hero 首页。
- 游戏闯关式学习首页。
- 抽象科技风、无意义渐变、装饰性大卡片。
- 只展示标准答案，不展示用户自己的采分点证据。

## 2. Core Screens

P0A 必须有以下屏幕规格或高保真 mock。

P0A navigation rule: 不替换现有 4 TabBar。今日任务可以作为现有入口内的「今日焦点」、独立入口页或 feature-flagged 页面承载；5 Tab 信息架构只作为 P0B 目标。任何设计稿如果要求 P0A 同时替换全站底部导航，默认退回修改。

### 2.1 今日页

First screen must answer:

1. 距离考试还有多久。
2. 今天最该做什么。
3. 为什么推荐。
4. 预计多久。
5. 做完补哪类分。

Layout:

```text
顶部状态条
今日主任务卡
快速操作
薄弱点 / 最近批改摘要
微复习
底部导航
```

Rules:

- One primary CTA only.
- 推荐原因必须来自 read model / evidence / cold-start diagnosis。
- 断更状态不展示惩罚性补债文案。
- P0A 今日页不要求进入正式 TabBar；但入口文案、返回路径和已有 4 Tab 的关系必须明确。

### 2.2 轻练页

Purpose:

不用长文本输入，也能练审题、采分点识别、流程和主体。

Required components:

- Progress indicator.
- Question prompt.
- Interaction block: single select / multi select / case small-question.
- Immediate feedback.
- Next step CTA.

States:

- loading.
- answer selected.
- partial correct.
- wrong with explanation.
- complete.

P0A explicitly defers sort / match / fill interactions to P0B unless product owner reopens scope with added engineering and QA budget.

### 2.3 半写页

Purpose:

训练得分语言和答题结构。

Required components:

- Task context.
- Visible scope hint: 本次只训练的采分点范围。
- Sentence blocks or short answer input.
- Scoring hint, without exposing answer key.
- Draft preservation.
- Submit CTA.

Rules:

- Do not require long mobile typing.
- Do not leak full scoring rubric before submit.
- Do not imply full-question scoring when task scope covers only part of the rubric.
- Result copy must distinguish `not_evaluated` from `miss`.
- Draft survives network failure.

### 2.4 AI 批改结果页

Order:

```text
score range / confidence / high-risk
top 3 issues
scoring point list
evidence blocks
rewrite suggestions
standard answer folded
second attempt / similar question CTA
feedback
```

Rules:

- Standard answer folded by default.
- Evidence must connect student text to scoring_point.
- High-risk state must be visible.
- Bottom CTA must keep correction loop alive.

### 2.5 OCR 确认页

Purpose:

OCR is input confirmation, not truth.

Required components:

- Image preview.
- OCR text.
- Suspicion spans.
- Confirmed text editor.
- Retake / confirm CTA.

Rules:

- Low-confidence spans are highlighted.
- User can correct text.
- Confirmed text is the only grading input.
- Abandoning confirmation stops grading.

### 2.6 错因复练入口

Purpose:

错题本不是收藏夹，而是错误模式复盘中心。

Required components:

- mistake_tag.
- linked scoring_point.
- linked case_family.
- repeated count.
- next review time.
- recommended action.

Rules:

- A mistake cannot be closed only by user tapping "已掌握".
- Similar question and retest must be visible.

### 2.7 我的页数据与隐私入口

Required items:

- 清除上传图片。
- 导出学习记录。
- OCR / 批改使用记录。
- 反馈批改问题。
- 考试日期。
- 每日可用时间。
- 学习偏好。

## 3. Component Contract

P0A components:

- `TaskCard`
- `RiskBadge`
- `ConfidenceBadge`
- `CaseFamilyCard`
- `ScoringPointRow`
- `MistakeTagChip`
- `EvidenceBlock`
- `RewriteSuggestionCard`
- `ModeSelector`
- `PhotoQualityWarning`
- `OcrSuspicionSpan`
- `StickyBottomCTA`
- `EmptyState`
- `LoadingSkeleton`
- `HighRiskBanner`

State vocabulary:

| State | Meaning |
| --- | --- |
| `hit` | 表述到位 |
| `partial` | 方向对，但缺关键词、主体、依据或措施 |
| `miss` | 未写到采分点 |
| `not_evaluated` | 本次任务不覆盖，不计入错因或扣分证据 |
| `uncertain` | OCR 或语义不确定 |
| `needs_review` | 高风险，建议复核 |

Same state must use same color, icon, and wording across screens.

## 4. Responsive And Accessibility

Required viewports:

- 375px width.
- 390px width.
- 430px width.
- large text mode.

Rules:

- Touch target at least 44px.
- Bottom CTA avoids safe area.
- Evidence text no smaller than 14px.
- Long words and IDs cannot overflow.
- High-risk warnings cannot rely on color alone.
- Loading and error states must be readable without animation.

## 5. Design Review Scorecard

Each screen must score at least 8/10 before implementation.

| Dimension | 10/10 means |
| --- | --- |
| Information architecture | User knows the next action in 5 seconds |
| State coverage | loading / empty / error / partial / success / high-risk covered |
| Journey continuity | Every result leads to second attempt, similar question, or review |
| Trust | Confidence, high-risk, and uncertainty are visible |
| Scope clarity | Light/semi-write screens make covered vs not-evaluated points unambiguous |
| Component consistency | Same state means same thing everywhere |
| Mobile ergonomics | No long typing default, no overflow, safe tap targets |
| Anti-slop | Looks like a serious diagnostic tool, not generic AI UI |

## 6. Required Design Artifacts

Before P0A frontend implementation:

- One visual board for the 7 core screens.
- Component inventory with state examples.
- Empty/error/high-risk states.
- Mobile viewport screenshots.
- Copy deck for high-risk, OCR uncertainty, and task recommendation reasons.

## 7. Post-Implementation Design QA

After implementation, run visual QA against:

- Screenshot match to approved visual board.
- Text fit in all required widths.
- No overlapping UI.
- Correct state colors and labels.
- Sticky CTA not blocking content.
- Evidence blocks readable.
- Standard answer folded by default.
