# Luban Learning Report Read Model Execution Plan

> Status: **Local Acceptance Gate Passed — Pending Production Observation (2026-05-20)** — Open Gaps G1-G7 已在本批次代码 + 测试中关闭（详见 §Open Gaps），本地 API + 微信开发者工具 CLI 验收已通过（详见 §Local Acceptance Evidence），但 §定量删除门槛 还未启动观察期。在 Langfuse / access log 证据满足之前，状态不得推进到 `Done`，旧 5 个 deprecated 接口也不得删除。
>
> Owner: Luban Learning Brain 主线（参见 `docs/plan/INDEX.md` §2 Learner State / Memory / Overlay）。
>
> Related：
> - PRD：`docs/plan/2026-05-18-luban-learning-brain-gbrain-absorption-prd.md`
> - Implementation：`docs/plan/2026-05-18-luban-learning-brain-gbrain-absorption-implementation-plan.md`
> - Retrieval：`docs/plan/2026-05-18-deeptutor-learning-fact-retrieval-implementation-plan.md`
> - Authority discipline：`AGENTS.md` §0 / §5.6 / §5.7 Single Authority Hard Gate

---

## 目标

把微信小程序"学情"页从多接口拼装，收敛为一个**可审查、可测试、可观测的** `learning-report-read-model`，并把"近 3 天完成数 / 今日进度 / 掌握度 / Learning Brain / 下一步训练"这些业务事实的 authority 落点写死到代码与契约里。

本计划只做读模型收权：
- 不新增第二套学习记忆。
- 不改变阅卷写入链路（`construction_grading` 的事件 schema/时序保持原样）。
- 不删除旧接口；旧接口降级为 read-model 内部输入源 + 后台兼容面。

## 非目标

- 不重做阅卷链路；不改变 `construction_grading` 写入事件的时机和 schema。
- 不把 Learning Brain projection 当作"今日进度 / 总体掌握度"的替代来源。
- 不在前端通过多接口兜底重新推导学情事实。
- 不在本阶段删除旧接口；旧接口只降级为 read-model 输入源和后台兼容面，删除条件在 §定量删除门槛 中明确。
- 不新增独立 learner profile 存储；学生画像仍由 evidence ledger、compiled truth、人工修正和旧 mastery 输入共同支撑。
- 不在本计划解决跨 surface（小程序 / WebView / 管理端）的读法漂移问题；本计划只锁两个壳层：`wx_miniprogram` 与 `yousenwebview/packageDeeptutor`。

## 单一 Authority

| 业务事实 | 唯一 authority | 说明 |
| --- | --- | --- |
| 练习完成数、近 3 天完成数、今日进度 | `learner_memory_events` 中 `source_feature=construction_grading` 且 `memory_kind=learning_evidence` 的事件，按 **attempt 计数** | 完成数按批改尝试 attempt 计数；同题二刷算 2 次。`unique_question_*` 单独输出。聊天总结、旧 `daily_practice_counts`、前端缓存都不能决定完成数 |
| Learning Brain 当前可信结论、证据流、下一步训练 | `LearnerStateService.read_compiled_learning_truth`，缺失时由同一事件 ledger 做只读 `dry_run` 合成 | 页面刷新可以看到刚批改事件；夜间 synthesis 仍是持久 projection 的主路径 |
| 诊断维度 / 掌握度展示 | `learning-report-read-model` 聚合现有 `assessment_profile` / `mastery_dashboard` 读法 | 旧接口是输入源，不再由页面直接决策 |
| 学情页最终展示（小程序 + WebView 双壳层） | `GET /api/v1/mobile/learning-report` | `wx_miniprogram` 与 `yousenwebview/packageDeeptutor` 都只消费这一份 read model |
| 输入源健康状态 | `learning-report-read-model.source_status` + `degraded` + `degraded_sources` | 任一输入源失败必须显式进入 `degraded=true / degraded_sources / source_status`，**禁止 try/except 静默吞掉** |
| 无效时间戳 evidence | `learning-report-read-model.freshness.unknown_date_count` | 无法解析 `created_at` 的事件不得默认算入今天；必须计入 `unknown_date_count` |

---

## 关键口径

### 完成数 attempt 口径（硬约束）

`今日进度 / 近 3 天完成 / attempt_count` **必须**按 evidence 事件数计数，**不按 `question_id` 去重**：

- 同一道题今天做两次 → 显示 **2 次练习**。
- 同一批 case 批改写入多条 `learning_evidence` → 按写入事件数累加。
- 缺少合法 `created_at` 的事件 → 不计入任何日 bucket，进入 `unknown_date_count`，不污染今日进度。

**唯一题数**只作为辅助解释字段，与 attempt 口径并列暴露：

- `overview.attempt_count`：所有窗口范围内的 attempt 总数。
- `overview.today_done`：今日 attempt 数。
- `overview.recent_three_done`：近 3 天 attempt 数。
- `overview.unique_question_count`：所有窗口内不同 `question_id` 数。
- `overview.today_unique_questions`：今日不同 `question_id` 数。
- `overview.recent_three_unique_questions`：近 3 天不同 `question_id` 数。

> ⚠️ **常见反模式**：用 `set(question_id) -> len()` 当作"完成数"。这把同题二刷折叠成 1，与本计划及 §单一 Authority 表直接冲突。任何 PR 引入此模式必须被 review 拦下。

### 时间戳与窗口

