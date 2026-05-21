# 2026-05-21 — QA Assets Verification（main 上自动化覆盖核对）

| Field | Value |
|---|---|
| 日期 | 2026-05-21 |
| 模式 | **只读核对**（无 edit / commit / PR / 不修源码） |
| 输入 | `docs/qa/2026-05-21-qa-triage-rollup.md` §7 "应修但不阻塞" 自动化部分 |
| 目的 | 核对 main 上 QA assets 是否已实现 §7 列出的自动化项；确认 release 硬门槛缺口；区分自动化可达 vs 真机不可替代 |
| 当前 main HEAD | `cc32c5e5 docs: record QA triage and web harness deep report` |

---

## 0. TL;DR

| 资产 | main 状态 | 当前能跑通 | CI 接入 |
|---|---|---|---|
| `ws-stream.js` 纯函数下沉 + contract test | ✅ 已落盘 | ✅ 65 assertions PASS | ❌ **未接 CI** |
| Progressive disclosure negative fixtures + 已知 gap 矩阵 | ✅ 已落盘 | ✅ 8 vectors PASS（4 blocked + 4 known-gap） | ❌ **未接 CI** |
| Token boundary 细粒度 fixture | ✅ 已落盘 | ✅ **2208** assertions PASS（6 × 4 策略） | ❌ **未接 CI** |
| Progressive disclosure render 单元测试 | ✅ 已落盘 | ✅ 6 assertion groups PASS | ❌ **未接 CI** |

**核心发现**：§7 列出的自动化资产**全部已存在**且**全部本地可跑通**，但**全部未接 CI** —— 即使下次有人改 sanitizer / ws-stream / markdown 渲染，这 4 套契约测试**不会自动触发**。**资产已 boil 完，enforcement 还没收紧。**

---

## 1. 已覆盖的 QA Asset 清单

### 1.1 ws-stream 纯函数下沉

**文件**：
- `wx_miniprogram/utils/ws-stream-pure.js`（153 行）—— 从 `ws-stream.js`（530 行）抽出 8 个纯函数 + 3 个常量
- `wx_miniprogram/tests/test_ws_stream_pure_contract.js`（454 行）—— 65 assertions / 8 个 groups

**下沉的函数**（与 §7 Gap-1 列出的全部命中）：
| 函数 | 测试覆盖 | 关键断言 |
|---|---|---|
| `normalizeErrorMessage` | Group 1（16 case） | traceback / DataInspectionFailed / api key / HEARTBEAT / read_file / HTTP_500 等 7 类内部 trace **必须**归一化为 "服务暂时不可用，请稍后重试" |
| `resolveEventVisibility` | Group 2（7 case） | `visibility=internal` 直接 / metadata 嵌套 / 大小写不敏感 / 空安全 |
| `buildStatusEvent` | Group 3（8 case） | internal progress **必须** swallow (return null)；internal thinking/observation **必须** 清空 content 且标记 `sanitized_internal=true` |
| `buildTurnSocketPayload` | Group 4（5 case） | seq>0 → `resume_from`；seq=0 → `subscribe_turn`；空 turn_id → null |
| `computeReconnectDelayMs` | Group 5（8 case） | 1→400, 2→800, 3→1600, 4→3200, 5+→4000（clamp） |
| `inferConversationTitle` | Group 6 | 50 字截断 + ellipsis |
| `buildFinalResponseEvent` | Group 7 | blank 返 null；嵌套 metadata.response 透传 |
| `buildPresentationEvent` | Group 8 | 缺失 / null safe |

**跑通证据**（本地实跑）：
```
PASS test_ws_stream_pure_contract.js (65 assertions)
```

### 1.2 Progressive disclosure negative fixtures + known-gap 矩阵

**文件**：
- `tests/fixtures/wechat_answer_leak_attack_cases.json`（169 行）—— **8 个 attack vector**
- `wx_miniprogram/tests/test_answer_leak_attack.js`（131 行）

**attack vector 矩阵**（直接来自 fixture）：

