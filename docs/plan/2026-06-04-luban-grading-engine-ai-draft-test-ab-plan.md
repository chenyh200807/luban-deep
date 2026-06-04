# 鲁班评分引擎 AI-Draft 测试环境 A/B 方案 + 最小纵切实施计划

> Status: `Proposed v0`（2026-06-04）。**测试环境 / AI-Draft / shadow / candidate_only —— 不进 production runtime authority、不改 `CaseGradingSkillKernel`、不接 RAG 进评分、不新增第二套 learner memory、不新增第二套 eval 子系统、不把 high_risk_review 当正确、不把 QWK 偷换成正式 gate、不碰 BI/billing。**
> 前置证据：`docs/plan/2026-06-03-luban-deepseek-production-shadow-v0-plan.md`（Phase 2.2）、`docs/plan/2026-06-04-luban-grading-metric-governance-qwk-plan.md`、`artifacts/luban_consensus_gold/selective_abstention_qwk_20260604/`。

## Task A：架构边界审计（已读代码核验）

### A.1 当前真实学生答案提交/批改链路在哪
- **生产热路径**：学生作答 → 统一聊天入口 `/api/v1/ws`（`deeptutor/api/routers/unified_ws.py`）→ capability + TutorBot loop → `deep_question`（`deeptutor/capabilities/deep_question.py`）→ **`deeptutor/services/construction_grading/deep_question_adapter.py:64` 调 `CaseGradingSkillKernel().grade(...)`**（案例题确定性 source-grounded 批改 authority）。
- ⚠️ 实际存在**两条 grading 路径**，本计划须区分清楚：(1) **确定性 kernel**（`deep_question_adapter`→`case_kernel.grade`，source-grounded 关键词匹配，案例题 source-of-truth）；(2) **LLM `submission_grader_agent`**（`deeptutor/agents/question/agents/submission_grader_agent.py`，`BaseAgent`，prompt `grade_submission`，TutorBot/agent 路径上的 LLM 评分，**不调 kernel**）。AI-Draft 不替换二者中任何一个。
- **可见链路 QA harness**（非生产）：`POST /api/v1/learning-brain/harness-case-grading`（`deeptutor/api/routers/learning_brain.py:223,247,252`），`_qa_enabled()` 门控，docstring 明确「owns no grading or memory truth … production grading goes through the capability + TutorBot loop, not this endpoint」。它已串起 grade → writeback → synthesis 真实 authority，是 AI-Draft 的自然挂载点。

### A.2 当前案例题批改 authority 是谁
- **案例题 source-grounded 批改 authority = `CaseGradingSkillKernel.grade()`**（`case_kernel.py:27`），生产由 `deep_question_adapter.py:64` 调用；harness 由 `learning_brain.py:252` 调用。
- ⚠️ 关键事实：**它是确定性关键词匹配器**（`_official_keyword_matches`，`status="full" if matched else "miss"`，无 partial、无 LLM）。authority 优先级：`grading_key.scoring_points` > `grading_rubric` > projected > open_skill。
- 我们离线验证的 **DeepSeek Arm2 semantic grader 是另一套(LLM)候选,绝不能替换 kernel,也不并入 `submission_grader_agent`** —— 否则就制造了第二套 production authority。

### A.3 AI-Draft 候选链路应挂在哪,才不制造第二套 authority
- **挂在 harness 层(QA-gated),作为 kernel.grade() 的并列 shadow/draft,不进 capability/TutorBot 生产 loop。** 复用现有 `harness-case-grading` endpoint 加 `mode=ai_draft` 分支(或新增仅测试用 `harness-case-grading-ai-draft` 子 endpoint / internal script)。
- AI-Draft 只产出 **draft 结果 + 对比**,不写入任何 runtime 评分权威,不被 `submission_grader_agent` 调用。

### A.4 输出如何标记 draft/shadow/candidate_only
- 顶层固定字段:`authority: "ai_draft_shadow"`、`candidate_only: true`、`not_production_grade: true`、`protocol_version: "arm2_semantic_protocol_v0"`、`metric_gate: {legacy: "WEAK-GO", metric_v2_qwk: "STRONG-candidate(candidate_only)"}`。
- 每个采分点:`auto_certified: bool`、`high_risk_review: bool`(true 时 `auto_certified=false`)。

### A.5 high_risk_review 存哪,是否要新表
- **不需要新表。** 写回复用现有 `learner_memory_events`(`memory_kind="learning_evidence"`),payload 由 `build_learning_evidence_payload()` 产出(`deeptutor/services/construction_grading/learning_evidence.py:18`),写入由 `write_grading_error_events()`(`writeback.py:17`)。
- high_risk_review 作为 **payload 内字段** 标注(`high_risk_review=true` 的点 `auto_certified=false`、**不提升 mastery claim**),不需独立容器。

---

## Task B：冻结 AI-Draft 评分协议 v0