- 单一时区：`Asia/Shanghai (UTC+8)`，所有日 bucket 用 `+08:00` 取整。
- `created_at` 解析失败 → `unknown_date_count += 1`，不进任何 `daily_counts`。
- `daily_counts` 的 key 必须是 `YYYY-MM-DD`，不允许 `__unknown__` 之类的占位混进近 3 天窗口。

### `event_limit` 与窗口可证关系

- 默认 `event_limit=100`，hard cap 500。
- 后端必须保证在 `event_limit` 限制下仍能完整覆盖"近 3 天"窗口。实现路径二选一：
  1. **首选**：后端按时间窗口拉取（`created_at >= now-3d`），同时保留 `event_limit` 仅作为安全上限。
  2. **临时**：维持 `LIMIT N`，但必须在 freshness 中暴露 `window_truncated=true` 当 evidence 数达到 limit；前端检测到 `window_truncated` 必须标记 degraded。
- 任何"近 3 天"统计在 `window_truncated=true` 时**不得**对外宣称完整。

### 掌握度口径

掌握度不是 `正确数 / 做题数`。本阶段保守聚合已有 `mastery_dashboard` / `assessment_profile`，但必须满足：

- 无 evidence 时不显示"100% 掌握"。
- 单章做对一题不能推导全局 100%。
- 章节 mastery 与全局 mastery 分开展示；全局 mastery 只能来自明确的 mastery authority 或按章节覆盖度加权。
- 若 mastery 输入源降级，页面可显示 evidence-driven 进度和 Learning Brain，但必须标记 `degraded`。

### Learning Brain 口径

Learning Brain 只回答三件事：

- 当前可信结论：从 compiled truth 或 dry-run synthesis 生成。
- 证据流：必须能追溯到 `learning_evidence` event / trace / RAG / 人工修正。
- 下一步训练：由错因、薄弱点和 typed graph 推导，不由前端拼文案。

它**不负责**决定今日完成数、**不负责**直接覆盖全局掌握度。

---

## 数据契约（Response Schema v1）

`GET /api/v1/mobile/learning-report` 返回 envelope：

```jsonc
{
  "ok": true,
  "user_id": "<authenticated user id>",
  "schema_version": 1,
  "authority": {
    "read_model": "learning-report-read-model",
    "progress_source": "learner_memory_events.learning_evidence",
    "learning_brain_source": "compiled_learning_truth" | "dry_run_learning_evidence",
    "deprecated_page_sources": [
      "/api/v1/practice/today-progress",
      "/api/v1/homepage/dashboard",
      "/api/v1/assessment/profile",
      "/api/v1/plan/mastery-dashboard",
      "/api/v1/learning-brain/projection"
    ]
  },
  "degraded": false,
  "degraded_sources": [],          // string[]，与 source_status 内 error 项一一对应
  "source_status": {
    "today_progress":    { "ok": true,  "latency_ms": 12, "error": null },
    "home_dashboard":    { "ok": true,  "latency_ms": 14, "error": null },
    "assessment_profile":{ "ok": true,  "latency_ms": 9,  "error": null },
    "mastery_dashboard": { "ok": false, "latency_ms": 31, "error": "<exception class>: <message head>" },
    "learner_events":    { "ok": true,  "latency_ms": 22, "error": null },
    "compiled_truth":    { "ok": true,  "latency_ms": 7,  "error": null },
    "dry_run_synthesis": { "ok": null,  "latency_ms": 0,  "error": null }   // 未触发为 null
  },
  "freshness": {
    "generated_at": "2026-05-20T10:00:00+08:00",
    "event_count": 42,
    "latest_event_at": "2026-05-20T09:58:11+08:00",
    "unknown_date_count": 0,
    "window_truncated": false
  },
  "overview": {
    "today_done": 0,                       // attempt 口径
    "recent_three_done": 0,                // attempt 口径
    "attempt_count": 0,                    // attempt 总数（窗口内）
    "today_unique_questions": 0,
    "recent_three_unique_questions": 0,
    "unique_question_count": 0,
    "daily_target": 30,
    "streak_days": 0,
    "weak_node_count": 0,
    "due_today_count": 0,
    "focus_hint": "",
    "learner_level": "",
    "study_tip": "",
    "overall_mastery": 0
  },
  "progress_feedback": { /* build_progress_feedback 输出，不在本计划重定义 */ },
  "mastery": { /* groups / hotspots / review_summary / overall_mastery */ },
  "radar_dimensions": [ { "name": "...", "value": 0.0 } ],
  "learning_brain": { /* build_learning_brain_read_model 输出，三段式 */ },
  "next_training": [ { "display_title": "...", "display_meta": "..." } ],
  "legacy_compat": {                       // 仅后台对账可读；小程序与 WebView 严禁消费
    "today_progress": {...},
    "home_dashboard": {...},
    "assessment_profile": {...},
    "mastery_dashboard": {...}
  }
}
```

**契约硬约束**：

1. `degraded=true ⇔ degraded_sources 非空 ⇔ 至少一个 source_status.<k>.ok=false`。三者必须同步，任何不一致视为契约违反。
2. `source_status.<k>.error` 失败时**必须**写入异常类名 + 截断后的 message head（≤ 200 字符），不允许 `"unknown"` 或 `null`。
3. `freshness.window_truncated=true` 时，调用方应将"近 3 天完成"视为下界而非真值。
4. `legacy_compat` 字段在小程序壳层是 forbidden（详见 §Phase 2 测试断言）。
5. 任何新增字段必须先更新本节再写代码。

---

## 废弃旧读法

旧接口保留作为后台兼容和降级观察面，**不参与页面决策**：

