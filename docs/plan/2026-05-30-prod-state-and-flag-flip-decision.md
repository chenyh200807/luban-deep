# 生产地基核验 + 体验 Flag 翻转决策单

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-30 |
| 类型 | Decision Sheet（只读核验产物） |
| 状态 | v1 |
| 核验方式 | **纯只读**：生产 Supabase 仅 `SET default_transaction_read_only=on` + SELECT 系统目录；阿里云 `/root/deeptutor/.env` 仅 `grep` 取点名 flag；本地仅 Read/grep 代码。**未翻任何 flag、未写任何库、未部署。** |
| 凭证来源 | `FastAPI20251222/.env` 的 `DB_URL`（host 校验 = `aws-1-ap-southeast-1.pooler.supabase.com:6543` db=`postgres`，确认是目标生产库；明文未打印） |
| 纪律 | 严守 AGENTS §3.7（阿里云非 `/root/deeptutor` 路径只读；本任务全程只读不越界） |
| 上游输入 | [2026-05-30-plan-vs-code-reconciliation.md](2026-05-30-plan-vs-code-reconciliation.md) 的 A 档#1/#4、B 档#5/#8 |

---

## 0. 执行摘要（前提被核验推翻，必读）

> **原任务前提**：「核心体验代码已落地但多个 flag 默认 OFF、学生侧 0 可见；最大杠杆是翻开 `LEARNING_STATE_INFERENCE_V2`，但翻 ON 前要先证实 RLS、且 `action_loop` 子门保持 OFF（采分点覆盖太低）。」

**生产 `.env` 实测推翻了这个前提**：

1. **`LEARNING_STATE_INFERENCE_V2` 及其全部 4 个子门在生产已经 100% 全量开（`=on`），对所有用户生效**——不是默认 OFF、不是待翻。
2. **其中 `ACTION_LOOP_STAGE=on` 也开着**——而生产 `questions_bank` 实测 `grading_rubric` 全库 **0%**、case_study `map_eligible` 仅 **48.7%**。即**约 51% 的案例题，学生现在打开"采分点漏分地图"就是空态**。这正是任务担心要避免的情况，但它**已经在线上发生**。
3. RLS 地基核验**通过**：学情/钱包/测评相关表均 RLS enabled，策略 owner-scoped 或 0-policy 默认拒绝，**无跨租户泄露**。所以"引擎全开"不是数据越权风险——任务里"没核实 RLS 就开学情面=越权"的担心，经核验已排除。
4. `assessment_sessions` 持久化**安全**：`DEEPTUTOR_ENV=production` → `is_production_environment()=True` → 强制走 Supabase durable，**不存在"静默回落 InMemory 丢卷"风险**（该风险只在非 production 且 flag 未设时才成立）。
5. **语义路由是 primary ON、shadow OFF**（默认值，无 .env 覆盖），scope=`all`。因 shadow 关闭，**误切率基线无数据可算**（安全垫从未启用），属真实在线风险（报告#8 成立）。

**结论方向反转**：当前不需要"翻开关让学情可见"——它早已全开。真正该做的决策是 **(a) 把过度激进的 `ACTION_LOOP_STAGE` 收回到 `off`/`internal` 直到采分点覆盖达标**，以及 **(b) 评估 semantic router 是否该先回 shadow 跑基线**。下一条"调 flag"的 prompt 应基于本单执行**收口/降级**，而非"翻开"。

---

## 1. A#1 — Assessment 持久化核验

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| `assessment_sessions` 表存在 | ✅ PASS | `pg_class` 命中，RLS on，3 策略 |
| 生产强制走 Supabase durable | ✅ PASS | `member_console/service.py:545` `use_supabase = is_production_environment() or env_flag("ASSESSMENT_SESSIONS_USE_SUPABASE")`；阿里云 `DEEPTUTOR_ENV=production`/`APP_ENV=production`/`SERVICE_ENV=production` → `is_production_environment()=True`，**不读 flag 即走 Supabase** |
| "未配置静默回落 InMemory→重启丢卷"风险 | ✅ 不存在（生产） | 回落分支 `service.py:553-555` 仅在**非 production 且 flag 未设**时触发；生产恒为 True，永不回落。`ASSESSMENT_SESSIONS_USE_SUPABASE` 未设属预期、无害 |
| `assessment_sessions` RLS owner-scoped | ✅ PASS | 3 策略全 `{authenticated}` + `(auth.uid())::text = user_id`（insert 用 with_check、select/update 用 using）；anon 无策略→被 RLS 拦截 |

**A#1 判定：PASS。** 生产测评卷持久、owner 隔离、无丢卷风险。无需任何动作。

---

## 2. A#4 — RLS migration 生产 apply 逐表核验