| 项 | 冻结值 |
|---|---|
| model | DeepSeek-V4-flash |
| protocol | Arm2 `list_rule_semantic_protocol`（list_rule 可按事实覆盖给 partial，**exact_required 仍逐字、严格隔离**） |
| structured JSON schema | 固定 schema（point_id/hit/score/evidence_span/rationale/policy_type/high_risk/needs_policy_review/unsupported） |
| evidence_span 守卫 | 必须逐字出现在 student_answer，否则 `unsupported=true`（fail-closed） |
| unsupported_positive | 硬门：必须 0；hit/partial 无合法 span 即 fail-closed |
| exact_required fallback | rationale-based：自承认近义/半术语却给正分 → high_risk_review（不改分） |
| selective abstention | tau=3.3 candidate（离线陪审分歧 + list_rule-partial + 弱 span + hedge 词排序） |
| high_risk_review 语义 | 仅表示「不自动认证」，**不等于正确**，路由离线陪审/人审 |
| metric（仅记录） | legacy raw gate 记录；metric-v2 QWK 仅测试诊断、`candidate_only`、**不当生产 gate** |

冻结证据：485 上 Arm2 auto_hit 0.9493/踩字 0/unsup 0；Arm2+弃权 high_risk 3.32%/auto_hit 0.9632/QWK 0.9618/硬门全 0。

---

## Task C：最小纵切（不直接大改 runtime）

- **1 个入口**：复用 `POST /api/v1/learning-brain/harness-case-grading` 加 `mode=ai_draft`（QA-gated）；或新增 internal script `scripts/run_luban_ai_draft_grading.py`（仅测试）。
- **1 个题目范围**：先限 20 题 golden（`luban_case_grading_golden_v1`）或 1-3 个真实题。
- **1 个输出 surface（draft 视图）**：`total_score / point_results[{hit,partial,miss, score, evidence_span, rationale, high_risk_review, auto_certified, typed_policy}] / learning_evidence_payload_preview`，顶层带 A.4 的 draft 标记。
- **1 个写回策略**：
  - **默认 dry_run**：只调 `build_learning_evidence_payload()` 出 preview，**不调** `write_grading_error_events()`（不写 learner_memory_events）。
  - `writeback=true`：调 `write_grading_error_events()`（复用现有路径，唯一写回口）；**high_risk_review 点不得提升 mastery claim**（payload 内标注，writeback 侧过滤 success-event）。

### 性能/成本边界
| 步骤 | 同步/异步 | 说明 |
|---|---|---|
| DeepSeek-flash 逐点批改 | 同步（测试环境可接受） | 单题 1 次调用 |
| span guard / fallback / abstention | 同步（确定性、<5ms） | 纯本地 |
| learning_evidence payload preview | 同步 | 纯函数 |
| writeback（可选） | 异步可选 | 复用现有 append_memory_event |
| selective abstention 的陪审信号 | **离线预生成**（测试 reference），不在热路径 | 真实热路径用 model-observable 代理 |

- first visible response 目标：≤ DeepSeek 单题延迟（实测 ~5-30s，测试环境可接受；生产另议）。
- p95 目标：≤ 35s（测试态，含 retry）。
- token 成本：~单题 2-8k completion tokens（DeepSeek-flash，便宜）。

---

## Task D：A/B 测试设计（测试环境，不等生产）

- **A 组**：当前 baseline —— `CaseGradingSkillKernel.grade()`（确定性关键词匹配）。
- **B 组**：鲁班 AI-Draft v0（DeepSeek Arm2 semantic + guards + abstention）。

| 指标 | 来源 |
|---|---|
| point_hit_agreement vs reference | 4 模型 consensus gold（**标注非真人 gold**）/ 若有 ledger/human 则并列 |
| QWK | metric-v2 诊断 |
| unsupported_positive | 硬门（必 0） |
| high_risk_review ratio | 目标 ≤10% |
| evidence_span found rate | span guard |
| teacher override rate | teacher-review 面板（若有真人） |
| student appeal rate | 申诉队列 |
| latency p50/p95 / token cost | 运行时记录 |
| 可解释性评分 | 教师/内测打分 |
| Learning Brain 写回可用率 | payload preview 合法率 |

**样本量与阶段门**：
1. **smoke**：20-50 份真实/模拟答案 —— 验证管线跑通、schema 合法、span guard 0 漏、写回 preview 可用。
2. **shadow**：100-300 份 —— 算 A/B 指标，4 模型 consensus 作 reference（标注非真人）。
3. **go/no-go 门槛**（测试 A/B，非生产）：B 组 unsupported=0 AND exact_major=0 AND high_risk≤10% AND（QWK ≥0.85 candidate）AND evidence_span_found ≥0.98 → 进 teacher-review pilot；否则回炉。
- 无真人老师时允许 4 模型 consensus gold 作 shadow reference，**必须标注非真人、不宣称生产准确率**。

---

## Task E：文件级实施清单（本轮先不大改，仅文档/脚本/测试）