- `/api/v1/practice/today-progress`
- `/api/v1/homepage/dashboard`
- `/api/v1/assessment/profile`
- `/api/v1/plan/mastery-dashboard`
- `/api/v1/learning-brain/projection`

页面层不再并发调用这些接口来拼状态。删除条件见 §定量删除门槛。

---

## 实施步骤

### Phase 0：Plan / Contract Alignment

1. 在本计划中固定唯一 authority、废弃旧读法、完成数 attempt 口径、`source_status` / `degraded` / `unknown_date_count` 契约。
2. 对照 `docs/plan/INDEX.md`，确认本计划挂在 Learning Brain / GBrain absorption 主线下。
3. 变更前记录当前学情页实际调用链：页面入口、API 方法、后端路由、旧接口依赖（已记录于本计划 §废弃旧读法）。

**验证**：

- `docs/plan/INDEX.md` 可找到本计划，状态与本文件一致。
- 计划中明确"页面最终展示只读 `/api/v1/mobile/learning-report`"。
- §数据契约 schema v1 与 `deeptutor/services/learner_state/learning_report_read_model.py` 返回字段逐项对齐（无多、无漏、命名一致）。

### Phase 1：Backend Read Model

文件：`deeptutor/services/learner_state/learning_report_read_model.py`、`deeptutor/api/routers/mobile.py`。

1. 后端 read model：
   - 只读 `member_service`、`LearnerStateService`，不直接读 Supabase。
   - 每个输入源通过 `_call_source(name, fn) -> (value, source_status_entry)` 包装：成功记录 `latency_ms`、失败记录 `error` 与 traceback head，**禁止裸 try/except 吞错**。
   - 聚合 `learning_evidence`，输出：
     - `daily_attempts: dict[str, int]`（attempt 口径）
     - `daily_unique_questions: dict[str, set[str]]`（仅用于解释字段）
     - `unknown_date_count: int`
     - `chapter_stats`：以 `concept_id → label` 为 key，含 `done / correct / last_activity_at`。
     - `streak_days`：基于 `daily_attempts`（不允许穿越 `unknown_date_count`）。
   - 复用 `build_progress_feedback` 输出"近 3 天完成"等反馈卡，注入 attempt 数。
   - 复用 `build_learning_brain_read_model` 输出三段式 Learning Brain；`compiled_truth` 缺失时显式触发 `dry_run` 并把 `dry_run_synthesis` 写入 `source_status`。
   - 在返回前组装 §数据契约 schema v1 的 envelope。

2. 路由：`GET /api/v1/mobile/learning-report`：
   - `event_limit: int = Query(default=100, ge=1, le=500)`。
   - 默认按 §关键口径 优先走"时间窗口 + 安全上限"实现；如临时保留 `LIMIT N`，需要在 `freshness.window_truncated` 标记。
   - 不做 in-handler 业务逻辑，所有聚合在 read model。

**验证**：

- 后端单测覆盖：
  - 同题二刷 → `recent_three_done=2`、`recent_three_unique_questions=1`、`attempt_count=2`。
  - 旧 `daily_practice_counts=0` + 有 evidence → "近 3 天完成" 按 evidence。
  - `mastery_dashboard` 抛错 → `degraded=true`、`degraded_sources=["mastery_dashboard"]`、`source_status.mastery_dashboard.error` 含异常类名、其他字段仍可见。
  - `compiled_truth` 缺失但 evidence 非空 → `learning_brain_source="dry_run_learning_evidence"`、`source_status.dry_run_synthesis.ok=true`。
  - 非法 `created_at`（`""`、`"not-a-date"`、未来时间）→ `unknown_date_count=N`、今日进度不被冒充。
  - `event_count >= event_limit` → `window_truncated=true`。
- API 单测覆盖：鉴权用户、`event_limit=1 / 500 / 0 / 501`、`authority` 字段、`degraded` 字段、`schema_version=1`。

### Phase 2：Mini Program Consumption（双壳层强一致）

文件：
- `wx_miniprogram/utils/api.js`、`wx_miniprogram/pages/report/report.js`
- `yousenwebview/packageDeeptutor/utils/api.js`、`yousenwebview/packageDeeptutor/pages/report/report.js`

3. 两个壳层共同遵循：
   - `utils/api.js` 暴露 `getLearningReport(eventLimit, opts)`。
   - 学情页 `onShow` **只**调 `_loadLearningReport` / `_loadReportPage`，单次请求。
   - 旧 `_loadOverview / _loadRadar / _loadMastery / _loadLearningBrain` 暂保留为类方法**仅供手动刷新或回滚命令调用**，不参与 `onShow`、retry、刷新主决策链。
   - 页面展示字段**只**从 unified payload 取；禁止读 `legacy_compat.*`。
   - 检测到 `degraded=true` 时，UI 顶部显示一条"部分数据降级（点击查看）"的提示，明示 `degraded_sources`，避免页面看似正常但事实缺失。
   - 仅当 `getLearningReport` 5xx 或 payload 不通过 schema 校验时，才允许走 `_loadOverview/_loadRadar/_loadMastery/_loadLearningBrain` fallback；fallback 内不得把旧接口升格为完成数 authority，仅展示"基础学情 + 网络异常"提示。

> **yousen 端特别说明**：`_loadReportPage` 当前在 snapshot 子字段为空时仍会触发旧接口 fallback。本 Phase 必须把 fallback 触发条件改成"仅 5xx / payload contract 断裂"，与 wx 端对齐。`_loadReportSnapshot` 内不得读 `legacy_compat.home_dashboard.study_plan`。