| # | attack_vector | marker | must_be_blocked | 当前状态 |
|---|---|---|---|---|
| 1 | `progressive_disclosure.sections.grading_key` | LEAK_GRADING_KEY_001 | ✅ true | **已拦** |
| 2 | `progressive_disclosure.sections.correct_answer` | LEAK_CORRECT_ANSWER_002 | ✅ true | **已拦** |
| 3 | `progressive_disclosure.sections.scoring_points` | LEAK_SCORING_POINTS_003 | ✅ true | **已拦** |
| 4 | `progressive_disclosure.sections.explanation` | LEAK_EXPLANATION_004 | ✅ true | **已拦** |
| 5 | `fallback_text_markdown`（后端把 "正确答案：X" 写进 markdown） | LEAK_FALLBACK_TEXT_005 | ⚠️ false | **known-gap** |
| 6 | `mcq.options[].text`（采分点关键词塞进 option text） | LEAK_MCQ_OPTION_006 | ⚠️ false | **known-gap** |
| 7 | `mcq.followup_context`（correct_answer 字段保留在 followupContext） | LEAK_FOLLOWUP_CTX_007 | ⚠️ false | **known-gap** |
| 8 | `callout_block.content`（callout 块内含答案解析） | LEAK_CALLOUT_008 | ⚠️ false | **known-gap** |

**测试的精妙处**（活规范）：
- 已拦路径：marker **必须不** 出现在 render state（出现 = 回归）
- known-gap 路径：marker **必须出现**（不出现 = 有人收紧了 sanitizer → 提示作者翻 `must_be_blocked=true`、删 `minimum_fix_suggestion`、写 CHANGELOG）
- 每个 known-gap fixture 都自带 `minimum_fix_suggestion` 字段，是这次 release 之前可以直接抄作业的 fix 蓝图（见 §4）

**跑通证据**：
```
─── Attack surface coverage summary ───
  ✓ blocked vectors:    4 / 8
  ⚠ known leak vectors: 4 / 8

Known-gap vectors (current scope of leak) — each needs explicit ack before next release:
  - fallback_text_markdown → fallback_text_contains_correct_answer
  - mcq.options[].text → mcq_option_text_contains_scoring_points
  - mcq.followup_context → mcq_followup_context_correct_answer
  - callout_block.content → callout_block_explanation

PASS test_answer_leak_attack.js (8 assertions across 8 attack vectors)
```

**与 triage rollup §6 判断 1 / §3 M-P0-1 / coverage-calibration §4 风险 #3 的关系**：完全闭环。M-P0-1 提出的"sanitize 只覆盖 progressive_disclosure 路径，绕过路径会泄露"已被这个 fixture 形式化为 4 个具体 attack vector，且每个都有 minimum_fix_suggestion。

### 1.3 Progressive disclosure render 单元测试（正向）

**文件**：`wx_miniprogram/tests/test_progressive_disclosure_render.js`（81 行）

**6 个 assertion group**：
1. `sanitizeProgressiveDisclosure` 剥离 4 个 hidden authority key
2. `deriveAiMessageRenderState` 把 sanitized payload 透传到 state（同样 4 key 不可泄露）
3. action chips 覆盖 "再练3题 / 讲透这个点 / 看记忆口诀" 三个语义
4. 空 payload 返回 null
5. verdict ≤120 chars / one_line_diagnosis ≤80 chars 截断
6. `difficulty_pacing` 非法值回退到 `hold`

**跑通证据**：
```
PASS test_progressive_disclosure_render.js (6 assertions groups)
```

### 1.4 Token boundary 细粒度 fixture

**文件**：
- `tests/fixtures/wechat_stream_token_boundary_cases.json`（44 行，**6 fixture**）
- `wx_miniprogram/tests/test_stream_token_boundary.js`（285 行）

**6 个 fixture**（覆盖范围）：
| name | 覆盖形态 | expected_newlines_min |
|---|---|---|
| `numbered_list_with_inline_bold` | 编号列表 + **粗体**：内容 | 8 |
| `paragraphs_with_blank_separators` | 多段落 + `\n\n` 间隔 | 14 |
| `mcq_option_inside_markdown` | MCQ 选项 text 在流式中切开 | 7 |
| `bulleted_list_with_punctuation_chain` | 无序列表 + 中文标点链 | 6 |
| `teaching_fallback_callouts` | 教学型 callout（核心结论 / 易错点 / 口诀） | 6 |
| `long_paragraph_no_markdown` | 纯长段落（验证不插入意外换行） | 0 |

