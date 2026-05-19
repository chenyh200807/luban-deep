# QA Report: wechat-harness 可见链路

> 报告位置说明：本仓库 Write hook 限制 `.md` 只能落在 `docs/` 等白名单目录，因此本报告写在 `docs/qa/` 而非 gstack 默认的 `.gstack/qa-reports/`。screenshots 仍在 `.gstack/qa-reports/screenshots/`，baseline 仍在 `.gstack/qa-reports/baseline.json`。

| Field | Value |
|-------|-------|
| **Date** | 2026-05-19 |
| **URL** | http://localhost:3000/wechat-harness |
| **Branch** | codex/gbrain-learning-brain |
| **Commit** | 1ee4a7dc (2026-05-19) |
| **PR** | — |
| **Tier** | Standard (报告模式 / 不修复) |
| **Scope** | Next.js 渲染的 `/wechat-harness` 页面（commit c5900022 引入；微信小程序 webview 内嵌容器），**不含** `yousenwebview/` 小程序 shell 本身（须走 `scripts/run_wechat_learning_brain_devtools_e2e.py`） |
| **Duration** | ~12 分钟 |
| **Pages visited** | 1（深度交互） |
| **Screenshots** | 5（位于 `.gstack/qa-reports/screenshots/`） |
| **Framework** | Next.js 16.2.6 (Turbopack)；FastAPI :8001 后端通过 next.config.js rewrites 代理 |

## Health Score: 85/100

| Category | Score |
|----------|-------|
| Console | 100 |
| Links | n/a (单页交互) |
| Visual | 100 |
| Functional | 85 |
| UX | 92 |
| Performance | 92 |
| Accessibility | 95 |
| Content | 97 |

加权计算（按 /qa-only 默认权重）：`15 + 10 + 17 + 13.8 + 9.2 + 14.25 + 4.85 ≈ 85`。

## Top 3 Things to Fix

1. **ISSUE-001: visible-chain section 标题未本地化，且实际只渲染 2 段（commit message 描述说 3 段）** — commit c5900022 与 cfc32879 i18n 工作的实际产出落差；中文学习者看到的是英文 debug 标签。
2. **ISSUE-002: API 首次响应 6.9 秒，无可见进度反馈** — 在微信 webview 实战中会被误判为按钮失灵，存在重复点击放大后端负载的风险。
3. **ISSUE-003: result 段直接渲染 ~5KB 原始 JSON（construction_exam_learning_truth schema）** — QA harness 输出与最终用户视图未清晰分层。

## Console Health

| Error | Count | First seen |
|-------|-------|------------|
| — | 0 | — |

跨四次 click 交互（首次触发、空字段触发、二次触发、refs 刷新）均 `(no console errors)`，干净。

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 1 |
| Medium | 1 |
| Low | 1 |
| **Total** | **3** |

> 另记录 1 项 **POSITIVE finding**（防御性 UX 工作正常）：见末段。

## Issues

### ISSUE-001: visible-chain 三段中文标题缺失，仅渲染 2 段英文 debug 标题

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Category** | functional / content / i18n |
| **URL** | http://localhost:3000/wechat-harness |

**Description:**

commit c5900022 message 明确写道：

> render **当前可信结论 / 证据流 / 下一步训练** sections from the `/api/v1/learning-brain/harness-case-grading` response.

并且分支上有专门的 i18n commit cfc32879 "Localize Learning Brain report labels for Chinese learners"。

实测 DOM 结果：

```js
document.querySelector('[data-testid=learning-brain-visible-chain]')
// → <DIV> with childCount: 2
//   section[0].firstHeading = "Compiled truth + timeline"
//   section[1].firstHeading = "Typed graph chain"
```

全页面 HTML grep：

| 字符串 | 出现 |
|---|---|
| `当前可信结论` | ❌ false |
| `证据流` | ❌ false |
| `下一步训练` | ❌ false |
| `Compiled truth` | ✅ true |
| `Typed graph` | ✅ true |

→ commit message 承诺的「3 段中文 visible-chain」实际只渲染了「2 段英文 section」。预期面向中文学习者的产品 UI 默认显示了内部英文 debug 标签。这要么是 i18n 回退了，要么是 c5900022 的命名/数量与实现脱节。

**Repro Steps:**

1. 启动 dev：
   - 后端 `uvicorn deeptutor.api.main:app --host 127.0.0.1 --port 8001`
   - 前端 `cd web && npm run dev`（或 hook-compliant `tmux new-session -d -s dev "cd web && node ./node_modules/next/dist/bin/next dev"`）
2. 浏览器打开 `http://localhost:3000/wechat-harness`
   ![Initial](../../.gstack/qa-reports/screenshots/01-initial.png)
3. 在 inspector 区域保留默认 User ID = `wechat_harness_learning_brain` 与默认案例答案，点 **运行闭环**
4. 等 ~7 秒，POST 200 返回，visible-chain 渲染完成
   ![After run](../../.gstack/qa-reports/screenshots/04-after-wait.png)