**验证**：

- Node 测试（wx）断言：页面入口只触发一次 `getLearningReport`，旧 `getTodayProgress / getHomeDashboard / getAssessmentProfile / getMasteryDashboard / getLearningBrainProjection` 调用次数为 0。
- Node 测试（yousen）必须新增同样断言；`empty snapshot branches should not suppress authoritative fallback reads` 测试需更新为 "仅 5xx / payload 断裂时才触发 fallback"。
- 双端共用一个"`legacy_compat` 不被消费"的静态检查（grep `legacy_compat` in `wx_miniprogram/pages/report` 与 `yousenwebview/packageDeeptutor/pages/report` 必须返回 0 结果）。
- `degraded=true` 时页面 UI 标记可见（单测断言 `page.data.degradedHint` 非空 / `page.data.degradedSources` 数组）。

### Phase 3：True Scenario E2E（可执行版本）

4. 真实场景 e2e（必须照单跑通，不允许仅描述）：

**Actor**：移动端真实用户（任一已开通会员的 demo 账号）。

**前置准备**（一次性，写入 runbook）：
- 微信开发者工具版本 ≥ 1.06.0；项目目录 `wx_miniprogram`，AppID 与 `.env.local` 一致。
- 后端：`uv run uvicorn deeptutor.api.main:app --reload --port 8000`，确认 `/api/v1/health` 返回 200。
- Supabase：`SUPABASE_URL / SUPABASE_SERVICE_KEY` 已配置，`learner_memory_events` 表可写。
- Langfuse：环境变量 `LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY` 已配置；记录本次跑批的 `trace_id`。
- 测试账号在 Supabase `learner_memory_events` 中先清空 `source_feature=construction_grading` 的事件，确保起点干净。

**步骤**：
1. 在微信开发者工具中打开学情页，确认 `今日进度=0`、`近 3 天完成=0`、Learning Brain 空态文案符合预期。
2. 切到对话页，发送中文出题指令（如"出一道关于建筑构造的选择题"）。
3. 选择或作答（如选 A）。
4. 等待系统批改 → 后端写入一条 `learning_evidence`（事件来自 `construction_grading`）。
5. 重复步骤 2-4 一次，使用**同一题** `question_id` 二刷，验证 attempt 口径。
6. 切回学情页，下拉刷新或重新进入。

**断言**（必须同时变化）：
- `近 3 天完成 = 2 题`（attempt 口径，非 1 题）。
- `今日进度 ≥ 2`。
- `unique_question_count = 1`、`recent_three_unique_questions = 1`。
- 薄弱点更新出现对应 concept。
- Learning Brain 当前可信结论非空。
- 证据流出现两条事件（trace_id 可在 Langfuse 中检索）。
- 下一步训练给出 case_repair 类型项。
- typed graph 中存在 `错因 -> 训练 -> 改善/未改善` 链。
- `source_status` 全部 `ok=true`、`degraded=false`。

**容错**：
- 若本地 LLM / RAG / Supabase 任一不可用，**必须记录阻塞源到 runbook**，不能把环境失败误报成 read model 失败。
- Web harness（`/wechat-harness`）可作为快速筛查，但**不能替代**微信开发者工具真实入口。

### Phase 3 Execution Log（2026-05-20，本地受限范围）

本节记录本会话在 sandbox 环境内能跑的所有自动化部分 + 真实远端 / GUI 依赖的阻塞源 + 真人跑批清单。本节是 living document：每次真人在 wx-devtools 中跑完一轮，回填一条记录。

#### A. 已自动跑通（不依赖 GUI / 远端写入）

| 项 | 实证 |
| --- | --- |
| 后端可启动 | `uvicorn deeptutor.api.main:app --host 127.0.0.1 --port 8888` 起来，`/healthz` 200，`/api/v1/system/public-capabilities` 200，243 routes 注册 |
| 同题二刷 attempt 口径（in-process 真实 writeback） | 通过 `construction_grading.writeback.write_grading_error_events` 写入 2 条相同 `question_id` 的 `learning_evidence` 到本地 file store；`build_learning_report_read_model` 返回 `today_done=2 / recent_three_done=2 / attempt_count=2 / today_unique_questions=1 / recent_three_unique_questions=1 / unique_question_count=1` |
| degraded 契约 | 同上 read model 返回 `degraded=False / degraded_sources=[] / source_status` 全 `ok` |
| compiled truth dry-run | `authority.learning_brain_source="dry_run_learning_evidence"` 自动触发 |
| 微信开发者工具 + CLI 可用性 | `/Applications/wechatwebdevtools.app/Contents/MacOS/cli` 存在，子命令含 `auto`（自动化）、`open`、`auto-preview` |

#### B. 阻塞源 — 必须由真人在 staging / 完整环境跑