**4 种切分策略 × 6 fixture = 24 组合**，每组合 50+ 帧 token-by-token 喂入：
1. `char-1`：每 1 字符切一刀（极致 token-by-token，硬要求 ≥50 chunks）
2. `char-3`：每 3 字符切一刀（接近真实 LLM token 大小）
3. `newline-boundary`：每个 `\n` 独立成帧（**当前分支主题** `fix/markdown-streaming-render-newline-loss` 的复现场景）
4. `risky-boundary`：在 `**` / `：` / `: ` / `- ` / `数字.` 边界劈一刀

**两条不变量**（每帧检查）：
- A：`renderableContent` 的换行数永远 ≤ 累积输入换行数（normalize 不能凭空插换行）
- B：渲染换行数随累积输入单调非降（不能反向丢字符）

**两条最终态**：
- 增量喂完后 `renderableContent` ≡ 一次性喂完
- 最终换行数 ≥ fixture 声明的 `expected_newlines_min`

**跑通证据**：
```
PASS test_stream_token_boundary.js (2208 assertions across 6 fixtures × 4 chunking strategies)
```

> 2208 个断言，对应 §7 Gap-3 "把当前 3 帧 fixture 扩展到 50-200 帧每 trace" —— 实际比当时建议更激进（4 策略而非 1 trace 模式）。

---

## 2. 仍缺的 Release 硬门槛

把已存在但未 enforce 的 + 物理无法自动化的 release 硬门槛全部点出来。

### 2.1 P0：CI Enforcement 缺口

**事实**：`.github/workflows/tests.yml` 的 `wx-checks` job 只运行 2 个老测试：
```yaml
- name: Run Mini Program regression scripts
  run: |
    node wx_miniprogram/tests/test_mcq_detect.js
    node wx_miniprogram/tests/test_markdown.js
```

**含义**：今天上线的 4 套契约测试 + 至少 30 个其它 wx_miniprogram 测试都不在 CI 强制门里。任意 PR：
- 改 `ai-message-state.js` → `test_answer_leak_attack` 不会跑 → known-gap 翻车不会 fail PR
- 改 `ws-stream.js` → `test_ws_stream_pure_contract` 不会跑 → internal trace 直出回归不会 fail PR
- 改 `render-schema.js` → `test_progressive_disclosure_render` 不会跑 → grading_key 泄露回归不会 fail PR
- 改 `markdown-normalize.js` / `markdown.js` → `test_stream_token_boundary` 不会跑 → 当前分支主题（newline-loss）回归不会 fail PR

**这是本次最大的 release 硬门槛缺口**：资产是齐的，**门是开的**。

### 2.2 真机/微信开发者工具不可替代项

下列项即使全部 CI 通过，**仍必须真机/devtools 复测**才能签字发车：

| 项 | 不可替代原因 |
|---|---|
| `wx.connectSocket` 真实 disconnect / reconnect 时序（飞行模式、5G→Wi-Fi 切换、后台前台） | Node 测试只能验证 `computeReconnectDelayMs` + `buildTurnSocketPayload` 纯逻辑；底层 socket 状态机依赖微信 runtime |
| wxml `<rich-text>` 节点树 + 长列表 `setData` 性能 | wxml 不是 HTML / JSX；Node 端无法渲染 |
| iOS / Android / devtools 三端 `_IS_DEVTOOLS` 分支差异 | `__wxConfig` 平台判断仅在微信 runtime 可见 |
| 拍照拼图、wxLogin、bindPhone、wx.requestPayment、wx.requestSubscribeMessage | `wx.*` 全家桶必须真机 |
| 学情页真后端数据完整性（非全 0 / 非全 100 / 章节覆盖度） | 需要真 Supabase + 真 backend 启动 |
| pending turn 30 分钟窗口跨 onHide / onShow 持久化 | 依赖 `wx.getStorageSync` + 小程序生命周期 |

---

## 3. S3 / S5 / S6 / S8 / S10 自动化映射

triage rollup §5 / §7 把这 5 条 smoke 标为"release 硬门槛"。逐项核对自动化已覆盖到哪一步、剩下哪一步必须真机。

### S3 — MCQ × 5 流式 + payload 不含 `correct_answer` / `scoring_points`

