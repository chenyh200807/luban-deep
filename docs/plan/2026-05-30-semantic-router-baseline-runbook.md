# Semantic Router 误切率基线——现状核验 + 取基线 runbook + 决策门槛

| 字段 | 值 |
| --- | --- |
| 日期 | 2026-05-30 |
| 类型 | Diagnosis + Runbook（只读核验产物） |
| 状态 | v1 |
| 核验方式 | **纯只读**：生产 Supabase SELECT、阿里云 `/root/deeptutor` 只读（含 `data/user/chat_history.db` 以 `mode=ro` 打开）、本地 codegraph/grep/Read。**未翻 flag、未写库、未部署。** |
| 凭证 | `FastAPI20251222/.env` 的 `DB_URL`（生产 pooler，明文未打印）；阿里云 SSH 只读 |
| 纪律 | AGENTS §5 根因 + §3.7（阿里云写边界，本任务全程只读） |
| 上游 | [2026-05-30-prod-state-and-flag-flip-decision.md](2026-05-30-prod-state-and-flag-flip-decision.md) §5（#8） |

---

## 0. 执行摘要

**现状判定：primary 决策"部分被记录、可只读取数"——绝对误切率基线今天就能取（Path A，不动 flag）；rollout report 的自动 disagreement 今天算不出（需 shadow，而开 shadow 会把实际路由退回 legacy）。**

1. **路由什么**：semantic router 根据「用户这句话与当前活跃学习对象的关系」决定 `next_action` → route ∈ {`deep_question`（出题/批改）, `chat`/`tutorbot`（通用）}。误切 = 把通用问答路进出题/批改，或把答题/改答路进通用聊天 → 答非所问 / 误判分。
2. **决策已被记录（可只读查）**：生产 SQLite `turn_events.metadata_json` 实测有 **313 条 `turn_semantic_decision`**（含 `next_action`/`relation`/`confidence`/`reason`）。`next_action → route` 是确定性映射，可派生路由；可 join 用户消息做对错标注。→ **Path A 纯只读可行。**
3. **完整 router 遥测是 Langfuse-only**：`semantic_router_mode`/`selected_capability`/`shadow_route` 在 SQLite 实测 **0 条**（仅发往 Langfuse trace）。且 prod `SHADOW_MODE=off` → 全网 `shadow_route` 为空 → **rollout report 的 `shadow_disagreement_rate` 当前无数据可算。**
4. **开 SHADOW_MODE 不是纯观察**：实测代码 `_select_capability_after_lifecycle`（orchestrator.py）——shadow 模式下 **legacy 老路由变成实际主用（`_select_legacy_capability`）、新语义路由降级为影子 preview**。所以开 shadow = 把当前线上路由**退回 legacy** + 记录新路由影子。是"安全回退+测量"，但**改变了当前实际行为**，且它给的是"新 vs 老分歧率"≠"对错率"。

**推荐：先走 Path A（只读抽样标注，拿绝对误切率），不动 flag。** 仅当需要自动化对比 / 或决定干脆回退 legacy 时才走 Path B。

---

## 1. §5 现状摸清（证据）

### 1.1 判决链（codegraph）
- `resolve_turn_semantic_decision`（semantic_router.py:594）→ `build_turn_semantic_decision`（:447）→ 产出 decision dict `{relation_to_active_object, next_action, allowed_patch, confidence, reason, target_object_ref}`。
- `semantic_route_for_decision`（:478）/ `turn_semantic_decision_route`：`SEMANTIC_ROUTE_BY_NEXT_ACTION[next_action]` → route。
- orchestrator `_select_capability_after_lifecycle`（orchestrator.py:248-320）：
  - **先过 lifecycle**（question_review/practice_generation 直接 → deep_question，mode=`question_lifecycle`，semantic router 不介入）；
  - 余下才进 semantic router：`primary`（新路由实际决策，`shadow_route=""`）/ `shadow`（**legacy 实际决策 + 新路由影子**）/ `disabled`（legacy）。