| 阻塞 | 现象 | 原因 | 解除条件 |
| --- | --- | --- | --- |
| HTTP 鉴权链 → Supabase 404 | `curl -H "Authorization: Bearer demo-token-phase3-demo-user" /api/v1/mobile/learning-report` 返回 500；uvicorn log 显示 `httpx.HTTPStatusError: 404` for `user_identity_aliases?alias_type=eq.legacy_user_id&alias_value=eq.phase3` | `_resolve_authoritative_user_id_from_claims` 强制走 wallet identity alias 查询；demo user 在生产 Supabase 没有 alias 记录；本会话不允许向生产 Supabase 写入（AGENTS §3.7 Aliyun SSH Write Boundary） | 在 staging Supabase 预先 seed 一个 `phase3-demo` 学员的 `user_identity_aliases` 行，或者用真实小程序 wxLogin 流程换取 dtm token |
| 真实出题 / 批改链路 | 未跑 | 需要 OPENAI_API_KEY（未配） / DEEPSEEK / 真实 LLM；本会话 LLM 凭据虽部分配置但不应在 sandbox 内消耗付费额度 | 在 staging 用配置好的 LLM provider 跑一次完整对话 |
| Langfuse `trace_id` 抓取 | 未生成 | 无真实 LLM 调用 → 无 trace | 跑通 B-2 后从 Langfuse UI 抓取 |
| 微信开发者工具 GUI 渲染断言 | 未跑 | Claude Code 不能控制 macOS GUI；wx-devtools `auto` 子命令可远程驱动，但需要 IDE 已经打开并加载项目 | 真人开 wx-devtools，或通过 `wechatwebdevtools cli auto --project ./wx_miniprogram --auto-port 9420` 启用 IDE 自动化后跑测试脚本 |

#### C. 真人跑批清单（照单可执行）

**Step 1 — 准备 demo 账号 (staging)**

```bash
# 在 staging Supabase 中，确保该 demo 账号在 user_identity_aliases 有 alias：
psql "$STAGING_DB_URL" -c "
  INSERT INTO user_identity_aliases (alias_type, alias_value, user_id, source, confidence)
  VALUES ('legacy_user_id', 'phase3-demo-user', 'phase3-demo-user', 'manual_seed', 1.0)
  ON CONFLICT DO NOTHING;
"
# 同时确保 phase3-demo-user 的 wallet 已开通会员（避免 paywall 拦截）
```

**Step 2 — 启动后端（指向 staging）**

```bash
DEEPTUTOR_ENV=staging uv run uvicorn deeptutor.api.main:app --host 127.0.0.1 --port 8888
curl -s http://127.0.0.1:8888/healthz   # 必须 200
curl -s -H "Authorization: Bearer demo-token-phase3-demo-user" \
     "http://127.0.0.1:8888/api/v1/mobile/learning-report?event_limit=50" \
  | python3 -c 'import json,sys; b=json.load(sys.stdin); print("schema_version=",b["schema_version"]); print("today_done=",b["overview"]["today_done"]); print("degraded=",b["degraded"])'
# 期望：schema_version=1, today_done=0 (起点干净), degraded=false
```

**Step 3 — 启动微信开发者工具 + 自动化端口**

```bash
# 在 IDE 设置 → 安全 → 服务端口里打开 CLI/HTTP；以下命令打开项目
/Applications/wechatwebdevtools.app/Contents/MacOS/cli open \
  --project /Users/<you>/Documents/CYH_2/Markzuo/deeptutor/wx_miniprogram

# 启用自动化（端口 9420 仅作示例，可换）
/Applications/wechatwebdevtools.app/Contents/MacOS/cli auto \
  --project /Users/<you>/Documents/CYH_2/Markzuo/deeptutor/wx_miniprogram \
  --auto-port 9420
```

**Step 4 — 在 wx-devtools 中按 Phase 3 §步骤执行**

1. 用 demo 账号登录小程序。
2. 切到学情页，截图：`screenshots/phase3-before.png`，断言 `近 3 天完成=0`、`今日进度=0`。
3. 切到对话页，发送出题指令"出一道关于建筑构造的选择题"。
4. 作答（如选 A）→ 等批改完成 → 后端 outbox 写一条 `learning_evidence`。
5. 重复步骤 3-4 一次，作答时**用同一个 `question_id`**（如出题侧 prompt 里指定"重新做上一题"，或后端 dev 接口直接 replay 同题）。验证 attempt 口径。
6. 切回学情页，下拉刷新。截图：`screenshots/phase3-after.png`。

**Step 5 — 断言（必须**同时**满足）**

- `近 3 天完成 = 2 题`（attempt 口径，**非 1 题**）
- `今日进度 ≥ 2`
- `unique_question_count = 1`
- `recent_three_unique_questions = 1`
- 薄弱点列表出现 `concept = 1A432000`（或当时实际批改 concept）
- Learning Brain：当前可信结论非空、证据流 ≥ 2 条、下一步训练含 `case_repair`
- typed graph：存在 `错因 -> 训练 -> 改善/未改善` 链
- API 层 `source_status` 全部 `ok=true`、`degraded=false`
- Langfuse 中能搜到 2 条 trace（含 batch grading）

**Step 6 — 回填本节**

把以下补到 §D：

```yaml
phase3_execution_runs:
  - date: 2026-MM-DD
    executor: <name>
    env: staging
    wx_devtools_version: <e.g. 1.06.x>
    langfuse_trace_ids:
      - <trace_id_1>
      - <trace_id_2>
    screenshots:
      before: phase3-before-<date>.png
      after: phase3-after-<date>.png
    assertions_passed: true   # 或者列出失败项
    blocker_notes: <空 或 具体卡点>
```

#### D. 真人执行记录（回填表）

> 此表初始为空。每次真人在 wx-devtools 跑完一轮真实 E2E，按 §C Step 6 模板追加一行；累积到第 3 次连续通过，方可推进到 §定量删除门槛 14 天观察期。

| run | date | executor | env | wx_devtools | trace_ids | screenshots | assertions | blockers |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| _(待补)_ | | | | | | | | |

### Phase 4：Release Gate / Observability