5. **观察**：visible-chain 容器只有 2 个 `<section>`；标题是英文 `Compiled truth + timeline` 与 `Typed graph chain`；中文 `当前可信结论 / 证据流 / 下一步训练` 这三个字符串在整个 HTML 里都不存在。

---

### ISSUE-002: `/api/v1/learning-brain/harness-case-grading` 首次响应 6875ms，UI 无进度反馈

| Field | Value |
|-------|-------|
| **Severity** | Medium |
| **Category** | performance / ux |
| **URL** | http://localhost:3000/wechat-harness → POST /api/v1/learning-brain/harness-case-grading |

**Description:**

实测网络耗时（gstack browse network log）：

| 触发 | 状态 | 耗时 | 大小 |
|---|---|---|---|
| 首次 click 运行闭环 | 200 | 6875ms | 57380B |
| 第二次 click（同 payload） | 200 | 1582ms | 57380B |

→ 冷启动 6.9s，热路径 1.6s（推测后端有 cache 或 lazy init）。

在微信小程序 webview 视角，这 7 秒内：
- ✅ `运行闭环` 按钮**有**文字反馈："运行闭环" → "运行中..."（见截图 03）
- ❌ 但**没有** spinner / progress bar / 旋转图标，文字反馈在小屏 / 高 DPR 设备上感知较弱
- ❌ result 区与 visible-chain 区在等待期间无 "loading…" / skeleton 占位（仍显示上一次结果或空白）
- ❌ 主屏没有任何"正在串流"的 progressive 反馈，6.9s 内除了角落里的 button 文字外，**用户看不到任何变化**

用户在 webview 全屏视角下若没注意到 button 文字变化，仍可能误判"按了没反应"，存在重复点击概率，会放大后端冷启动开销。

**Repro Steps:**

1. 首次加载 `/wechat-harness`，确保是冷启动（或后端刚 reload）
2. 不改默认值，点 **运行闭环**
3. **观察**：button 文字立刻变成"运行中..."（截图 03）；但 visible-chain 与 result 区在整个 6.8s 期间无变化。网络面板显示 POST 在 pending 状态持续 6.8+ 秒。
   ![before — button="运行闭环"](../../.gstack/qa-reports/screenshots/02-before-run.png)
   ![during — button="运行中..."，主屏无变化](../../.gstack/qa-reports/screenshots/03-after-run.png)
   ![after — visible-chain + result 渲染完成](../../.gstack/qa-reports/screenshots/04-after-wait.png)

---

### ISSUE-003: result 段渲染 ~5KB 原始 JSON（construction_exam_learning_truth schema），未与产品视图分层

| Field | Value |
|-------|-------|
| **Severity** | Low |
| **Category** | content / ux |
| **URL** | http://localhost:3000/wechat-harness |

**Description:**

`learning-brain-result` testid 容器内：

- 总文本长度 5333 字符
- 50 个 `<pre>` / `<code>` 节点
- 其中包含完整 `construction_exam_learning_truth` schema 原文：

```json
{
  "subject": "construction_exam_learning_truth",
  "weak_points": [
    {
      "concept_id": "1A432000",
      "error_code": "E02",
      "claim": "工程招标投标与合同管理 上出现 采分点遗漏 错因",
      "supporting_event_ids": [
        "d9e2e6955a2f4b8295c860681592c46f",
        "95afc3480f574163930f1737faf8d292"
      ],
      ...
```

本意是 QA harness 给工程师调试用的「inspector 视图」，但页面上**没有任何文本明确告诉读者「这是 dev/QA only」**，并与上方 visible-chain（产品视图）排布在同一页同一垂直流里，存在两种风险：

1. 误把 `/wechat-harness` 路由开放给非工程用户（demo / 截图 / 录屏 / 内部演示场景）时，会暴露 internal schema、event UUID、内部错因代码。
2. 未来如果有人复用本 inspector 的 React 组件到面向用户的页面，缺乏「inspector / production」分层会让 dev-only 数据漏出。

**Repro Steps:**

1. 在 `/wechat-harness` 触发 **运行闭环**
2. 滚动到下半部分 result 区
3. **观察**：连续多个代码块直接 dump JSON，含 `subject`, `weak_points`, `supporting_event_ids`, `concept_id`, `error_code` 等字段；末段反复出现 `training_not_improved_error / 1A432000:E02:projected_rubric:危险性较大工程专项方案程序 → 1A432000:E02`。
   ![result with JSON dump](../../.gstack/qa-reports/screenshots/04-after-wait.png)

---

## Positive Findings

**PF-001: 输入校验防御正常工作**

清空 User ID 与案例答案后：
- `<button data-testid="learning-brain-run">` 自动 `[disabled]`
- 点击 disabled button 不发出 network 请求（browse network log 无新条目）
- 0 console errors
- result 区保留上一次结果，不会被空请求污染