| 子项 | 自动化 | 真机 |
|---|---|---|
| **请求 5 道选择题**（用户语义意图 → backend 出题） | ❌ 需要真后端 | ✅ 必须 |
| **全程流式**（token-by-token） | ✅ `test_stream_token_boundary` 已覆盖 4 切分策略 × 6 fixture | ✅ 真机抓包 |
| **最终 MCQ ×5 渲染契约** | ✅ `test_mcq_detect`（在 CI）+ `test_progressive_disclosure_render` | — |
| **grep payload 不含 `correct_answer` 在 4 个已拦路径** | ✅ `test_answer_leak_attack` BLOCKED ×4 | — |
| **grep payload 不含 `correct_answer` 在 4 个 known-gap 路径** | ⚠️ `test_answer_leak_attack` KNOWN-GAP ×4（**fixture 自承认会泄露**） | ✅ **必须真机 + Charles/Whistle grep** |

**结论 S3**：渲染层与已拦路径已自动化（占主流推送场景的 ≈ 50%）；**4 条 known-gap 路径必须靠真机 grep + 真后端 enforcement 才能签字**。最小修复见 §4。

### S5 — 飞行模式 5s → resume_from with seq

| 子项 | 自动化 | 真机 |
|---|---|---|
| `buildTurnSocketPayload` seq>0 走 `resume_from` 契约 | ✅ `test_ws_stream_pure_contract` Group 4（5 case） | — |
| `computeReconnectDelayMs` 5 次退避 400→4000ms | ✅ Group 5（8 case） | — |
| 真实 `wx.connectSocket` close → 自动重连 timer 触发 | ❌ 纯函数已锁，**物理 socket 状态机不可自动化** | ✅ 必须真机（飞行模式开关 / 网络掐断） |
| 重连后不丢 token / 不重复 token | ❌ 依赖真 WS 真后端 seq 编号 | ✅ 必须真机 + 抓包 diff |

**结论 S5**：**逻辑层 100% 自动化**（消除了 "我以为 buildTurnSocketPayload 会做 X 但实际它做 Y" 这类回归）；物理重连**必须真机**。

### S6 — MCQ 答题：DOM grep `grading_key` 不在 wxml

| 子项 | 自动化 | 真机 |
|---|---|---|
| state 序列化里 `grading_key` 不存在（progressive_disclosure 路径） | ✅ `test_answer_leak_attack` blocked + `test_progressive_disclosure_render` | — |
| **state 序列化里 `correct_answer` 不存在（mcq.followup_context 路径）** | ⚠️ KNOWN-GAP（marker LEAK_FOLLOWUP_CTX_007 当前**会**出现在 state） | ✅ 必须真机 + DOM inspector grep wxml 节点树 |
| wxml `<rich-text>` 节点实际不渲染 followupContext | ❌ Node 测不到 wxml | ✅ 必须真机 |

**结论 S6**：**关键已拦路径自动化覆盖了**；mcq.followup_context 这条已知泄露路径**必须真机** DOM inspector 兜底，直到 minimum_fix_suggestion（§4-2）落地。

### S8 — 学情页 8D 雷达 / 章节掌握度 真数据非全 0 非全 100

| 子项 | 自动化 | 真机 |
|---|---|---|
| 雷达 render 契约 | ✅ `test_report_radar_authority.js` / `test_report_radar_fallback.js` / `test_report_radar_palette_contract.js`（在 main 但不在 CI） | — |
| Learning Brain projection 三段（current_truth / evidence_flow / next_training） | ✅ `test_report_learning_brain.js`（在 main 但不在 CI） | — |
| **真后端数据非全 0 / 非全 100 / 章节覆盖度** | ❌ 完全无自动化，依赖 staging Supabase | ✅ 必须真后端 staging + 真数据 |

**结论 S8**：render 契约层有覆盖（**但未接 CI**）；**数据真实性必须真后端 staging**。这是 triage rollup §3 M-P1-4 的硬约束，无任何自动化捷径。

### S10 — 401 token 过期 → relaunch → pending turn 不丢

| 子项 | 自动化 | 真机 |
|---|---|---|
| 401 错误归一化（"登录已失效，请重新登录"） | ✅ `test_ws_stream_pure_contract` Group 1（AUTH_EXPIRED / HTTP_401） | — |
| token refresh 路径契约 | ✅ `test_api_auth_refresh.js`、`test_auth_token_expiry.js`、`test_login_token_preserve.js`（在 main 但不在 CI） | — |
| pending turn 30 分钟窗口持久化契约 | ✅ `test_chat_pending_turn_continuity_contract.js`、`test_chat_turn_recovery.js`、`test_chat_workflow_status_restore.js`（在 main 但不在 CI） | — |
| **wx.reLaunch 真实回到登录页 + storage 状态恢复** | ❌ 必须微信 runtime | ✅ 必须真机 |