5. 发布前 gate：
   - 后端单测：§Phase 1 验证列表全部通过。
   - API 单测：§Phase 1 验证列表全部通过。
   - 小程序 Node 测试：§Phase 2 验证列表全部通过（wx 与 yousen 双端）。
   - 真实链路 e2e：§Phase 3 步骤全部通过，并把 Langfuse `trace_id` 写入 PR 描述。
   - 线上 access log / Langfuse / 后端日志确认学情页主入口命中新接口，且 deprecated 接口的 `referer = wx_miniprogram | packageDeeptutor` 流量趋零（量化阈值见 §定量删除门槛）。
   - 若 `degraded=true` 出现，必须能从 `source_status` 定位是 `mastery_dashboard / assessment_profile / learner_events / compiled_truth / dry_run_synthesis` 中哪个失败。

6. 回滚策略：
   - 触发条件（任一）：
     - `/api/v1/mobile/learning-report` 在线上 5 分钟窗口 5xx 率 ≥ 1%。
     - payload contract 断裂（前端 schema 校验失败率 ≥ 0.5%）。
     - `degraded=true` 比例 ≥ 5% 持续 15 分钟且 `degraded_sources` 包含 `learner_events` 或 `compiled_truth`。
   - 动作：前端打开 fallback 开关（`enable_report_legacy_fallback=true`），允许 `_loadOverview/_loadRadar/_loadMastery/_loadLearningBrain` 短期参与。
   - 边界：
     - fallback 只能读取旧接口展示基础学情，不得重新把旧接口升级为完成数 authority。
     - 回滚期间必须保留事件写入链路，避免学习事实丢失。
     - 必须在 24 小时内提交 root-cause + fix PR；超时升级 Owner。

---

## Local Acceptance Evidence（2026-05-20）

本节记录本地可执行验收，证明 Phase 0-3 与 Phase 4 的本地发布前 gate 已完成。生产连续观察仍以 §定量删除门槛 为准，不能被本地验收替代。

### 后端 / API / 双壳层测试

已执行：

```bash
python -m py_compile scripts/run_learning_report_read_model_e2e.py
pytest tests/services/learner_state/test_learning_report_read_model.py \
  tests/api/test_mobile_router.py::test_mobile_learning_report_uses_learning_evidence_for_recent_progress \
  tests/api/test_mobile_router.py::test_mobile_learning_report_requires_authentication \
  tests/api/test_mobile_router.py::test_mobile_learning_report_rejects_event_limit_out_of_range \
  tests/api/test_mobile_router.py::test_mobile_learning_report_accepts_event_limit_boundaries \
  tests/api/test_mobile_router.py::test_mobile_learning_report_propagates_source_degradation -q
node wx_miniprogram/tests/test_report_learning_brain.js
node yousenwebview/tests/test_report_snapshot_dedupe.js
```

结果：

- 后端/API：`24 passed`
- wx：`PASS test_report_learning_brain.js`
- yousen：`PASS test_report_snapshot_dedupe.js (37 assertions)`

### 真实读模型 E2E

本地 `8001` 存在旧进程且未加载本计划新增路由，故启动当前代码到 `8013`：

```bash
BACKEND_PORT=8013 scripts/start_local_learning_brain.sh start --no-web
python scripts/run_learning_report_read_model_e2e.py \
  --base-url http://127.0.0.1:8013 \
  --code dev-learning-report-e2e-1779263557 \
  --open-devtools \
  | tee .local-runs/learning-brain/learning-report-e2e-latest.json
```

关键断言结果：

- 登录用户：`wx_d1d45958ca5b`
- 起点：`recent_three_done=0`、`attempt_count=0`
- 两次中文批改 attempt 后：
  - `recent_three_done=2`
  - `today_done=2`
  - `attempt_count=2`
  - `unique_question_count=1`
  - `recent_three_unique_questions=1`
  - `degraded=false`
  - `source_status` 全部可解释且成功
  - Learning Brain `current_truth=6`、`evidence_flow=14`、`next_training=1`
  - typed graph：`has_training_uses_question=true`、`has_training_not_improved_error=true`
- 第三次改善 attempt 后：
  - `attempt_count=3`
  - `unique_question_count=1`
  - typed graph 仍保留完整 `错因 -> 训练 -> 未改善` 链
- 微信开发者工具 CLI：
  - `islogin={"login":true}`
  - `open_returncode=0`
  - `open_stderr` 含 `✔ open`

验收产物：

- `.local-runs/learning-brain/learning-report-e2e-latest.json`
- 本地服务日志：`.local-runs/learning-brain/logs/backend.log`

### 仍不可推进 Done 的原因

§定量删除门槛 是真实线上时间窗口，不可压缩：

- `/api/v1/mobile/learning-report` 上线后连续 14 天 5xx / p95 / degraded 达标。
- deprecated 5 个接口在 `referer = wx_miniprogram | packageDeeptutor` 下连续 7 天 RPS=0。
- 后台 BI / 管理端迁移或 ADR 豁免完成。

因此当前最高可信状态是：`Local Acceptance Gate Passed — Pending Production Observation`。

---

## 测试矩阵