→ 表明前端在按钮层面已经防御了「空字段提交」的废请求场景。后端无需额外校验也不会被无效输入触发。建议保留并在未来变更时回归这条 behavior。

![empty fields state](../../.gstack/qa-reports/screenshots/05-empty-fields.png)

---

## Pages Visited & Evidence Index

| # | 阶段 | 截图 |
|---|------|------|
| 1 | 初次加载 `/wechat-harness` | `.gstack/qa-reports/screenshots/01-initial.png` |
| 2 | 触发运行闭环之前 | `.gstack/qa-reports/screenshots/02-before-run.png` |
| 3 | 第一轮 click 之后 ~2s | `.gstack/qa-reports/screenshots/03-after-run.png` |
| 4 | 等待 ~10s 后 stream 完成 + visible-chain 渲染 | `.gstack/qa-reports/screenshots/04-after-wait.png` |
| 5 | 清空字段后 button disabled | `.gstack/qa-reports/screenshots/05-empty-fields.png` |

## Scope Disclaimers / Deferred

- **小程序 shell (`yousenwebview/`) 未测**：headless Chromium 不能加载 `.wxml/.wxss` 与 `wx.*` API。**AGENTS.md:166 硬约束（前端或微信小程序改动必须至少完成一次微信开发者工具中的模拟器或真机回归验证）仍未满足**——必须由人工跑 `python scripts/run_wechat_learning_brain_devtools_e2e.py` 或在微信开发者工具的模拟器/真机回归一次 commit c03053d7 引入的 home → deeptutorEntry 导航路径。本报告**不替代**该步骤。
- **未测移动 viewport / 真机宽度**：本次只跑 desktop default viewport。webview 内实际宽度受微信 UA 与设备 DPR 影响，可能与 desktop 渲染差异较大；若担心，建议补一次 `$B viewport 375x667` 回归。
- **未鉴权场景未覆盖**：harness 接口默认 happy path 走通；未模拟 `Authorization` header 缺失 / token 过期 / Supabase 写边界（commit 10c89016 `compiled_truth_source` 改 read-only 后的副作用）。

## 后续建议（信息性，不属 fix）

1. **ISSUE-001 处置方向**：让 commit message 与实现对齐——要么补齐"下一步训练"第三段 + 中文 label，要么修订 commit description 用准确数量与英文 label。建议先 grep `Compiled truth`/`Typed graph` 在 `WechatHarnessClient.tsx` 是否还有 i18n 包装的剩件。
2. **ISSUE-002 处置方向**：button 上加 loading state + spinner；或将 6.9s 冷启动拆成 streaming（SSE/chunk），让首字节 < 1s 内吐出。
3. **ISSUE-003 处置方向**：在 inspector 容器外明确加 `<header>DEV / QA harness — internal only</header>` 横条 + 折叠包装；或仅在 `NODE_ENV !== 'production'` 时挂载该 inspector React 组件。

---

## Verification Summary

- `tmux ls` → `dev: 1 windows`（Next.js dev 跑在受控 tmux session 内，日志在 `.local-runs/qa/web-dev.log`）
- `curl :3000/wechat-harness` → 200
- `curl :3000/api/v1/learning-brain/harness-case-grading` proxy → 命中 :8001（FastAPI），代理链路 OK
- gstack browse console 全程 `(no console errors)`
- gstack browse network 累计仅 POST 200，无 4xx/5xx

---

## Regression Baseline

新 baseline 写入 `.gstack/qa-reports/baseline.json`；旧 baseline 备份为 `.gstack/qa-reports/baseline-2026-05-18.json`。

跨 baseline 对照（不直接构成 regression 结论）：

| Baseline 文件 | 时间 | URL | Score | Issues 数 | 备注 |
|---|---|---|---|---|---|
| `baseline-2026-05-18.json`（旧） | 2026-05-18 | `:3802/wechat-harness` | 100 | 0 | 字段稀疏，疑似 stub；端口与 build 不同 |
| `baseline-learning-brain-2026-05-19.json` | 2026-05-19 早间 | `:8001/wechat-harness` | 88 | 3 (verified) | 含 "Learner-visible Learning Brain text leaked raw identifiers"，与本次 ISSUE-003 同类型 |
| **`baseline.json`（本次新）** | 2026-05-19 17:00 | `:3000/wechat-harness` | 85 | 3 (high/medium/low) | 本报告所用 |

git log 显示 c5900022 之后 (HEAD = 1ee4a7dc) **没有任何** `web/app/wechat-harness/` 或 `deeptutor/api/routers/learning_brain.py` 改动。本次 ISSUE-001/002/003 **大概率从 c5900022 引入起就存在**，不是最近 5 个 commit 的新回归。

下次跑 `/qa-only --regression .gstack/qa-reports/baseline.json` 即可对比。
