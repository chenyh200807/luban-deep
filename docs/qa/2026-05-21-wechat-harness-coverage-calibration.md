# Web harness vs 微信小程序真实入口 — 覆盖校准

| Field | Value |
|---|---|
| Date | 2026-05-21 |
| Mode | 只读调查（无 edit / commit / PR） |
| Scope | `web/app/wechat-harness/*` + `web/lib/wechat-harness-*` ↔ `wx_miniprogram/pages/chat/*` + `wx_miniprogram/utils/{ai-message-state,render-schema,api,endpoints,ws-stream}.js` |
| Prior | `docs/qa/2026-05-21-wechat-harness.md`、`docs/qa/2026-05-21-wechat-harness-rerun.md` |

---

## 0. 一句话结论

> Web harness 真正测的是**渲染决策契约**（block schema、MCQ 卡片、teaching fallback、progressive disclosure 防泄露），**不是**小程序的真实运行时。它能代表的小程序场景约 **15–25%**，**95% 是严重高估**。

---

## 1. 谁是真共享，谁只是 Web fixture

| Layer | 共享方式 | 证据 |
|---|---|---|
| **`wx_miniprogram/utils/render-schema.js`**（518 行） | **物理共享**：harness 通过 Node `createRequire` 直接 `require()` 小程序 JS 文件 | `web/lib/wechat-harness-data.ts:38-44` |
| **`wx_miniprogram/utils/ai-message-state.js`**（441 行） | 同上，**物理共享** | `web/lib/wechat-harness-data.ts:38-44` |
| **`wx_miniprogram/utils/markdown.js`**（510 行） | 传递性共享（被 ai-message-state require） | `ai-message-state.js:2` |
| **`wx_miniprogram/utils/mcq-detect.js`**（410 行） | 传递性共享 | `ai-message-state.js:3` |
| **`wx_miniprogram/utils/markdown-normalize.js`**（130 行） | 传递性共享 | `ai-message-state.js:4` |
| **`tests/fixtures/wechat_*.json`**（16 cases） | 物理共享 fixture | `wechat-harness-data.ts:208-215` |
| **`wx_miniprogram/utils/api.js`**（628 行） | **不共享** | 含 `wx.request`、`wx.reLaunch` |
| **`wx_miniprogram/utils/ws-stream.js`**（484 行） | **不共享** | 用 `wx.connectSocket`、读 `wx.*` 状态 |
| **`wx_miniprogram/utils/endpoints.js`**（123 行） | **不共享** | `__wxConfig` 平台检测 |
| **`wx_miniprogram/utils/auth.js`**（152 行） | **不共享** | `wx.getStorageSync`、`wx.setStorage` |
| **`wx_miniprogram/utils/helpers.js`**（180 行） | **不共享** | 含 `wx.*` getSystemInfo / vibrate |
| **`wx_miniprogram/utils/workflow-status.js`**（522 行） | **不共享**（harness 也不 require） | — |
| **`wx_miniprogram/utils/citation-format.js`**（135 行） | 理论可共享但 harness **未 require** | — |
| **`wx_miniprogram/utils/chat-turn-recovery.js`**（113 行） | 理论可共享但 harness **未 require** | — |
| **`wx_miniprogram/pages/chat/chat.js`**（2789 行） | **不共享** | wx.* 重度依赖 + UI 编排 + 生命周期 + setData |
| **`wx_miniprogram/pages/chat/chat.wxml`**（38KB） | **物理不可共享** | 微信小程序 markup，非 JSX/HTML |
| **`wx_miniprogram/pages/chat/chat.wxss`**（73KB） | **物理不可共享** | 微信小程序 style，非 CSS |
| **`web/app/wechat-harness/WechatHarnessClient.tsx`**（800 行） | Web-only React 客户端 | 用 lucide-react + MarkdownRenderer 渲染 fixture |

**LOC 视角**：
- 真共享业务代码 ≈ **2000 行 JS**
- 小程序独有业务代码 ≈ **5400 行 JS** + **111KB wxml/wxss**
- 共享比例：**~27% by LOC**

---

## 2. 覆盖矩阵

每行 = 一个用户可见或可观测的行为。

