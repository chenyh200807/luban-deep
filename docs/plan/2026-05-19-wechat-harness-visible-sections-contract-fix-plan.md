# DeepTutor `/wechat-harness` Visible Sections Contract 治本计划

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-19 |
| 主线 | 学习事实编译 / Evidence-first Memory（挂入 INDEX.md 主线 4） |
| 状态 | Draft |
| 作者 | 接入 /qa-only 后的 root-cause 调查 |
| 关联 ISSUE | qa-report 2026-05-19 ISSUE-001 / -002 / -003（已重判） |
| 单一 authority | `learning_brain_read_model.visible_sections` （`current_truth / evidence_flow / next_training`） |

---

## 1. 目标（What must be true after this lands）

1. **「visible chain 视图」只有一个 authority**：`learning_brain_read_model.visible_sections`。任何 wrapper（Python inline HTML、Next.js React、未来微信小程序原生页）都消费同一份 contract、渲染同一组三段中文标题。
2. **Next.js `/wechat-harness` page 与后端 `_qa_enabled()` 对齐**：production 下两端都 404，dev/local 下两端都开放。
3. **commit c5900022 message 描述（中文 3 段 visible-chain）落地到 Next.js 端**——但落地方式是「让 Next.js 遵守已有 contract」，不是凭空补 i18n 字典。

## 2. 非目标（What this plan explicitly does NOT do）

- ❌ 不优化 `/api/v1/learning-brain/harness-case-grading` 的 6.9s 冷启动。原因：harness 串行调真 grading + writeback + synthesize 是**设计意图**（端到端 visible-chain 验证），不是 hot path；同样的 endpoint 不被生产路径用。如后续担心生产 grading 路径性能，另起 plan。
- ❌ 不删 `deeptutor/api/routers/learning_brain.py:29-151` 的 Python inline HTML wrapper。两个 wrapper 物理独立（Next.js 在 `:3000/wechat-harness`、FastAPI 在 `:8001/wechat-harness`，且 `next.config.js` rewrites 不覆盖该 path）、服务不同人群（后端 dev / 前端 dev），可共存——只要两者**消费同一 contract**。
- ❌ 不动 `web/lib/wechat-harness-data.ts` 的 case fixtures、phone preview、mode switching、parity inspector 等无关代码（AGENTS §3 Surgical Changes）。
- ❌ 不引入新 env flag、不新增 i18n 字典系统、不改 contracts/learner-state.md。

## 3. Root Cause 复盘（four-question discipline, AGENTS §5.5）

| 维度 | 内容 |
| --- | --- |
| **业务事实** | 学习者 / 教研 / 开发者打开 visible chain 时，应看到「当前可信结论 / 证据流 / 下一步训练」三段中文摘要，对应 read model 内 `visible_sections.{current_truth, evidence_flow, next_training}` |
| **Authority** | `deeptutor/services/learner_state/learning_brain_read_model.build_learning_brain_read_model` 是 visible chain 视图的唯一 authority；`_mobile_sections`（line 295-315）输出三段已 humanize 的 items |
| **Contract** | Read model 返回 `{visible_sections: {current_truth, evidence_flow, next_training}}`；每个 item 至少携带 `display_title / display_meta / display_label / display_path / evidence_level_label / event_id`（Python HTML 在 router line 119-127 已经按这个 shape 消费） |
| **状态流转** | API → JSON `visible_sections` → wrapper 渲染。Python HTML 走完链路；Next.js `LearningBrainEvidenceChain` (line 401-466) **绕过 contract**，直接消费底层 `compiled_objects / typed_graph_edges` |

→ **真根因 = Next.js `LearningBrainEvidenceChain` 实现层下沉到 internal projection，跳过了已经存在的 `visible_sections` 业务事实层**。这是经典 contract violation，不是 i18n 漏覆盖、不是 commit message 错写、不是 design intent 模糊。

ISSUE-003 (JSON dump leak) 与 ISSUE-001 同根因家族：Next.js page **完全没有 production gate**，与后端 `_qa_enabled()` 不对齐——一旦未来 `/wechat-harness` 路由被生产 build 起飞，case fixtures + inspector 内部 JSON 会同时漏出。

ISSUE-002 (6.9s) 与上述无关，且不是真 bug（见 §2 非目标）。

## 4. 修复方案（thin wrappers, fat skills, surgical changes）

### P0 — Next.js `LearningBrainEvidenceChain` 改为消费 `visible_sections`（治本）

**Authority Restoration**：

- 修改文件：`web/app/wechat-harness/WechatHarnessClient.tsx`
- 范围：
  - `LearningBrainResponse` type 增加 `visible_sections?: { current_truth: VisibleItem[]; evidence_flow: VisibleItem[]; next_training: VisibleItem[]; }` 字段（与 read model contract 对齐）
  - `LearningBrainEvidenceChain` (line 401-466) **完全重写**：从 `result.visible_sections` 渲染三段，中文 heading 固定为「当前可信结论 / 证据流 / 下一步训练」
  - 删除直接消费 `compiled_objects / typed_graph_edges` 的渲染（这两个字段仍保留在 type 里，但 evidence-chain section 不再读它们）
  - 文件顶部 `eslint-disable i18n/no-literal-ui-text` 保留（dev mirror 故意，与 contracts/learner-state.md:291 一致）
  - `result.compiled_objects` / `result.typed_graph_edges` 的现有渲染可作为附加 inspector 折叠区保留（**仅作为 dev-only 二级 inspector，title 明示「raw projection (dev only)」**），不进入 visible-chain 主视图
