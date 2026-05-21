# DeepTutor Web Harness Deep QA — 2026-05-21

- **Target**: `http://127.0.0.1:3000/wechat-harness` (Next.js 16.2.6 / dev / Turbopack)
- **Mode**: report-only (`/gstack-qa-only`) — no code fixes
- **Branch**: `main` @ `9b08a781`
- **Tester**: Claude Code (gstack-qa-only)
- **Viewports tested**: 1440×900 桌面、375×812 移动
- **Screenshots**: `.gstack/qa-reports/screenshots/2026-05-21-web-harness/`

## Health Score: **68 / 100**

按 gstack-qa 加权 rubric：Console 70 · Links 100 · Visual 25 · Functional 60 · UX 65 · Performance 80 · Content 92 · Accessibility 70。

Visual / Functional 双重失血来自移动端整块不可滚动（P0）与 fixture-filter detail 不同步（P1，是 P3-1 e16 回归未修复）。Console 失血来自 `/api/v1/learning-brain/harness-case-grading` 500。

---

## Top 3 必须修

1. **P0 移动端无法滚动到 chat preview / 右侧验收断言 / 学情闭环**（影响所有 case，所有 fixture）。
2. **P1 `/api/v1/learning-brain/harness-case-grading` 500，UI 仅显示英文裸文本 "Learning Brain QA failed"**。学情闭环 = 验收闭环的核心动作。
3. **P1 fixture-filter 点击后 detail panel 不切换**——P3-1 e16 回归未修复。filter 收窄列表后 detail 仍渲染已被隐藏的 case，假"通过"状态保留。

---

## 摘要表

| 编号 | 优先级 | 标题 | 覆盖入口 |
|---|---|---|---|
| H-001 | P0 | 移动 375×812 body/html overflow:hidden + main 3120px 不可滚动 | Web harness ✅ |
| H-002 | P1 | `/api/v1/learning-brain/harness-case-grading` 500，错误文案裸英文 | Web harness ✅（API 真实 endpoint） |
| H-003 | P1 | fixture-filter 切换不更新 detail panel（P3-1 e16 回归） | Web harness ✅ |
| H-004 | P2 | "当前结论 公共主链通过 / 实时最终态与历史恢复态一致" 永远显示 | Web harness ✅ |
| H-005 | P2 | 头部 "结构化 16 / 选择题 1 / 置信度 95%+" 在非结构化 case 也显示 | Web harness ✅ |
| H-006 | P2 | MCQ 提交允许空答案，"已记录选择：空" 无校验 | Web harness ✅ |
| H-007 | P2 | Exam Semantic Callouts 直接展示 "采分点 / 拿分要点 / 易错点提醒" 等评分细则 | **必须微信入口复测** |
| H-008 | P2 | 移动端横滚 case row 卡片严重截断（仅 "C / 教" 可见） | Web harness ✅ |
| H-009 | P3 | 当前 render model JSON 直接暴露给浏览者 | Web harness ✅ |
| H-010 | P3 | streaming Chunk 1 与 Chunk mid 渲染完全相同（fixture 切片不区分） | **必须微信入口复测真实 SSE** |
| H-011 | P3 | dev HMR WebSocket 失败噪音（生产无影响） | Web harness ✅ |

---

## 详细 Issue

### H-001 — P0 — 移动 375×812 整块右侧内容不可达
**Surface**: `/wechat-harness` viewport 375×812 (`p2-mobile-initial.png`, `p2-mobile-fresh-viewport.png`)

**Repro**:
1. viewport 375×812 → `goto /wechat-harness`
2. 等 React 水合完成
3. 滚动尝试：`window.scrollTo` / 触摸滚动均无效

**实测 CSS / DOM**:
```js
{
  bodyOverflow: "hidden",
  htmlOverflow: "hidden",
  mainOverflowY: "auto",
  mainHeight: 3120.41,
  mainScrollHeight: 3120,
  mainHasOwnScrollbar: false  // scrollHeight == clientHeight
}
```

**影响**:
- 顶部 812px 可见：QA 头部、case 计数、parity 计数、搜索框、12 个 filter pill、2 张横滚 case 卡片、"CHAT" 标题、case 标题、case 摘要、"结构化 16" badge
- **812px 以下完全不可达**：chat 气泡（题目 1 / MCQ / table / 公式 / 流式 controls）、右侧 验收断言 / Final-History Parity / 人工关注点 / 学情闭环 QA / 当前 render model
- 主要风险面（渲染合同与学情闭环）在移动端等于消失

**Web vs 小程序**: 这是 Web harness 自身的布局 bug；小程序真实入口的 `scroll-view` 走原生滚动，不会有此问题；**不需要小程序复测**，但移动端 dogfood Web harness 完全失效。

---