> 评分图例：✅=harness 覆盖；⚠️=harness 部分覆盖；❌=harness 不覆盖；🔁=共享同一逻辑；🪜=有 fixture/部分契约但运行时不同。

| # | 场景 | Harness 覆盖 | 小程序必须单独测 | 共享同一逻辑? | 风险 | 推荐补强 |
|---|---|---|---|---|---|---|
| 1 | Markdown 换行 / 段落 / 列表渲染 | ✅ 16/16 fixture | 视觉 / 长内容 | 🔁 markdown.js + ai-message-state | **低** | 加入更多 stream-edge fixture |
| 2 | 表格 / 公式 / 图表 / steps / recap 五类 structured block 渲染 | ✅ 5 fixture | 视觉 / mobileStrategy=scroll/compact_cards 切换 | 🔁 render-schema.normalizeBlock | 低 | wxml 视觉 baseline |
| 3 | MCQ 题卡识别 + 选项归一化 + 受理回执 | ✅ schema 层 | 真用户点选 → 提交 → 反馈 | 🔁 normalizeMcqOptions + createMcqBlock | 中 | 加 mcq-submit 真接口契约测 |
| 4 | progressive disclosure 防泄露（grading_key/correct_answer/scoring_points/explanation 必须剥离） | ✅ `sanitizeProgressiveDisclosure` 函数本身 | **真 WS payload 走相同路径** + 防 fallback markdown 里漏 | 🔁 render-schema.js:458 `_HIDDEN_DISCLOSURE_KEYS` | **高** | negative-case fixture（带 grading_key 的恶意 payload）+ chat.js 真链路验证 |
| 5 | DSML / tool call / API key / read_file 等内部 token 不暴露给用户 | ✅ `coerceUserVisibleContent` + `INTERNAL_PATTERNS` | 同 #4 | 🔁 ai-message-state.js:8-27 | **高** | 加 negative fixture（含真实内部 trace 样本）|
| 6 | teaching fallback：当 MCQ + 教学正文混排，识别采分点/易错点/口诀等 callout | ✅ `parseTeachingFallbackBlocks` + `hasTeachingSemanticFallback` | wxml callout 渲染 | 🔁 ai-message-state.js:268-306 | 中 | 视觉回归 |
| 7 | final stream state ↔ history hydrate parity（流式终态 = 重进对话后恢复态）| ✅ `compareFinalAndHistory` 跑过 16/16 | wxml setData 后 rich-text 节点重建 | 🔁 但只比较 schema，不比较 wxml 节点树 | 中 | wxml node-tree snapshot |
| 8 | **WebSocket 连接 + heartbeat + reconnect 指数退避（5 attempts, 400→4000ms）** | ❌ | **必须真机** | ❌ ws-stream.js 100% miniprogram-only | **极高** | 抽出 ws-stream 纯函数到 `tests/contracts/`，stream trace replay |
| 9 | **WebSocket resume_from with seq（断连后从上一个 seq 续传）** | ❌ | 必须 | ❌ `buildTurnSocketPayload` 在 ws-stream.js 内 | **极高** | 同上 |
| 10 | **WebSocket 事件分类：thinking / progress / observation / stage_start / tool_call / tool_result + visibility public vs internal** | ❌ | 必须 | ❌ `buildStatusEvent` + `resolveEventVisibility` 在 ws-stream.js 内 | 高 | 同上 |
| 11 | **WebSocket 错误归一化（HEARTBEAT / DataInspectionFailed / api key / traceback → "服务暂时不可用"）** | ❌ | 必须 | ❌ `normalizeErrorMessage` 仅在 ws-stream.js | 高 | 抽出纯函数测 |
| 12 | **HTTP API base candidate fallback（:8001 → :8012 → 远端）** | ❌ | 必须 | ❌ endpoints.js + api.js 100% miniprogram-only | 中 | mock 多 base + stub wx.request |
| 13 | **HTTP 401 → 自动 refresh token / 失败 → relaunch login** | ❌ | 必须 | ❌ api.js:71-123 | **高** | mock auth flow test |
| 14 | **HTTP 429 → "操作过于频繁" 文案** | ⚠️ 仅一个 surface fixture "Billing Quota Exceeded" | 真 backend 触发的 429 | 🪜 文案 fixture 共享，但触发路径不同 | 中 | 加 429 真路径 e2e |
| 15 | **HTTP 503 → FEATURE_DISABLED 文案** | ❌ | 必须 | ❌ api.js:264-269 | 中 | mock 503 test |
| 16 | **5xx 幂等重试（GET/PUT/DELETE，2 次指数退避）** | ❌ | 必须 | ❌ api.js:271-297 | 中 | stub wx.request 模拟 5xx 序列 |
| 17 | **pending turn 持久化 / 30 分钟内重连恢复** | ❌ | 必须 | ❌ chat.js:42-60 + chat-turn-recovery.js | 高 | 难以契约化，建议真机 + storage e2e |
| 18 | **conversation list 拉取 / 创建 / 归档 / 删除** | ❌ | 必须 | ❌ api.js:471-520 | 中 | mock backend 契约测 |
| 19 | **learning-brain projection / mobile/learning-report 渲染** | ⚠️ 仅 client-side state JSON 输出，**未真打后端** | 必须真后端 | ❌ 数据获取链路不共享，render 决策共享 | **高**（学情数据真实性是产品核心）| 真后端 + Supabase 集成测 |
| 20 | **MCQ submit → /api/v1/sessions/:id/messages/:mid/feedback 回写** | ❌ | 必须 | ❌ api.js:548-565 | 中 | mock + 真链路 |
| 21 | **assessment 摸底测试 create / submit 流程** | ❌ | 必须 | ❌ api.js:573-593 | 中 | 真后端 e2e |
| 22 | **首次微信小程序登录 wxLogin + bindPhone** | ❌ | 必须 | ❌ api.js:359-377 | 高 | 真机（开发者工具 mock）|
| 23 | **小程序 onLoad / onShow / onHide / onShareAppMessage 生命周期** | ❌ | 必须 | ❌ chat.js 内 | 中 | 真机 |
| 24 | **wxml `<rich-text>` 节点数组渲染 + 长列表 setData 性能** | ❌ | 必须 | ❌ wxml + chat.js setData | 中 | 真机性能 baseline |
| 25 | **iOS / Android / devtools 三端差异（特别是 `_IS_DEVTOOLS` 分支）** | ❌ | 必须 | ❌ | 中 | 真机三端回归 |
| 26 | **billing quota / wallet / ledger / checkout 完整链路** | ⚠️ 一个 surface fixture | 必须 | ❌ api.js:399, 522-544 | **高**（商业化） | mock + 真接口 |
| 27 | **Hero 区域拖拽（HERO_MAX_DRAG_PX=84 / 阻尼 0.32 / 震动阈值 40）** | ❌ | 必须 | ❌ chat.js:23-25 | 低 | 真机交互 |
| 28 | **markdown 流式 token 边界换行丢失（当前分支主题 `fix/markdown-streaming-render-newline-loss`）** | ⚠️ 通过 `buildStreamFrames` 模拟三帧（first line / first half / final），不是真 token-by-token | 真 WS 推流的 token 边界 | 🔁 markdown.js + markdown-normalize.js | **高** | 加细粒度 token-by-token fixture，token 数 ≥ 50 帧 |
| 29 | **citation-format / citation rendering** | ❌（harness 未 require citation-format.js） | 必须 | 理论可共享 | 中 | harness 加 fixture |
| 30 | **history tombstone（已删对话不再出现）** | ❌ | 必须 | ❌ history-tombstone.js | 低 | storage e2e |