> 注：本 Supabase 项目**不使用** `supabase_migrations.schema_migrations` 台账（查询报 relation 不存在）。因此"是否 apply"以 **schema 真实状态**为准——这比 migration 日志更硬，直接证明 migration 效果已落库。

| 表 | RLS | 策略数 | owner-scoped | anon/auth DML 直授 | 判定 |
| --- | --- | --- | --- | --- | --- |
| `learner_memory_events` | ✅ on | 0 | — (0-policy = 默认拒绝) | 无 | ✅ PASS（service-role only） |
| `learner_summaries` | ✅ on | 0 | — (默认拒绝) | 无 | ✅ PASS |
| `learner_mistake_book_items` | ✅ on | 4 | ✅ `auth.uid()::text=user_id` | 无 | ✅ PASS（#5 前置达成） |
| `wallets` | ✅ on | 2 | ✅ user_isolation + service_bypass | 无（#82 revoke 生效） | ✅ PASS |
| `wallet_ledger` | ✅ on | 0 | — (默认拒绝) | 无 | ✅ PASS（账本不可客户端写） |
| `assessment_forms` | ✅ on | 0 | — (默认拒绝) | 无 | ✅ PASS（service-role only，20260525130000 效果在） |
| `assessment_sessions` | ✅ on | 3 | ✅ `auth.uid()::text=user_id` | ⚠️ anon+auth 有 DML grant | 🟡 PASS-with-note |
| `user_profiles` | ✅ on | 2 | ✅ owner + service_role | 无 | ✅ PASS（#75 效果在） |
| `user_stats` | ✅ on | 2 | ✅ owner + service_role | 无 | ✅ PASS（#75） |
| `bot_learner_overlays` | ✅ on | 1 | ✅ `auth.uid()::text=user_id` (ALL) | ⚠️ anon+auth 有 DML grant | 🟡 PASS-with-note |
| `bot_learner_overlay_events` | ✅ on | 1 | ✅ owner (ALL) | ⚠️ anon+auth 有 DML grant | 🟡 PASS-with-note |
| `bot_learner_overlay_audit` | ✅ on | 1 | ✅ owner (ALL) | ⚠️ anon+auth 有 DML grant | 🟡 审计可自篡改（见下） |
| `luban_feedback` | ✅ on | 0 | — (默认拒绝) | ⚠️ anon+auth 有 DML grant（被 0-policy 兜住） | 🟡 PASS-with-note |

> 报告称"4 张沉默表"实为 migration `20260525120000_close_rls_off_business_tables.sql` 关闭的 **25 张** RLS-off 业务表（含 assessment_forms / learner_memory_events / learner_summaries / daily_paths / heartbeat_jobs / intents 等），策略为 enable RLS + revoke 而**不加 policy**（业务全走 service_role）。

**A#4 判定：核心 PASS，无跨租户泄露。** 两个 P2 收口项（非上线 blocker）：

- **P2-a 审计表可自篡改（合规反模式）**：`bot_learner_overlay_audit` 的 `_self_access` 策略 `cmd=ALL {authenticated}`，允许用户对**自己的审计行** INSERT/UPDATE/DELETE。审计应 append-only/service-role-write。owner-scoped 保证无跨租户泄露，但学员可篡改自己的审计轨迹。建议收紧为 service-role 写 + owner 只读（`overlays`/`overlay_events` 同样是 self-write，但那是个人学情 overlay、属设计，影响仅及自身画像，优先级低于 audit）。
- **P2-b 残留 anon/authenticated DML 直授**：`assessment_sessions` / `bot_learner_overlay*` / `luban_feedback` 仍带 Supabase 默认 `grant`。这些表因创建于 `20260525120000` 之外（或已自带 RLS 故不在那次 revoke 名单），grant 未被收。**当前被 RLS 兜住**（0-policy 拒绝，或策略不含 anon 角色），无实际暴露；但属 SR2 想清除的 defense-in-depth 反模式，建议补一条 `revoke insert,update,delete on these from anon, authenticated`（service_role 不受影响）。

---

## 3. 生产 Flag 真值表（读阿里云 `/root/deeptutor/.env`，只读）