### H-002 — P1 — 学情闭环 endpoint 500
**Surface**: 右侧 "学情闭环 QA" → 点击 "运行闭环" (`p6-learning-brain-run.png`)

**Repro**:
1. `goto /wechat-harness`（默认 case = Structured Table Formula Mcq Combo）
2. User ID 默认 `wechat_harness_learning_brain`，案例题作答默认 `应加强现场管理，落实责任，严格检查。`
3. 点 "运行闭环"

**结果**:
- `POST http://localhost:3000/api/v1/learning-brain/harness-case-grading → 500 (45ms, 21B)`
- Console: `[error] Failed to load resource: the server responded with a status of 500`
- UI 显示： **`Learning Brain QA failed`**（英文裸文本，紧贴 textbox 下方）

**问题**:
- 没有错误码、stack、retry button、降级 fallback
- 文案未做 i18n
- 500 21 字节 body 可能是简化的 `{"detail":"..."}` — 用户无法判断是 fixture 缺失、Backend 端点 disable、还是真实 5xx

**Web vs 小程序**: API endpoint 本身 Web 端可复现，**小程序入口仍需复测**，确认是不是仅 harness POST 路径未启用还是 backend 真坏。

---

### H-003 — P1 — fixture-filter 不刷新 detail panel（P3-1 e16 回归未修复）
**Surface**: 左侧 filter chips → e.g. "compactHeading" (`p8-fixture-e16-compactHeading.png`)

**Repro**（已在多个 fixture 验证）:
1. `goto /wechat-harness` → detail = "Structured Table Formula Mcq Combo"
2. 点击 filter chip：`structured` / `blankSeparatedOrdered` / `compactDashBullet` / `compactHeading` / `examCalloutLabels` / `全部`
3. 观察左栏 case row 数：`structured` (click failed due to selector ambiguity in browse tool), `blankSeparatedOrdered`=1, `compactDashBullet`=3, `compactHeading`=1, `examCalloutLabels`=1, `全部`=16 — filter 行为正确
4. 观察右侧 detail heading：**所有情形下 heading 仍为 "Structured Table Formula Mcq Combo"**（未匹配当前 filter）

**矛盾状态**:
- chip "compactHeading" 高亮 active
- 左栏只剩 1 行 "Compact Heading Markers From Live Chat"
- 右侧详情仍是被过滤掉的 "Structured Table Formula Mcq Combo"
- 右侧 render model JSON 仍是旧 case 的 blockTypes/visibleBlockTypes
- 右侧 "当前结论 公共主链通过" 依旧（参见 H-004）

**期望**: filter 收窄到不包含当前 case 时，要么 (a) 自动选中过滤结果首行，要么 (b) 显示空状态 "请选择匹配的 case"。当前两者都没有。

**Web vs 小程序**: filter UX 是 Web harness 专属设计，小程序无此 chrome；**不需要小程序复测**；Web 必须修以避免内部 dogfood 被误导。

补充验证：直接点击 case row（不经过 filter）→ 切换正常。`@e49` "Compact Heading Markers From Live Chat" 点击后 heading & render model 都更新。说明 **bug 仅在 fixture chip 路径**。

---

### H-004 — P2 — "公共主链通过 / 一致" 永远绿色
**Surface**: 右侧 "当前结论" + "Final / History Parity"，覆盖以下所有验证场景：
- mode = stream / Chunk 1（visibleBlockTypes=[]）
- mode = stream / Chunk mid（同上）
- mode = stream / Final payload
- mode = final
- mode = history
- case = billing quota exceeded（错误页）
- case = auth expired（错误页）
- 5xx 失败之后（H-002）

**问题**: 这两个标签不是观测态，是静态文案。
- "当前结论 公共主链通过" 始终绿色
- "Final / History Parity 实时最终态与历史恢复态一致" 始终显示一致，即使在 streaming 阶段视觉上空白也照旧
- 用户读这俩标签会以为有真实校验，但只是 fixture-author 的固定文案

**Web vs 小程序**: 标签本身只在 Web harness；**不需要小程序复测**。但这种"假满分"模式如果蔓延到 report.wxml 的真实展示，则风险翻倍 — 建议同时审计 `wx_miniprogram/pages/report/report.wxml` 是否有类似硬编码 "通过/达标" 文案。

---

### H-005 — P2 — 顶部 KPI 是仓库聚合，不是 per-case
**Surface**: detail header pill row：`结构化 16 / 选择题 1 / 置信度 95%+`

**问题**:
- 在 "Auth Expired Retry Surface" / "Billing Quota Exceeded Surface" 这种纯文本错误页 case 中，header 仍显示 "结构化 16 / 选择题 1 / 置信度 95%+"
- "结构化 16" 是整 fixture 集合数，不是该 case 的结构化块数（该 case `hasStructuredContent: false`）
- "选择题 1" 同理
- "置信度 95%+" 是 harness 目标，与 case 无关
- 视觉上紧贴 case 标题，会被读成 per-case 指标