- 约 50-80 行 diff

**Why this is root-cause-fix not patch**：
- 不是补 i18n 字典（那是症状层）
- 不是改 commit message（那是粉饰）
- 而是**让 Next.js 遵守已有的 contract**——后端早已暴露 visible_sections，Python wrapper 早已正确消费，这就是 single authority

### P1 — Next.js `/wechat-harness` page 加 production gate（防御对齐）

- 修改文件：`web/app/wechat-harness/page.tsx`
- 范围：
  - import `notFound from "next/navigation"`
  - server component 内 check `process.env.DEEPTUTOR_ENV` 和 `process.env.DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA`，逻辑**与后端 `_qa_enabled()` 完全对齐**：`runtime_environment() == "local" AND flag == truthy`
  - 不符合时调 `notFound()`
  - 约 10-15 行 diff
- 复用：把 env 解析封装成共享 helper（`web/lib/wechat-harness-gate.ts` 或类似），未来如果加更多 dev-mirror 页面共用——但仅当本次有 ≥2 处用到，否则 inline（less is more）。**本次只有 1 处，inline。**

**Why this is hardening not band-aid**：
- 后端早已存在 `_qa_enabled()` 三层验证（tests 已覆盖：`test_learning_brain_harness_is_disabled_in_{staging,production}_even_with_flag`）
- 前端 page 完全无 gate 是单点缺口
- 与后端用相同 env flag = 两端配置统一，无需新增运维项

### 不在 P0/P1 范围（明确）

- ISSUE-002 dev harness 6.9s：no fix，加 inline comment 一行说明「intentionally end-to-end, not hot path」即可
- Python inline HTML wrapper：保留不动
- 微信小程序 deeptutor 原生页 (`yousenwebview/packageDeeptutor/`) 的 visible chain 渲染：不在本计划——AGENTS §4:166 仍要求人工微信开发者工具回归 c03053d7

## 5. 验收标准（must-have，缺一不可）

| # | 检查项 | 验证手段 |
| --- | --- | --- |
| A1 | `/wechat-harness` happy path 后，visible-chain 容器 (`[data-testid=learning-brain-visible-chain]`) 渲染 3 个 `<section>` | 重跑 `/qa-only`，DOM dump childCount==3 |
| A2 | 三个 section heading 文本分别等于「当前可信结论」「证据流」「下一步训练」 | DOM `getElementsByTagName('h3')` 取文本断言 |
| A3 | 三段内容来自 `visible_sections.{current_truth, evidence_flow, next_training}`（不是 `compiled_objects` / `typed_graph_edges`） | 在 `WechatHarnessClient.tsx` 中 grep `compiled_objects` 出现在 `LearningBrainEvidenceChain` 内必须为 0 |
| A4 | `NODE_ENV=production` 且 `DEEPTUTOR_ENV` 不是 `local` 时，`/wechat-harness` 返回 404 | `cd web && NODE_ENV=production npm run build && NODE_ENV=production DEEPTUTOR_ENV=production npm run start`，`curl localhost:3000/wechat-harness` HTTP 404 |
| A5 | local + `DEEPTUTOR_ENABLE_LEARNING_BRAIN_QA=1` 时 `/wechat-harness` 正常加载 | 重跑 `/qa-only` 不受影响 |
| A6 | 现有测试不破坏 | `pytest tests/api/test_learning_brain_router.py tests/services/learner_state/test_learning_brain_read_model.py -q` 全绿 |
| A7 | 新增 Playwright 测试覆盖 A1+A2 | `web/tests/wechat-harness.spec.ts` 增加 `test("visible chain renders three Chinese sections", ...)` 一例 |
| A8 | 新增 Playwright 测试覆盖 A4 | `web/tests/wechat-harness.spec.ts` 增加 `test("page is 404 in production", ...)`（用 env mock 或独立 spec） |

## 6. 风险与不确定性（明确指出，按要求）