| Flag（生产 env 实际键名） | 生产值 | 代码默认 | 解析后语义 | 来源 |
| --- | --- | --- | --- | --- |
| `LEARNING_STATE_INFERENCE_V2_STAGE` | **`on`** | off | **master 100% 全开** | `cohort.py` `_STAGE_PERCENT["on"]=100` |
| `LEARNING_STATE_INFERENCE_V2_EVIDENCE_STAGE` | **`on`** | off | 子门 100% | 同上 |
| `LEARNING_STATE_INFERENCE_V2_STATE_PROJECTION_STAGE` | **`on`** | off | 子门 100% | 同上 |
| `LEARNING_STATE_INFERENCE_V2_ACTION_LOOP_STAGE` | **`on`** ⚠️ | off | **子门 100%（采分点地图/下一步训练全开）** | 同上 |
| `LEARNING_STATE_INFERENCE_V2_VERIFICATION_STAGE` | **`on`** | off | 子门 100% | 同上 |
| `LEARNING_STATE_INFERENCE_V2_INTERNAL_USERS` | 未设置 | ∅ | 无白名单（已全量故无所谓） | `cohort.py:_internal_users` |
| `DEEPTUTOR_SEMANTIC_ROUTER_ENABLED` | 未设置 | **True** | **primary ON** | `orchestrator.py:490` |
| `DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE` | 未设置 | **False** | **shadow OFF（无安全垫/无对比数据）** | `orchestrator.py:497` |
| `DEEPTUTOR_SEMANTIC_ROUTER_SCOPE` | 未设置 | `all` | 全 turn 走新路由 | `orchestrator.py:500-505` |
| `DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED` | 未设置 | **False** | **扣费 no-op（内测安全）** | `wallet/service.py:28` |
| `SUPABASE_RAG_COMPILED_TRUTH_ENABLED` | 未设置 | **False** | shadow-only，学生侧个性化召回未生效 | `supabase.py:1675` |
| `SUPABASE_RAG_PROVENANCE_BOOST_ENABLED` | 未设置 | **False** | 同上 | `supabase.py:1688` |

> ⚠️ 注意键名：master 与子门用 `*_STAGE` 后缀解析（`cohort.py:_stage_env_name`），**裸 `LEARNING_STATE_INFERENCE_V2` 未设是无关项**；semantic router shadow 的真实键是 `DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE`（非 `_SHADOW_ENABLED`）。

---

## 4. #5 — `LEARNING_STATE_INFERENCE_V2` 前置条件 + 反转结论

| 前置条件 | 状态 | 证据 |
| --- | --- | --- |
| `learner_mistake_book_items` 表+RLS 已 apply 生产 | ✅ 满足 | RLS on + 4 owner 策略（§2） |
| 底层证据表 RLS 已 apply | ✅ 满足 | `learner_memory_events`/`learner_summaries` RLS on（§2） |
| 采分点覆盖足以避免大面积空态 | ❌ **不满足** | 生产 `questions_bank`：total=4638，case_study=1961，`grading_rubric` 非空=**0（0%）**，`grading_keywords` 非空=960（49.0%），`structured_rules` 非空=661（33.7%），**map_eligible=955/1961=48.7%** |

**结论（反转）**：
- 任务设想的"翻 internal/cohort 但 `action_loop` 保持 OFF"——**已无法照做，因为生产 master + 4 子门含 `action_loop` 全部 `on`（100%）已超过 internal/cohort**。
- RLS 已验证安全，所以"引擎全开"**不是越权风险**；问题纯属**产品质量**：`action_loop=on` + map_eligible 48.7% → 约 51% 案例题采分点地图为空态（代码有 honest-empty-state 兜底，故不是崩溃，但体验降级）。
- **数据反向证实了任务的产品直觉是对的**：`action_loop` 在采分点覆盖达标前不该全量。当前它却全量开着。

**建议动作（需人工决策，属"调 flag"范畴，本只读单不执行）**：
- **选项 A（推荐，保守）**：把 `LEARNING_STATE_INFERENCE_V2_ACTION_LOOP_STAGE` 由 `on` 收回 `internal`（或 `off`），保留 `evidence`/`state_projection`/`verification` 全开——学生仍看到学情诊断/历史证据/复测，但不被大面积空的采分点地图拉低体验；待教研把 `map_eligible` 抬到 ≥70%（计划自设门槛）再逐档放回。
- **选项 B（需证据）**：若真机实测确认 honest-empty-state 对 51% 案例题"足够体面"（不误导、不显残缺），可维持 `action_loop=on`——但必须有真机/DevTools 截图证据，目前没有。

---

## 5. #8 — Semantic Router 现状与判定

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 生产是 primary 还是 shadow | **primary ON** | `_semantic_router_enabled` default=True，`.env` 未覆盖（`orchestrator.py:490`） |
| shadow 安全垫是否启用 | **否（OFF）** | `_semantic_router_shadow_mode` default=False，`.env` 未覆盖（`orchestrator.py:497`） |
| scope | `all`（全 turn） | default（`orchestrator.py:504`） |
| 误切率基线可否只读跑出 | **否** | `report_semantic_router_rollout.py` 只吃 JSONL trace 导出文件（`_load_records`），不连实时源；且 **shadow 关闭→没有 primary-vs-shadow 对比记录在产生**，无数据可算基线 |