**Web vs 小程序**: 仅 Web harness；**不需要小程序复测**。

---

### H-006 — P2 — MCQ 允许空提交，无批改反馈
**Surface**: chat bubble 内 MCQ 卡片 → 提交按钮

**Repro**:
1. `goto /wechat-harness`（默认 case，含 MCQ "题目 1 / 请选择正确答案"）
2. 不选 A/B 直接点 "提交" → UI 显示 `已记录选择：空`
3. 重置 → 选 A 后点 "提交" → UI 显示 `已记录选择：A`
4. 任何情况下 **无正确性反馈、无解析、无答案揭示**

**问题**:
- "提交" button 没有 aria-disabled 也不阻止空提交
- 文案 "请选择正确答案" 是题干 prompt，不是答案 leak（OK）
- harness 的 MCQ 是 view-only fixture，不走真实批改链路 — 这本身合理，但 "提交" 按钮造成误期，应明示这是预览

**Web vs 小程序**: harness 只是渲染 fixture；**小程序入口必须复测**真实 MCQ 提交流（WS submission_grader_agent → grading 闭环）是否同样允许空提交。

---

### H-007 — P2 — Exam Semantic Callouts 直接展示评分细则
**Surface**: case "Exam Semantic Callouts" (`p5-case-exam-callouts.png`)

**实测渲染内容**（无任何用户交互前直接出现）:
- **核心考点**: 屋面防水等级与设防层数要对应。
- **采分点**: 写出等级、设防道数、适用部位。
- **易错点提醒**: 不要把屋面和地下工程混在一起。
- **拿分要点**: 先判断部位 / 再写设防层数

**说明**:
- 在 Web harness 当前 fixture 里这条 message 不含 MCQ（`mcqCount: 0`），所以**没有直接答案泄露**
- 但小程序真实 chat 流中若同一 message 同时含 callouts + MCQ，则采分点/拿分要点 = 题目答案，progressive disclosure 失效

**Web vs 小程序**:
- Web harness ✅ 验证 callout 渲染本身 OK
- **必须微信入口复测**：真实 chat 里 callout 是否在 MCQ 解锁前提前出现；进阶提示按钮是否真的能"延迟揭示"采分点

---

### H-008 — P2 — 移动横滚 case row 卡片严重截断
**Surface**: 375×812 viewport 顶部 case row 横滚区 (`p2-mobile-fresh-viewport.png`)

**观察**:
- 仅显示 1.5 张卡片
- 每张卡片内可见只有 case 标题首字符 "C" 与 "教"（"chat" / "教学" tag 缩成首字）
- 必须横向滑才看得到完整 case 名 / 一致性标记 / 来源 fixture

**Web vs 小程序**: 仅 Web harness 移动布局；**不需要小程序复测**。

---

### H-009 — P3 — render model JSON 直接暴露
**Surface**: 右侧栏底部 "当前 render model"

```json
{ "mode": "final", "frame": "final",
  "blockTypes": ["table","formula_block"],
  "visibleBlockTypes": ["table","formula_block","mcq"],
  "mcqCount": 1, "hasStructuredContent": true,
  "streamPhase": "complete" }
```

**说明**: harness 内部调试很需要；但若不加 dev-only gate，产品/客户访问 `/wechat-harness` 会看到 raw schema。建议加 `process.env.NODE_ENV !== 'production'` 或权限门。

---

### H-010 — P3 — streaming Chunk 1 与 Chunk mid 渲染相同
**Surface**: mode = 实时流式 → 切换 "Chunk 1" / "Chunk mid" frame

**观察**:
- Chunk 1: bubble 显示 "先看表格，再看公式，最后作答。" + streaming chip；render model `blockTypes:[paragraph]`
- Chunk mid: bubble 显示完全相同；render model 也是 `blockTypes:[paragraph]`
- 只有 Final payload 触发完整 table+formula+MCQ 渲染

**可能性**:
- (a) fixture 设计如此，mid = 1 同语义（合理）
- (b) progressive streaming 没有真切片，跳过中间态

**Web vs 小程序**: 真实 SSE 切片仅在 chat WebSocket 里观察得到；**必须微信入口复测**：真实流式时是否能看到 paragraph → +table → +formula → +mcq 的渐进过程。

---

### H-011 — P3 — HMR WebSocket 失败噪音
6 条相同 console error：
```
WebSocket connection to 'ws://127.0.0.1:3000/_next/webpack-hmr?id=...' failed
```
dev only，生产无影响。

---

## 哪些可由 Web Harness 覆盖