| 场景 | 输入 | 预期 |
| --- | --- | --- |
| 旧 daily count 为 0，但有 `learning_evidence` | 今日 1 条 evidence | `近 3 天完成=1题`、`progress_source=learner_memory_events.learning_evidence` |
| 同题二刷（attempt 口径硬约束） | 同一 `question_id` 同一日 2 条 evidence | `today_done=2`、`recent_three_done=2`、`today_unique_questions=1`、`attempt_count=2` |
| 跨日多题练习 | 今日 1 条 + 昨日 1 条 + 前日 1 条（不同 question_id） | `recent_three_done=3`、`recent_three_unique_questions=3` |
| 多章节练习 | 不同 concept evidence | 章节统计、雷达、弱点分布分别更新 |
| 批改失败未写 event | 无 evidence | 学情不虚增，页面提示"完成练习后生成画像" |
| `mastery_dashboard` 抛错 | `get_mastery_dashboard` raise | `degraded=true`、`degraded_sources=["mastery_dashboard"]`、`source_status.mastery_dashboard.error` 含异常类名；进度和 Learning Brain 仍尽量可见 |
| 多源同时降级 | mastery + assessment 同时 raise | `degraded=true`、`degraded_sources=["mastery_dashboard","assessment_profile"]`、其余 `ok=true` |
| compiled truth 缺失 | 有 evidence，无 projection | `learning_brain_source="dry_run_learning_evidence"`、`source_status.dry_run_synthesis.ok=true`、Learning Brain 三段式可见 |
| compiled truth 存在 | 有 projection | `learning_brain_source="compiled_learning_truth"`、不重复触发 dry_run |
| 人工修正 supersede | correction event 覆盖旧结论 | 当前可信结论体现 supersede，证据流保留旧证据 |
| 改善链路 | 先错后对同一 concept | typed graph 出现 `错因 -> 训练 -> 改善` |
| 过期事实 | 旧事件超出有效窗口 | decay 后弱点权重下降，不再长期卡住画像 |
| 非法时间戳 | `created_at=""`、`"not-a-date"`、未来 1 天 | `unknown_date_count` 累加；今日 attempt 不被冒充；`daily_counts` 无 `__unknown__` key |
| `event_limit` 触顶 | 实际 evidence 数 ≥ `event_limit` | `freshness.window_truncated=true` |
| `event_limit` 越界 | `event_limit=0` 或 `501` | API 返回 422（FastAPI Query 边界） |
| 未授权用户 | 无 `Authorization` header | API 返回 401，不暴露 user_id |
| 小程序 `legacy_compat` 静态检查 | grep `legacy_compat` in mini-program pages | 命中数 = 0 |
| 小程序入口断言 | wx + yousen 页面 `onShow` 触发 | `getLearningReport` 调用 = 1，旧 5 个接口调用 = 0 |
| `degraded` UI 提示 | mock degraded=true 响应 | `page.data.degradedHint` 非空、`page.data.degradedSources` 含具体名称 |

---

## 验收标准

| 项 | 标准 |
| --- | --- |
| 完成数 authority | `近 3 天完成` 不再从 `daily_practice_counts` 读，且按 attempt 口径计数（同题二刷 = 2）|
| Degraded 可观测 | 任一旧输入源异常时，接口仍尽量返回 evidence-driven 学情，但**必须**标记 `degraded=true` 并列出失败源；不允许任何 `try/except: pass` |
| 实时性 | 刚完成一题后，刷新学情页能看到完成数 +1（attempt 口径）|
| 三段式 | 同一批阅卷事件能在 Learning Brain 中形成"当前可信结论 / 证据流 / 下一步训练" |
| 页面无竞争 | 页面层没有多接口竞争同一学情事实；wx + yousen 双壳层入口都只调 `getLearningReport` |
| 旧接口保留 | 旧接口保留可用，但只作为后台兼容输入和回滚 fallback |
| degraded 解释能力 | `source_status` 能解释页面为什么 degraded，不能只给用户一个空状态 |
| 时间戳健壮 | 非法时间戳事件进入 `unknown_date_count`，不污染今日进度 |
| 窗口可证 | `freshness.window_truncated` 在 evidence 数触顶时为 `true`，前端正确呈现"下界"语义 |
| 契约一致 | §数据契约 schema v1 与代码返回逐字段一致；任何新增字段先改本文件 |
| 小程序契约 lint | `legacy_compat` 在两个壳层 `pages/report` 下 grep 数 = 0 |

---

## 定量删除门槛

只有同时满足以下条件，才考虑删除旧页面读法：

1. `/api/v1/mobile/learning-report` 上线后**连续 14 天**：
   - 5xx 率 < 0.1%（按 5 分钟窗口 p95）
   - p95 延迟 < 800 ms
   - `degraded=true` 比例 < 1%
2. Langfuse / access log 证明：
   - 5 个 deprecated 接口（`/api/v1/practice/today-progress` 等）在 `referer = wx_miniprogram | packageDeeptutor` 下的 RPS **连续 7 天 = 0**。
3. 后台 BI / 管理端确认：
   - 已迁移到新的后台读模型，**或**明确写入 ADR 豁免，列出依赖方与替代方案。
4. 删除 PR 必须挂回本计划，并在 INDEX.md 中将本计划状态推进到 `Done`。

---

## Open Gaps（2026-05-20 收口记录）

下表是 2026-05-20 评审锁定的 7 项 Gap。本批次已逐条收口；本地验收已推进到 `Local Acceptance Gate Passed — Pending Production Observation`，但 §定量删除门槛 还未启动观察期，未达 Done。