---

## 3. Web harness 可信覆盖率估计

**按用户场景权重加权**：

| 场景大类 | 用户场景权重 | Harness 覆盖比例 | 贡献 |
|---|---:|---:|---:|
| 发送一条消息（含流式 + markdown 渲染）| 25% | 渲染最终态 30% / 实时流式 10% | **6%** |
| 流式渲染过程（token 边界、throttle、重排） | 15% | 40% | **6%** |
| MCQ 题卡交互 | 10% | schema 100% / 提交 0% / 反馈 0% | **3%** |
| 多轮 follow-up 上下文 | 10% | 0% | **0%** |
| 学情 / 报告页 | 10% | 0% | **0%** |
| 断线重连 / resume | 5% | 0% | **0%** |
| 认证 / 登录态过期 | 5% | 0% | **0%** |
| billing / quota / 升级 | 5% | 1 fixture，30% 文案 | **1.5%** |
| 错误页 / 网络失败文案 | 5% | 2 fixture，30% | **1.5%** |
| wxml 渲染层 / 长列表性能 | 5% | 0%（视觉层完全不共享） | **0%** |
| 首次进入 / 生命周期 | 5% | 0% | **0%** |
| **合计** | **100%** | | **≈ 18%** |

**真实可信覆盖率：15–25%**（区间反映场景权重的不确定性）。