| # | 不确定点 | 应对 |
| --- | --- | --- |
| U1 | `visible_sections` 字段在 `surface="qa"` 时走 `_qa_sections`，与 `surface="mobile"` 的 `_mobile_sections` shape 不同。当前后端 `harness-case-grading` 调 `surface="mobile"`，Next.js 也消费这个；但 `_qa_sections` 的 shape 没在本次 read 范围内验证 | Subagent 必须先读 `learning_brain_read_model.py:230-290` 的 `_qa_sections` 实现确认 shape；如果 shape 不同，Next.js 类型断言保持 surface="mobile"（API 调用方决定 surface）|
| U2 | Next.js `page.tsx` server component 能否读非 `NEXT_PUBLIC_` 前缀的 env var | 可以（server component 进程级 `process.env`）。但 `next dev` 加载 `.env.local` 的 timing 要验证 — 若不行，fallback 用 `next.config.js` 的 publicRuntimeConfig |
| U3 | `LearningBrainEvidenceChain` 重写后，5/19 早间 baseline `baseline-learning-brain-2026-05-19.json` 中的 ISSUE-002 "Typed graph did not expose complete training result chain" 是否回归 | 修复方案保留 typed_graph 作为附加 inspector 折叠区（不删数据，只把它从 visible-chain 主视图移开）；新 Playwright 测试不应断言 typed_graph 缺失 |
| U4 | 三段中文 heading 是否会被未来 i18n 系统反向锁定为英文 | 当前 `eslint-disable i18n/no-literal-ui-text` 仍生效，三段中文是硬编码——这是 dev mirror 故意，与 contracts/learner-state.md:291「dev/local 可见链路验证入口」一致；如果未来引入完整 i18n，需要同步更新本文件 + Python inline HTML 对应位置 |

## 7. 执行方式

**Phase 1 — Brainstorm 已完成**：root cause 已定位（见 §3）

**Phase 2 — Build（用 `superpowers:dispatching-parallel-agents` 并行）**：

- **Subagent A（codex:codex-rescue）**：执行 P0
  - 必读：`deeptutor/services/learner_state/learning_brain_read_model.py:70-170, 230-320`（read model + `_qa_sections` + `_mobile_sections`）+ `deeptutor/api/routers/learning_brain.py:60-130`（Python wrapper 如何消费 visible_sections）+ `web/app/wechat-harness/WechatHarnessClient.tsx:401-466`（要改的代码）
  - 必须遵守：thin wrappers fat skills、surgical changes、不改任何 §2 非目标范围内文件
  - 交付：单 commit，diff 仅触 `WechatHarnessClient.tsx` + 必要的 `wechat-harness-types.ts` type 字段
- **Subagent B（general-purpose）**：执行 P1
  - 必读：`deeptutor/services/runtime_env.py` + `deeptutor/api/routers/learning_brain.py:154-155` (`_qa_enabled`) + `tests/api/test_learning_brain_router.py:182-235`
  - 交付：单 commit，diff 仅触 `web/app/wechat-harness/page.tsx`（如有 helper 文件，inline 同 page.tsx）
- **Subagent C（general-purpose）**：执行 A7+A8 Playwright 测试新增
  - 必读：`web/tests/wechat-harness.spec.ts`（现有写法）
  - 交付：在 spec 文件追加 2 个 test case

**Phase 3 — Verify**：

- 跑 `pytest tests/api/test_learning_brain_router.py tests/services/learner_state/test_learning_brain_read_model.py -q`
- 跑 `cd web && npm run lint && npx playwright test wechat-harness.spec.ts`
- 重跑 `/qa-only` against `:3000/wechat-harness` → 期望 baseline 从 85 → ≥95（ISSUE-001/003 消失，ISSUE-002 保留为 INFO 不计分）
- 跑 production gate 黑盒测试（A4 manual check 或在 spec 里 mock env）

## 8. 相关代码入口

| 关注点 | 入口 |
| --- | --- |
| Read model authority | `deeptutor/services/learner_state/learning_brain_read_model.py:65-145` |
| Visible sections 来源 (mobile surface) | `deeptutor/services/learner_state/learning_brain_read_model.py:295-315` |
| Visible sections 来源 (qa surface) | `deeptutor/services/learner_state/learning_brain_read_model.py:317- …` |
| 后端 production gate | `deeptutor/api/routers/learning_brain.py:154-155, 207, 234` |
| 后端 inline HTML wrapper（正确消费 contract，参考实现） | `deeptutor/api/routers/learning_brain.py:29-151` |
| Main app HTML route mount | `deeptutor/api/main.py:504-506` |
| Next.js page（缺 gate） | `web/app/wechat-harness/page.tsx` |
| Next.js evidence chain（违反 contract） | `web/app/wechat-harness/WechatHarnessClient.tsx:401-466` |
| 现有 prod gate 测试 | `tests/api/test_learning_brain_router.py:182-235` |
| 现有 Playwright | `web/tests/wechat-harness.spec.ts`, `web/playwright.config.ts:41` |
| Contract 文本 | `contracts/learner-state.md:289-292` |

## 9. 实施阶段（最小 PR 切片）

| 阶段 | 内容 | 验证门 |
| --- | --- | --- |
| 阶段 0 | 本计划获用户批准 | AskUserQuestion 确认 |
| 阶段 1 | P0 + P1 + A7/A8 测试（同一 PR）| 验收 A1-A8 全绿 |
| 阶段 2 | 重跑 /qa-only 出新报告，归档 baseline | qa-report 新文件 |

阶段 1 是**单 PR**（不拆）：因为 P0 改 contract 消费方 + P1 加 gate 是同一 single authority 治本动作，分两个 PR 会让中间态有「gate 已加但视图仍违反 contract」的尴尬。