| Gap | 关闭做法 | Closed by |
| --- | --- | --- |
| **G1：完成数 attempt 口径** | `_aggregate_learning_evidence` 改为按事件 attempt 累加 `daily_attempts`；`daily_unique_questions` 单独维护用于解释字段。`set(question_id)→len` 模式已删除。 | 本批次 (2026-05-20)，by `learning_report_read_model.py` |
| **G2：`source_status` / `degraded` / `degraded_sources`** | 新增 `_call_source(name, fn) -> (value, status_entry)`，包装所有输入源（`today_progress / home_dashboard / assessment_profile / mastery_dashboard / learner_events / compiled_truth / dry_run_synthesis`）。envelope 字段 `degraded / degraded_sources / source_status` 三者按"任一 ok=false → degraded=true"硬约束同步。 | 本批次 (2026-05-20)，by `learning_report_read_model.py` |
| **G3：`unknown_date_count`** | 新增 `_date_key_from_iso`：空字符串 / 无法解析 / 明显未来时间统一返回 `None`，事件进入 `unknown_date_count`，不进 `daily_attempts`。`freshness.unknown_date_count` 暴露。 | 本批次 (2026-05-20)，by `learning_report_read_model.py` |
| **G4：`attempt_count` / `*_unique_questions` / `window_truncated`** | `overview` 补齐 `attempt_count / today_unique_questions / recent_three_unique_questions / unique_question_count`；`freshness` 补齐 `unknown_date_count / window_truncated`（`event_count >= event_limit` 时为 `true`）。 | 本批次 (2026-05-20)，by `learning_report_read_model.py` |
| **G5：yousen 入口收齐** | `_loadReportPage` 命中 unified payload 直接走 `_hydrateFromUnifiedReport`，不再并发触发 `_loadOverview/_loadRadar/_loadMastery/_loadLearningBrain`；这四个方法首行 `if (snapshot) return;`，只在 unified 整体失败时被 fallback 显式调用。`_loadReportSnapshot` 不再读 `legacy_compat.home_dashboard.study_plan`。`retryRadar/retryMastery` 改为重新跑 `_loadReportPage`。`degradedHint / degradedSources / reportFallbackActive` 暴露给 UI。 | 本批次 (2026-05-20)，by `yousenwebview/packageDeeptutor/pages/report/report.js` |
| **G6：测试可证明 attempt 口径 + degraded 契约** | `tests/services/learner_state/test_learning_report_read_model.py` 新增：同题二刷、跨日 attempt、`mastery_dashboard` raise → degraded、多源同时 raise、合法 + 非法时间戳混合、`unknown_date_count`、`window_truncated` 触顶 / 不触顶、`compiled_truth` 存在跳过 dry_run、`compiled_truth` 缺失触发 dry_run。`tests/api/test_mobile_router.py` 新增：无 Authorization → 401、`event_limit ∈ {0, -1, 501}` → 422、`event_limit ∈ {1, 500}` → 200、`source_status` 一致性、`schema_version=1` + 全字段断言。wx Node 测试新增 `legacy_compat` grep=0、入口只触发一次 `getLearningReport`、旧 5 个接口调用 0 次。yousen Node 测试新增 `legacy_compat` grep=0、unified snapshot 命中时旧接口 0 次、unified payload 失败触发 fallback 且 `degradedHint` 非空、`degraded=true` 时 UI 字段同步。 | 本批次 (2026-05-20)，by 后端/API/wx/yousen 测试文件 |
| **G7：INDEX / 计划状态同步** | INDEX.md 描述与本计划 Status 同时更新到 `Local Acceptance Gate Passed — Pending Production Observation`，并显式说明"7 项 Gap 已关闭，本地验收通过，但 §定量删除门槛 未完成观察"。 | 本批次 (2026-05-20)，by `docs/plan/INDEX.md` + 本文件顶部 Status |

> 注：所有 Gap 行**保留**作为追溯记录（不删除），状态切换由 Status 头注明。下一阶段进入观察期，目标是 §定量删除门槛：连续 14 天 5xx<0.1% + p95<800 ms + `degraded` 比例 <1%，且 deprecated 5 个接口在 `referer = wx_miniprogram | packageDeeptutor` 下 7 天 RPS=0；满足后才能把状态推进到 `Done` 并执行删除 PR。

每个 Gap 后续如需追加修复（如生产环境暴露新边界），仍按原规则：
1. 提交 PR 标题包含 `[learning-report-read-model][Gx]`。
2. PR 描述链接本节，并在对应 Gap 行追加新的 `Closed by PR #xxx, <date>` 注记。
3. 推进到 `Done` 必须满足 §定量删除门槛。

---

## 代码入口索引

| 用途 | 文件 |
| --- | --- |
| Read model 聚合 | `deeptutor/services/learner_state/learning_report_read_model.py` |
| 路由暴露 | `deeptutor/api/routers/mobile.py`（`GET /api/v1/mobile/learning-report`） |
| Learning Brain 三段式 | `deeptutor/services/learner_state/learning_brain_read_model.py` |
| Progress feedback 卡片 | `deeptutor/services/learner_state/progress_feedback.py` |
| Compiled truth / synthesis | `deeptutor/services/learner_state/service.py` + `learning_synthesis.py` |
| Evidence writeback | `deeptutor/services/construction_grading/writeback.py` |
| wx 入口 | `wx_miniprogram/pages/report/report.js` + `wx_miniprogram/utils/api.js` |
| yousen 入口 | `yousenwebview/packageDeeptutor/pages/report/report.js` + `yousenwebview/packageDeeptutor/utils/api.js` |
| 后端单测 | `tests/services/learner_state/test_learning_report_read_model.py` |
| API 单测 | `tests/api/test_mobile_router.py`（`test_mobile_learning_report_*`） |
| 小程序 Node 测试 | `wx_miniprogram/tests/test_report_learning_brain.js` + `yousenwebview/tests/test_report_snapshot_dedupe.js` |
| 本地真实读模型 E2E | `scripts/run_learning_report_read_model_e2e.py` |