> 上一轮 QA 报告里写的 "PARITY 16/16 通过" 是**渲染契约层**的 100%，不是用户场景层的。这两个指标常被混用。
> **harness 是好的 schema regression guard，不是好的端到端覆盖代表。**

---

## 4. 小程序独有风险清单（harness 不覆盖、最容易引入回归）

按"出问题概率 × 用户影响"排序：

| 排名 | 风险 | 触发场景 | 当前防护 |
|---:|---|---|---|
| 1 | **WS reconnect / resume 错位** | 用户网络抖动 / 5G→Wi-Fi 切换 / 后台前台切换 | ws-stream.js 自测，无契约 test |
| 2 | **流式 token 边界换行丢失**（当前分支主题）| chunk 在换行符上切断 | harness 三帧 fixture 已存在，但 token 数太少 |
| 3 | **progressive_disclosure 答案泄露** | 后端 payload 含 grading_key / correct_answer | render-schema.js sanitize 在，但**只在 progressive_disclosure 路径**；如果 backend 把答案塞进 fallback markdown / MCQ option text，**绕过 sanitize** |
| 4 | **学情页假满分 / 假进度** | learning-report API 返回为空 / 错位 | 无 harness 覆盖；真后端必须返回真数据，否则用户看到"100% 掌握"误导 |
| 5 | **401 处理错位**（token 过期但不 relaunch / relaunch 但丢失 pending turn）| token TTL 临期 | api.js + chat.js 各处都有 401 handling，分散，无契约 test |
| 6 | **DSML / 内部 token / tool call 泄露给用户** | LLM 偶发吐出 system prompt fragment | `INTERNAL_PATTERNS` 在 ai-message-state.js:8-15，**只匹配 6 种 pattern**，未来新出现的内部 token 类型会漏 |
| 7 | **pending turn 重连丢失**（30 分钟窗口内退出 → 重进，turn 状态丢失或重复显示）| 用户关闭小程序在后台 | chat.js pending turn polling，未契约化 |
| 8 | **多基地址 fallback 卡死**（:8001 down → :8012 也 down → 远端也 down，但已经重试 5 次）| 本地开发偶发 / develop 环境 | endpoints.js fallback 顺序，无 test |
| 9 | **wxml long list setData 卡顿**（MAX_MESSAGES=200，但单条消息含大量 blocks）| 长对话历史 | 性能分级（FLUSH_THROTTLE_MS / MD_PARSE_INTERVAL）做了节流，但无 perf budget test |
| 10 | **iOS / Android / devtools 三端 _IS_DEVTOOLS 分支不一致** | 仅在三端不同设备触发 | 真机回归依赖人手 |
| 11 | **citation 引用渲染层错位**（小程序 rich-text 节点和 web 不一致） | 后端返回 citations | harness 不 require citation-format.js |
| 12 | **wallet / 积分不够时的 503 / FEATURE_DISABLED 文案被吞** | 真实用户额度耗尽 | 仅一个 fixture 覆盖文案，未覆盖触发路径 |

---

## 5. 最小 15 个 release smoke scenarios

每条都是真机或真后端必须跑的 happy / failure path，**harness 替代不了**。