✅ 渲染合同（blockTypes / visibleBlockTypes / mcqCount / hasStructuredContent / streamPhase）
✅ markdown：换行、列表、空行、`<hr>`、heading、emphasis、strong
✅ 代码块 ```A = \pi r^2``` 渲染
✅ 表格渲染（防火门 2 / 防火分区 3）
✅ formula block（A = πr² SVG）
✅ MCQ 卡片 layout 与 "提交" 行为（空提交 + 单选）
✅ chat bubble "complete" / "streaming" 状态 chip
✅ 三模式切换 实时流式 / 最终态 / 历史 hydrate
✅ "查看原文" 折叠 disclosure
✅ console error / network 4xx / 5xx 监控
✅ 桌面 1440×900 整体 layout
✅ 静态文案（公共主链通过 / 一致 / 当前结论）
✅ 真实 endpoint `/api/v1/learning-brain/harness-case-grading` 的 HTTP 健康
✅ fixture filter 行为 + 该 P3-1 e16 回归

## 必须微信小程序真实入口复测

- ❗ **MCQ 真实提交批改链路**（H-006）— harness 只 view-only，真实 grading 走 WS submission_grader_agent
- ❗ **progressive disclosure 在真实 chat 中是否提前泄露 MCQ 答案**（H-007）— 真实 chat 可能把 callouts 与同 message 的 MCQ 同时下发
- ❗ **真实 SSE / WS 流式切片**（H-010）— harness 用静态 fixture，看不到真实 token-by-token
- ❗ **学情闭环报告页 (`wx_miniprogram/pages/report/`)** — 本轮 git status 改动了 report.js / report.wxml / report.wxss，本次 QA 未触达；需要走真实 user 登录 + chat 答题 + 报告生成 → 复测假满分、假进度、空状态误导（H-004 模式是否在 report.wxml 复制）
- ❗ **学情闭环 endpoint 在真实身份下是否仍 500**（H-002）— 这次是 harness 默认 user_id `wechat_harness_learning_brain`，真实小程序 user 触发可能走另一条码
- ❗ **wxss 的 scroll-view 行为** — Web harness 的 mobile bug（H-001）不会出现在小程序原生 scroll-view
- ❗ **chat.js / chat.wxml / chat.wxss** 改动的真实展示 — 本轮 git status 显示这些都改了，没有走真实 chat 入口

---

## 附：本次 QA 覆盖的 case 清单

16 cases，全部加载成功（`Parity 16/16`）：

| Case | Source | Render | 测试动作 |
|---|---|---|---|
| Structured Table Formula Mcq Combo | wechat_structured_renderer_cases.json | table + formula + mcq | 默认载入，三模式 / 三 frame / MCQ 空提交 / MCQ 选 A 提交 / 查看原文 disclosure |
| Structured Steps Recap Chart Combo | 同 | steps + recap + chart | case 行点击切换 ✅ |
| Compact Heading Markers From Live Chat | wechat_markdown_golden_cases.json | hr + 多 heading + ul | case 行点击切换 ✅；fixture chip 切换 detail 不刷新 ❌ |
| Exam Semantic Callouts | 同 | 4× callout + ul | progressive disclosure 风险检查 |
| Billing Quota Exceeded Surface | web/lib/wechat-harness-data.ts | paragraph × 2 | 静态满分标签验证 |
| Auth Expired Retry Surface | 同 | paragraph | 同上 |
| 其余 10 cases | — | — | parity 16/16 默认列表呈现，未逐个点击 |

---

## Artifacts

- 截图目录：`.gstack/qa-reports/screenshots/2026-05-21-web-harness/`
- 关键证据：
  - `p1-desktop-initial.png` — 桌面首屏
  - `p1-desktop-streaming.png`, `p1-desktop-stream-mid.png`, `p1-desktop-stream-final.png` — streaming 三 frame
  - `p1-desktop-history.png` — history hydrate
  - `p2-mobile-initial.png`, `p2-mobile-fresh-viewport.png`, `p2-mobile-scroll1000.png`, `p2-mobile-tryscroll.png` — 移动滚动 P0
  - `p4-mcq-submit-empty.png`, `p4-mcq-submit-A.png` — MCQ 行为
  - `p5-disclosure-raw.png`, `p5-case-exam-callouts.png`, `p5-case-steps-recap.png` — disclosure / case 切换
  - `p6-learning-brain-run.png`, `p6-case-billing.png`, `p6-case-auth.png` — 学情闭环 500 / 错误页 / 假满分
  - `p8-fixture-e16-compactHeading.png`, `p8-case-compactHeading-row.png` — P3-1 e16 回归证据
  - `p0-login-404.png` — `/login` 路由 fallback（"配置控制台暂不可用"，非 404）

## Status

`DONE` — 9 phases 全部完成，0 修复，11 issue（1×P0、2×P1、5×P2、3×P3）。