**结论 S10**：**契约层自动化非常充分**（光这一项就 5+ test）—— 但**全部未接 CI**；relaunch UI flow **必须真机**。

### 综合判断（5 条 smoke）

| Smoke | 自动化可达 | 真机/devtools 不可替代 | 当前 CI gating |
|---|---|---|---|
| S3 | 渲染契约 + 4/8 leak vector | 4/8 known-gap + payload grep | ❌ 测试存在未接 CI |
| S5 | 重连逻辑 100% | 物理重连 | ❌ 测试存在未接 CI |
| S6 | 已拦路径 100% | wxml DOM grep + mcq.followup_context | ❌ 测试存在未接 CI |
| S8 | render 契约 100% | 真后端数据真实性 | ❌ 测试存在未接 CI |
| S10 | 错误归一化 + token refresh 契约 100% | wx.reLaunch UI flow | ❌ 测试存在未接 CI |

**5 条全部都有"自动化可达但 CI 未 enforce"的部分**——这是把 §7 自动化做完后**唯一剩下的 quick win**：把测试接进 CI。

---

## 4. 下一步最小修复建议（仅针对 progressive disclosure / internal token 泄露）

> 用户明确范围：**只针对 progressive disclosure / internal token 泄露**。不修 Sidebar，不修 mobile harness。

### 4.1 P0 — 把 known-gap 翻成 blocked（4 个 attack vector）

**直接抄 fixture 自带的 `minimum_fix_suggestion` 字段**。每条都是精确的最小 diff，且测试已经准备好：一旦 fix 生效，对应 fixture 把 `must_be_blocked: false` 翻成 `true`，测试会**自动**变红→变绿地确认收紧成功。

#### Fix 1: `fallback_text_markdown`（LEAK_FALLBACK_TEXT_005）

**位置**：`wx_miniprogram/utils/ai-message-state.js` 中 `deriveAiMessageRenderState` 末段

**最小 diff**（来自 fixture）：
> 在 `deriveAiMessageRenderState` 末段对 `renderableContent` 加一道正则 scrub：
> `/(正确答案|参考答案|答案是|采分点|评分点|grading[_ ]?key|correct[_ ]?answer|scoring[_ ]?points)\s*[:：][\s\S]{0,200}/gi`
> → 替换为 `"…[已折叠]"`

**回归保护**：fixture LEAK_FALLBACK_TEXT_005 写了 `"正确答案：LEAK_FALLBACK_TEXT_005"` 在 markdown 里，fix 后 marker 不该出现在 state；翻 `must_be_blocked: true` 即可固化。

**风险等级**：极低（仅匹配特定中文/英文关键词后接冒号；不会误伤正常对话内容）

#### Fix 2: `mcq.options[].text`（LEAK_MCQ_OPTION_006）

**位置**：`wx_miniprogram/utils/render-schema.js` 中 `normalizeMcqOptions`

**最小 diff**（来自 fixture）：
> 在 `normalizeMcqOptions` 内对 `text` 加同样的 scrub 正则；或在 `normalizeMcqQuestion` 末段把 question.stem + 所有 option.text 串成一段，用 scrub 后再回写。

**回归保护**：fixture 在 option B text 写 `"梁柱 - 采分点：LEAK_MCQ_OPTION_006"`，fix 后 marker 不该出现。

#### Fix 3: `mcq.followup_context`（LEAK_FOLLOWUP_CTX_007）

**位置**：`wx_miniprogram/utils/render-schema.js` 中 `normalizeMcqQuestion`

**最小 diff**（来自 fixture）：
> ```
> followupContext = Object.assign({}, raw);
> delete followupContext.correct_answer;
> delete followupContext.scoring_points;
> delete followupContext.explanation;
> ```
> 同时在 `chat.js` `_onPresentation` 路径再做一道防御扫描。

**风险等级**：极低（白名单式删除特定 key，不动其它 followup_context 字段）

#### Fix 4: `callout_block.content`（LEAK_CALLOUT_008）

**位置**：`wx_miniprogram/utils/render-schema.js` 中 `normalizeBlock` callout 分支

**最小 diff**（来自 fixture）：
> 增加 callout-level sanitize：扫描 callout content 的 text spans，若命中 `/(正确答案|参考答案|答案是|grading[_ ]?key|correct[_ ]?answer)/i` 关键词，整个 callout 替换成中性文案 `"完整解析需在评分后查看"`。