| # | 场景 | 通过判定 | 必走 |
|---:|---|---|---|
| S1 | 首次安装 + wxLogin + bindPhone 完整 | profile 页能拉到 user_id + phone | 真机 |
| S2 | 已登录用户 onShow 进入聊天 → conversation list ≤ 1.5s 出现 | UI 出现 + 0 console error | 真机 |
| S3 | 发送 "请给我来 5 道选择题不要提前给答案" → 流式 token 实时 → 最终态 MCQ × 5 + 无答案/采分点暴露 | grep payload 不含 correct_answer / scoring_points | 真机 + Charles/Whistle 抓包 |
| S4 | 流式中途切后台 30 秒 → 回前台 → 流式自动 resume（不重新开 turn）| seq 接续，无重复 token | 真机 |
| S5 | 流式中途断网 5 秒 → 自动重连 → resume_from with seq → 不丢 token / 不重复 | 重连日志命中 RECONNECT_BASE_DELAY 退避 | 真机 + 飞行模式开关 |
| S6 | MCQ 答题：点 A → 提交 → 反馈消息 + 解析展开 + grading_key 不在 wxml DOM | DOM inspector grep | 真机 |
| S7 | follow-up "为什么 C 错"：上一轮 MCQ 上下文带入下一轮 start-turn | request body 含 followup_context.question_id | 真机 + 抓包 |
| S8 | 学情页：8D 雷达 + 章节掌握度 + 易错点 + 复习预报真数据（非全 0 / 非全 100）| 数值在合理区间 | 真后端 staging |
| S9 | Learning Brain projection：current_truth / evidence_flow / next_training 三段渲染，event_count > 0 | UI 三段都有内容 | 真后端 staging |
| S10 | 401 token 过期 → 自动跳登录页 → 重新登录 → 回到原对话（pending turn 不丢） | 流式继续 | 真机 + token TTL 测试桩 |
| S11 | 429 quota exceeded → "今日额度已用完" 文案 + 升级按钮 | 文案匹配 fixture | 真机或 stub backend |
| S12 | 503 FEATURE_DISABLED → 灰显该功能 + 不阻塞其他功能 | 其它 endpoint 仍可用 | mock backend |
| S13 | 网络抖动：5xx 在 GET 上自动重试 2 次，POST 不重试 | 日志命中 retry，且 POST 只发 1 次 | mock backend |
| S14 | 长对话（150+ 消息）滚动到顶部，setData 帧率不掉到 30fps 以下 | 性能 panel | 真机 + 性能 baseline |
| S15 | iOS + Android + devtools 三端跑同一份 stream trace fixture，wxml 节点树 + visible_blocks 一致 | snapshot diff | wechat-devtools-cli + 真机 |

---

## 6. 哪些逻辑应该下沉成 shared contract tests

**已经下沉（harness 形式）**：
- render-schema.js → fixture replay × 16 case
- ai-message-state.js → fixture replay × 16 case
- markdown.js / mcq-detect.js / markdown-normalize.js → 传递性覆盖

**应该但目前没下沉**（建议加 `tests/contracts/` 目录或扩展 harness）：

| 模块 | 抽出的纯函数 | 测什么 | 失败影响 |
|---|---|---|---|
| `ws-stream.js` | `normalizeErrorMessage`、`resolveEventVisibility`、`buildStatusEvent`、`buildTurnSocketPayload`、`computeReconnectDelayMs` | 错误归一化、visibility 过滤、resume payload、退避公式 | 极高（用户看到内部 trace / 重连失败） |
| `api.js` | `unwrapResponse`、`applyAuthPayload`、`createHttpError`（retry 决策抽参数化）| 401/429/503/5xx 文案与 retry 决策 | 高 |
| `endpoints.js` | `getBaseUrlCandidates`、`toSocketBaseUrl`、`getSocketUrlCandidates` | base order、wss 转换 | 中 |
| `auth.js` | `shouldRefreshToken`、token TTL 计算 | 401 自动 refresh 时机 | 中 |
| `chat-turn-recovery.js` | pending turn 序列化 / 反序列化 | 30 分钟窗口逻辑 | 中 |
| `citation-format.js` | citation 节点生成 | rich-text 节点 schema | 低 |

**下沉原则**：所有不依赖 `wx.*` 的纯逻辑都应该单独可测。当前 `ws-stream.js` 把纯函数和 `wx.connectSocket` 副作用混在一个 module，这是最大的契约盲区。

---

## 7. 下一轮如果要修，先修这 3 个覆盖缺口

按 **(风险 × 用户影响) / 实现成本** 排序：