### 新增
| 文件 | 职责 |
|---|---|
| `docs/plan/2026-06-04-luban-grading-engine-ai-draft-test-ab-plan.md` | 本计划（已建） |
| `scripts/run_luban_ai_draft_grading.py`（实现轮）| AI-Draft 协议封装：调 DeepSeek-flash + span guard + fallback + abstention，产出 draft 视图 + payload preview；默认 dry_run |
| `tests/scripts/test_luban_ai_draft_grading.py`（实现轮）| 断言:draft 标记齐、unsupported=0 fail-closed、high_risk 不 auto_certified、dry_run 不写库、复用 learning_evidence payload |

### 修改（实现轮，需先确认）
| 文件 | 改动 | 边界 |
|---|---|---|
| `deeptutor/api/routers/learning_brain.py` | harness endpoint 加 `mode=ai_draft` 分支(QA-gated) | 不动 kernel、不进生产 loop |
| `deeptutor/services/construction_grading/schema.py` | 仅加 draft 输出 dataclass(可选) | 不改 kernel 评分逻辑 |

### 不碰
- `deeptutor/services/construction_grading/case_kernel.py`（grading authority，绝不改）
- `deeptutor/services/construction_grading/writeback.py` / `learning_evidence.py`（写回路径，复用不改逻辑）
- capability/TutorBot 生产 loop、`deep_question_adapter.py`（kernel 生产调用方）、`submission_grader_agent.py`（LLM 评分 agent）、`unified_ws.py`
- consensus gold 产物、`CaseGradingSkillKernel` runtime authority、BI/billing、第二套 learner memory/eval

### 测试命令
```
python -m pytest tests/scripts/test_luban_ai_draft_grading.py \
  tests/scripts/test_luban_selective_abstention.py \
  tests/scripts/test_luban_grading_metric_qwk.py -q
```
### 回滚
- AI-Draft 全部 QA-gated（`_qa_enabled()`）；关 flag 即下线，不影响生产。
- dry_run 默认，无写库副作用；`writeback=true` 仅复用现有 append_memory_event，可按 source_id 清理。

---

## 实施状态（2026-06-04，最小纵切已落地）

- ✅ `scripts/run_luban_ai_draft_grading.py`：DeepSeek Arm2 semantic + span guard(fail-closed) + exact_required rationale fallback + selective-abstention(model-observable proxy) → draft 视图 + `learning_evidence_payload_preview`（**复用现有 `build_learning_evidence_payload`**），**默认 dry_run、无写库**。draft 固定标 `authority=ai_draft_shadow / candidate_only / not_production_grade`。
- ✅ `tests/scripts/test_luban_ai_draft_grading.py`：draft 标记、span guard fail-closed→unsupported、high_risk 不 auto_certified、total 排除 high_risk/unsupported、payload preview 复用现有 builder、dry_run。
- ✅ smoke 20 题 golden（dry_run）跑通：span guard 实捕 unsupported、high_risk 实路由、`learning_evidence_payload_preview` 由现有 schema 产出。产物 `artifacts/luban_consensus_gold/ai_draft_test_20260604/ai_draft_smoke_results.json`。
- ⏸️ 未做（按红线，留后续单独 PR）：harness `learning_brain.py` 的 `mode=ai_draft` 分支（需在 QA-gated 下小心接线，本轮先以 internal script 形式交付，不碰 router 生产代码）；`writeback=true` 真写（复用 `write_grading_error_events`，需 learner_state_service，留 teacher-review pilot 阶段）。

## Task F：交付结论

1. **提交/批改链路审计**：生产走 `/api/v1/ws` → capability/TutorBot → `deep_question` → `deep_question_adapter.py:64` 调 `CaseGradingSkillKernel.grade()`（确定性 source-grounded 关键词匹配，案例题 authority）；另有 LLM `submission_grader_agent`（独立路径，不调 kernel）；QA 可见链路走 `harness-case-grading`（非 authority）。
2. **AI-Draft 架构**：`harness-case-grading?mode=ai_draft`（QA-gated）→ DeepSeek Arm2 semantic + span guard + exact_required fallback + selective abstention → draft 视图 + learning_evidence payload preview（默认 dry_run）→ 可选 `writeback=true` 复用 `write_grading_error_events`。**与 kernel 并列 shadow,不替换、不进生产 loop。**
3. **是否需要新表**：**不需要。** 复用 `learner_memory_events`（memory_kind=learning_evidence）；high_risk_review 作 payload 字段,代码证据充分。
4. **A/B 方案**：A=kernel 确定性,B=AI-Draft;smoke 20-50 → shadow 100-300,4 模型 consensus 作非真人 reference;门槛见 Task D。
5. **最小纵切清单**：见 Task C/E。
6. **是否可进入代码实现**：**GO（仅限测试环境 AI-Draft / QA-gated / 默认 dry_run）。** 边界清晰、复用现有写回、无新表、可回滚、不碰生产 authority。
7. **下一个执行 prompt**：实现 `scripts/run_luban_ai_draft_grading.py` + harness `mode=ai_draft` 分支 + `tests/scripts/test_luban_ai_draft_grading.py`,先 smoke 20 题 golden（dry_run），出 draft 视图与 payload preview;严守红线。