### 1.2 决策记录在哪（SQLite + Langfuse 实测）
| 字段 | SQLite `turn_events` | 说明 |
| --- | --- | --- |
| `turn_semantic_decision`（含 confidence/next_action/reason） | ✅ **313 条** | 可只读查、可派生 route、可 join 消息标注 |
| `semantic_router_mode` / `selected_capability` / `shadow_route` | ❌ **0 条** | 仅 turn_runtime.py:4461-4482 发往 Langfuse trace |
| `question_lifecycle_decision` / `effective_response_mode` 等 result 摘要 | ✅ | result-type event metadata |

- 持久化后端 = `SQLiteSessionStore`（`data/user/chat_history.db`，prod 实测 302MB / messages=6985 / turn_events=299376）；**不在 Supabase Postgres**。
- `arr_runner` 等 observability 读 **fixture**（`semantic_router_eval_cases.json`），不读实时决策。

### 1.3 生产决策分布（只读抽样 313 条 turn_semantic_decision，2026-05-30）
```
next_action: route_to_generation 138 / route_to_grading 112 / route_to_followup_explainer 49 / hold_and_wait 14
relation   : switch_to_new_object 122 / answer_active_object 101 / ask_about_active_object 42 /
             continue_same_learning_flow 23 / uncertain 14 / revise_answer_on_active_object 11
confidence : n=313 min=0.00 p50=0.90 p90=0.95 max=1.00 ; <0.4 共 14 条 (4%)
```
**信号**：路由整体高置信（p50=0.90），低置信(<0.4)仅 4%。这 14 条低置信 + 14 条 `hold_and_wait`/`uncertain` 是误切高风险子集，标注时必查。`route_to_grading`(112) 误切伤害最高（把非作答误判分），加权。

---

## 2. rollout report 实测（`scripts/report_semantic_router_rollout.py`）

- **算什么**：只统计 `semantic_router_mode=="shadow"` 的记录，用 `selected_capability`(legacy 实际) vs `shadow_route`(新路由影子) 差异算 `shadow_disagreement_rate` + `deep_question_to_chat_disagreements` + confidence 桶 + p95 延迟。
- **要什么输入**：一个 **JSONL trace 导出文件**（每行含上述字段；不连实时源）。
- **只读跑实测**：用 2 行合成样本跑通，输出正确（`shadow_disagreement_rate` 等字段齐全）。
- **当前能不能出真基线**：**不能**。prod `shadow_route` 全空（shadow off），且这些字段不在 SQLite（Langfuse-only）。要么开 shadow 产数据（Path B），要么不用这个脚本、走 Path A 的绝对标注。

---

## 3. 取基线两条路 + 推荐

### Path A（推荐）——只读 SQLite 抽样 + 标注，**不动 flag、不改行为**
直接测**绝对误切率**（router 决策对不对），而非"新老分歧"。

**步骤（全只读）**：
1. 只读导出样本（阿里云，`mode=ro` 不锁写者）：从 `turn_events`（`turn_semantic_decision` 非空）取全部 313 条，join `turns.turn_id → session_id → messages(role='user', 同轮 content)` 拿到「用户消息 + 当时 active_object + 决策(next_action/route/confidence/reason)」。`next_action→route` 用 `SEMANTIC_ROUTE_BY_NEXT_ACTION` 派生。
2. 分层抽样：**必含** 14 条 `<0.4` + 14 条 `hold_and_wait`/`uncertain` + 全部 `route_to_grading`(112，高危)；其余按比例抽到 ≥150 条。
3. 标注对错：人工或 LLM-judge 对每条判「该轮真实意图 vs 路由结果是否匹配」（4 类标签：correct / wrong_to_deep_question / wrong_to_chat / ambiguous）。
4. 算基线：`mis_route_rate = wrong / labeled`；分 route 报（尤其 grading 误判率）；记低置信段误切占比。
5. 产出 `docs/qa/2026-05-XX-semantic-router-baseline.md`。

**优点**：零行为改动、零 flag、直接测对错。**代价**：需标注工时 + 写一次性只读导出脚本。**join key 已验证**：`turn_events.turn_id`、`messages.session_id`、`turns` 桥接均在 schema 内。