### Gap-1: WS 流式行为契约测试（最高优先级）
- **现状**：`ws-stream.js` 484 行，0 个 unit test，每次发布靠真机点
- **风险**：reconnect / resume / 事件 visibility / 错误归一化任一处出回归，用户体验是断流、重复 token、看到内部错误堆栈
- **最小动作**：
  1. 把 `ws-stream.js` 内**所有不调 `wx.connectSocket` 的函数**抽到 `wx_miniprogram/utils/ws-stream-pure.js`（约 200 行，含 buildStatusEvent / buildTurnSocketPayload / normalizeErrorMessage / resolveEventVisibility / computeReconnectDelayMs）
  2. 新增 `tests/contracts/ws_stream_pure.test.js`：fixture 是真实生产 WS trace 的 JSONL 录制（5-10 条），逐事件喂入，验证输出 normalized event
  3. 在 harness 加一个 tab："stream trace replay"，从 JSONL 喂进 ai-message-state 一帧一帧推
- **改动量**：~300 LOC（其中改业务代码 ~50 LOC，提取函数；新增 test ~250 LOC）
- **回报**：把当前 0% → ~60% ws 覆盖；把 Smoke S4 / S5 / S10 的真机依赖降低

### Gap-2: 防答案泄露的 negative-case contract test（高优先级）
- **现状**：`sanitizeProgressiveDisclosure` 函数本身有 unit test 价值，但**只测了 happy path**（fixture 都是清洁数据）。如果后端 future 把 `correct_answer` 塞到 `fallback_text` markdown 里（不走 progressive_disclosure 路径），**当前 sanitize 拦不住**
- **风险**：商业敏感 — 答案泄露会被竞品截图传播
- **最小动作**：
  1. 在 `tests/fixtures/wechat_progressive_disclosure_attack_cases.json` 加 5-10 个 negative fixture：
     - payload 含 grading_key 在 progressive_disclosure.sections（应被剥）
     - payload 含 correct_answer 在 fallback_text markdown（**当前会泄露**）
     - payload 含 scoring_points 在 MCQ option text（**当前会泄露**）
     - payload 含 explanation 在 callout block（**当前会泄露**）
  2. 在 harness 加 "negative cases" 视图，红色标记泄露
  3. 在 `render-schema.js` 扩展 `_HIDDEN_DISCLOSURE_KEYS` 检查到 fallback / mcq option / callout 三个路径（**这是改业务代码，需用户授权**）
- **改动量**：~150 LOC fixture + ~30 LOC test infra；如果接受扩展 sanitize 业务代码，再 +50 LOC
- **回报**：把 high-stakes 泄露风险从"靠 backend 自律"→"前端硬拦"

### Gap-3: 流式 token 边界细粒度 fixture（高优先级，当前分支直接相关）
- **现状**：`buildStreamFrames` 只生成 3 帧：first visible line / first half / final。**完全测不到 token-by-token 边界**——当前分支 `fix/markdown-streaming-render-newline-loss` 修的就是 token 边界问题
- **风险**：本轮修复的回归会重现，且 harness 测不出
- **最小动作**：
  1. 把生产 WS trace 录 10 个真实 stream（不同长度 + 含 markdown 边界 / MCQ 边界 / 公式边界）
  2. 在 `web/lib/wechat-harness-data.ts` 增加 "real-stream-trace" 模式：按 50-200 帧逐 chunk 喂 `deriveAiMessageRenderState`，**每帧都比对 `renderableContent` 不丢失换行**
  3. harness UI 加 "token boundary stress" 面板，hover 任一帧看 diff
- **改动量**：~80 LOC harness data + ~200 LOC fixture（trace JSONL）
- **回报**：当前分支主题的回归保险；token 边界相关的所有未来修改都有自动验证

---

## 8. 没动什么

- ❌ 业务代码、测试代码、配置、依赖文件、`.env` 都没改
- ❌ 没 commit / stash / reset / clean / 开 PR / 切分支
- ❌ 没启动新进程；环境恢复阶段起的 FastAPI / Next dev 仍按上一轮状态
- ✅ 只 Read 了上面列出的文件
- ✅ 本报告写到 `docs/qa/` 下，与现有 QA 报告同目录