**#8 判定**：新语义路由作为**主裁判**已在生产全量上线，且**从未在 shadow 下跑过基线**——"先 shadow 再放量"的计划灰度顺序被默认配置跳过。这是真实在线风险（误切对象/答非所问会直接打到核心聊天体验），但无离线证据证明其当前误切率。

**建议动作（需人工决策）**：
- **选项 A（取证后再判）**：先开 `DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE=on` 跑一段，导出 trace JSONL → `report_semantic_router_rollout.py` 得 disagreement/误切率基线，再决定 primary 是否可信。
- **选项 B（先兜底）**：在拿到基线前，把 scope 收到 `question_and_guide`（缩小新路由作用面）或回退 shadow，降低未知误切对核心聊天的暴露。
- 二者皆属"调 flag/部署"动作，本只读单不执行。

---

## 6. 【翻转决策单】

> 每行：**当前生产值 | 前置是否满足 | 建议动作 | 为什么先这条**。注意——多数 flag **已经开着**，本单的"动作"多为**收口/取证**而非"翻开"。

| Flag | 当前生产值 | 前置满足? | 建议动作 | 为什么 |
| --- | --- | --- | --- | --- |
| `LEARNING_STATE_INFERENCE_V2`(master) | **on/100%** | ✅ RLS 安全 | **维持**（已全开且 RLS 安全，无越权） | 数据隔离已核验，引擎全开不构成安全问题 |
| `…_EVIDENCE_STAGE` | on | ✅ | 维持 | 历史证据/错因有数据，体验正向 |
| `…_STATE_PROJECTION_STAGE` | on | ✅ | 维持 | 三层画像投影，正向 |
| `…_ACTION_LOOP_STAGE` | **on** | ❌ map_eligible 48.7% / rubric 0% | **收回 `internal`/`off`**（推荐）或真机取证后维持 | 51% 案例题采分点地图空态，拉低体验；任务直觉正确，应降级 |
| `…_VERIFICATION_STAGE` | on | ✅ | 维持 | 复测闭环，正向 |
| `DEEPTUTOR_SEMANTIC_ROUTER_ENABLED` | on(primary) | ⚠️ 无基线 | **先开 shadow 取基线**，或暂缩 scope | 主裁判从未跑 shadow 基线，误切率未知 |
| `DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE` | off | — | **开 on 取一段基线** | 没有它就拿不到误切率，无法判 primary 安全 |
| `DEEPTUTOR_BILLING_ENFORCEMENT_ENABLED` | off | — | **维持 off** | 内测扣费 no-op 是正确安全姿态 |
| `SUPABASE_RAG_COMPILED_TRUTH_ENABLED` | off | — | **维持 off** | 契约 §20/§22 默认 OFF，无 staging baseline 前不翻 |
| `SUPABASE_RAG_PROVENANCE_BOOST_ENABLED` | off | — | **维持 off** | 同上 |

### 为什么是这条只读单、而不是"直接翻开关"或"先回写文档"

- **直接翻 `LEARNING_STATE_INFERENCE_V2` 是个伪命题**——它早已全开。不先核验就按"它是 OFF"去操作，会做出错误动作（甚至重复开一个已开的门）。**只读核验是发现"前提错了"的唯一途径**，纪律上不能跳。
- 本单一次性锁定了 A#1（持久化 PASS）/ A#4（RLS 核心 PASS + 2 个 P2 收口）两个硬门，和 #5 / #8 两个翻转前提的**生产真值**，产出的决策单就是下一条"调 flag"prompt 的直接输入——且方向已从"翻开"修正为"收口 action_loop + 给 semantic router 取基线"。

---

## 7. 关联文件

- 上游对照报告：[2026-05-30-plan-vs-code-reconciliation.md](2026-05-30-plan-vs-code-reconciliation.md)
- 学情推断引擎计划：[2026-05-22-luban-learning-state-inference-engine-transformation-plan.md](2026-05-22-luban-learning-state-inference-engine-transformation-plan.md)
- 采分点基线：`docs/qa/2026-05-22-rubric-coverage-baseline.md`
- 钱包权威：[2026-04-19-supabase-wallet-single-authority-prd.md](2026-04-19-supabase-wallet-single-authority-prd.md)
- 上线前清单：[2026-05-25-prelaunch-readiness-checklist.md](2026-05-25-prelaunch-readiness-checklist.md)
- 关键代码入口：`deeptutor/services/experiments/cohort.py`（flag→stage 解析）、`deeptutor/services/runtime_env.py`（production 判定）、`deeptutor/services/member_console/service.py:544`（assessment repo 选择）、`deeptutor/runtime/orchestrator.py:486-505`（semantic router 默认）

---

*本单为 2026-05-30 只读核验快照。所有"建议动作"均待人工在独立"调 flag"步骤中执行；本单未改任何 flag/库/部署。*