### Path B（需自动化对比 / 或想顺便回退 legacy 时）——开 SHADOW_MODE
> ⚠️ 实测语义：开 shadow = **legacy 变实际主用 + 新路由降影子**。这是行为改动（线上路由退回 legacy），不是纯观察。给的是"新 vs 老分歧率"≠对错率。

| 步 | 动作 | 授权 | 验证 | 回滚 |
| --- | --- | --- | --- | --- |
| 1 | 备份 `cp /root/deeptutor/.env .env.bak.20260530-sr` | 写边界内 | `ls .env.bak*` | 删备份 |
| 2 | 设 `DEEPTUTOR_SEMANTIC_ROUTER_SHADOW_MODE=on`（**只加这一行**；`_ENABLED` 不动） | 写边界内 | `grep SHADOW_MODE .env` | 从 .bak 还原/删该行 |
| 3 | `cd /root/deeptutor && docker compose up -d --force-recreate <api>`（`docker restart` 不重载 env_file） | 写边界内 | 容器 healthy；新 turn 的 Langfuse trace `semantic_router_mode=shadow` | 还原 .env + 再 `up -d --force-recreate` |
| 4 | 观察期跑流量（注意此间学生吃 **legacy** 路由）→ 从 Langfuse 导出 JSONL → `python scripts/report_semantic_router_rollout.py export.jsonl` 出 `shadow_disagreement_rate` | — | 报告产出 | 关 shadow 即恢复新路由 primary |
| 5 | 读完基线立即关 shadow（步 2 反向）回到 primary | 写边界内 | `semantic_router_mode=primary` | — |

**风险**：观察期线上是 legacy 行为；disagreement 高不代表新路由错（可能 legacy 错）。所以 Path B 适合"想顺便确认回退 legacy 是否更稳"或"要自动化数值"，不适合单纯判新路由对错。

---

## 4. 决策门槛（客观判据）

基于 Path A 的**绝对误切率**（首选）：

| 误切率 (mis_route_rate, labeled ≥150) | 判定 | 动作 |
| --- | --- | --- |
| ≤ 2% 且无单类系统性误切 + grading 误判率 ≤1% | primary 可信 | **维持** primary ON / scope=all，归档基线 |
| 2%–5% | 局部不稳 | **缩 scope** 到 `question_and_guide`（减小新路由作用面），重测 |
| > 5%，或 grading 误判率 >2%，或某类系统性误切 | primary 不可信 | **回退**：`SHADOW_MODE=on`（legacy 主用）或 `ENABLED=off`，修因后再放量 |

辅助（Path B 的分歧率，仅参考）：`shadow_disagreement_rate > 15%` 说明新老路由大面积不一致，需人工抽查谁对——高分歧本身不判罪，但触发必须标注。

低置信兜底：当前 `<0.4` 仅 4%，可作为持续监控线——若该比例随版本上升，是 router 退化早警。

> 阈值 2%/5% 为内测(<100 DAU)起步建议值，可据首轮标注校准；核心是**先有绝对误切率，再谈维持/缩scope/回退**，不要在零数据下让主裁判继续裸奔。

---

## 5. 关联文件 / 代码入口
- 决策单：[2026-05-30-prod-state-and-flag-flip-decision.md](2026-05-30-prod-state-and-flag-flip-decision.md)（#8）
- 代码：`deeptutor/services/semantic_router.py`（`resolve_turn_semantic_decision:594`/`build_turn_semantic_decision:447`/`semantic_route_for_decision:478`）、`deeptutor/runtime/orchestrator.py:248-320`（primary/shadow/disabled + 默认值 :486-505）、`deeptutor/services/session/turn_runtime.py:4461-4482`（router 遥测→Langfuse）、`deeptutor/services/session/sqlite_store.py:851-879`（turn_events/messages schema）、`scripts/report_semantic_router_rollout.py`（shadow-only disagreement）
- 取数面：阿里云 `/root/deeptutor/data/user/chat_history.db`（只读 `mode=ro`；`turn_events.turn_semantic_decision` 313 条）

---

*本 runbook 为 2026-05-30 只读核验快照。所有 ops 步骤待人工在独立"调 flag/部署"步骤执行；本单未改任何 flag/库/部署。*