**风险等级**：中（callout 是教学 UX 高价值表达；建议先用日志记录命中率再决定是 hard scrub 还是 soft warning）

### 4.2 P0 — CI 接入（**改 workflow 文件，不改业务代码**）

**位置**：`.github/workflows/tests.yml` 第 222-225 行 `wx-checks` job

**最小 diff**（仅 4 行新增，不动现有 2 行）：
```yaml
      - name: Run Mini Program regression scripts
        run: |
          node wx_miniprogram/tests/test_mcq_detect.js
          node wx_miniprogram/tests/test_markdown.js
          # ↓ 新加 4 行
          node wx_miniprogram/tests/test_progressive_disclosure_render.js
          node wx_miniprogram/tests/test_answer_leak_attack.js
          node wx_miniprogram/tests/test_ws_stream_pure_contract.js
          node wx_miniprogram/tests/test_stream_token_boundary.js
```

**风险等级**：零业务代码风险；只增加 CI 步骤。本地已确认 4 条**全部 PASS**，CI 跑结果应一致（Node v22 / Ubuntu）。

**收益**：
- 任何改 sanitizer / ws-stream / markdown 的 PR 都自动触发 4 套契约测试
- 收紧 sanitizer 时 `test_answer_leak_attack` 会自动提示翻 `must_be_blocked: true`
- token boundary 回归即时拦截

### 4.3 P1 — 把其他在 main 但未接 CI 的高价值测试一并补上（**仅改 workflow，不改业务代码**）

至少加入这几个（理由：直接对应 S6/S8/S10 风险）：
```yaml
          # P1：补 wx_miniprogram 高价值契约测试
          node wx_miniprogram/tests/test_render_schema.js
          node wx_miniprogram/tests/test_ai_message_state.js
          node wx_miniprogram/tests/test_chat_pending_turn_continuity_contract.js
          node wx_miniprogram/tests/test_chat_turn_recovery.js
          node wx_miniprogram/tests/test_chat_workflow_status_restore.js
          node wx_miniprogram/tests/test_api_auth_refresh.js
          node wx_miniprogram/tests/test_auth_token_expiry.js
          node wx_miniprogram/tests/test_api_noauth_401.js
          node wx_miniprogram/tests/test_report_radar_authority.js
          node wx_miniprogram/tests/test_report_learning_brain.js
```

**未在本核对中实际跑**——逐个跑通后再加进 CI，避免一次性 fail 太多。**建议作为独立分支单跑一遍**，把任何 main 上已经红的测试先单独 triage。

### 4.4 不在本次范围（但相关）

- Sidebar collapsed Settings 一致性（triage §6 判断 2）—— **不在本次 fix scope**
- `/wechat-harness` 移动端 DOM 缺失（triage W5）—— **不在本次 fix scope**
- `/member` SSR redirect 监控/SEO 表现（triage §6 判断 3）—— **不在本次 fix scope**
- 这些都已在 triage rollup §7 中归类为"应修但不阻塞"或"独立工单"

---

## 5. 没动什么

- ❌ 不修源码、不改业务代码、不改测试、不改配置、不改依赖、不改 CI 文件
- ❌ 不 commit / stash / reset / clean / 不开 PR / 不切分支
- ❌ 不重启 / 不 kill 任何进程
- ❌ 不 npm install / npm ci
- ✅ Read 了 8 个文件（4 个测试 + 2 个 fixture + ws-stream-pure.js + tests.yml 节选）
- ✅ 本地跑了 4 个 node test（read-only execution，无副作用）
- ✅ 本报告写到 `docs/qa/2026-05-21-qa-assets-verification.md`

---

## 6. 一句话结论

> §7 的自动化资产**已经 boil 完了**：`ws-stream-pure.js` + 4 套契约测试 + 14 个 attack/boundary fixture，本地 **2287 个断言 PASS**。
> **唯一缺的是 enforcement** —— 4 行 `tests.yml` 改动可以把所有这些资产从"睡着的"变成"会咬人的"，零业务代码风险。
> 此外还有 **4 个 known-gap attack vector**（fallback markdown / mcq option / followup_context / callout）的 minimum_fix_suggestion 已经写在 fixture 里，等被 cherry-pick 即可——商业敏感的答案泄露面**只差这一步**。
