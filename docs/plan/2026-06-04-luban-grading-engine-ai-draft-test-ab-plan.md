# 鲁班评分引擎 AI-Draft 测试环境 A/B 方案 + 最小纵切实施计划

> Status: `Proposed v0`（2026-06-04）。**测试环境 / AI-Draft / shadow / candidate_only —— 不进 production runtime authority、不改 `CaseGradingSkillKernel`、不接 RAG 进评分、不新增第二套 learner memory、不新增第二套 eval 子系统、不把 high_risk_review 当正确、不把 QWK 偷换成正式 gate、不碰 BI/billing。**
> 前置证据：`docs/plan/2026-06-03-luban-deepseek-production-shadow-v0-plan.md`（Phase 2.2）、`docs/plan/2026-06-04-luban-grading-metric-governance-qwk-plan.md`、`artifacts/luban_consensus_gold/selective_abstention_qwk_20260604/`。
> 模型分工：当前打造期以 **Best-Quality 4-model jury** 作为质量上限；DeepSeek-fast 只承担 `production-cost grader` 候选和蒸馏目标。DeepSeek 单模型 gate 只控制未来自动写权，不阻塞 Best-Quality QA、teacher-review、GBrain/Learning Brain pack 与学员证据体验。

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

## Teacher-Review Writeback Pilot 已接入（2026-06-04）

- ✅ **fat skill**：`deeptutor/services/construction_grading/teacher_review_writeback.py`（Stream C）—— 把 QA 面板老师复核 JSON 转成 teacher-final `CaseGradingResult`，**复用现有 `build_learning_evidence_payload` / `write_grading_error_events`，无新表/无第二套 memory/无新 builder**。override=更高 authority；high_risk/unsupported 未复核→降权 never mastery；teacher override 可升降。
- ✅ **薄适配**：router `POST /api/v1/learning-brain/harness-case-grading-review`（QA-gated，默认 dry_run / writeback=false；writeback 需 QA+teacher_reviewed=true 才走现有写回；teacher_score 越界/非法 hit → 400）；前端「Dry-run 写回预览」按钮展示 override/confirm/mastery/降权摘要 + payload 摘要 + 明确「未真正写库」。**写回规则零前端/最小 router**。
- ✅ **真实 smoke**（Q10/S2 exact_required）：老师 override P5/P6→miss(踩字)、confirm 清洁 hit → **mastery=P1/P2**，5 个 gap 进 learning_evidence，**dry_run 未写库**（无 writeback_count）。产物 `artifacts/luban_consensus_gold/teacher_review_writeback_pilot_20260604/`。
- 硬规则：AI-Draft 单独绝不写库；teacher-reviewed 才是 Learning Brain 写入 authority；high_risk/unsupported 不自动 mastery；dry_run 不跳过；不改 kernel/RAG/runtime/新表。

## Best-Quality 四模型协作模式已接入（2026-06-04）

- ✅ **fat skill**：`deeptutor/services/construction_grading/best_quality_ai_draft.py` —— GPT5.5+Opus4.8+DeepSeek-V4+Qwen3.7 逐采分点投票 + policy-aware 裁决（exact_required 取严踩字 / list_rule 语义多数 partial / 硬分裂 → high_risk），**复用 ai_draft_shadow guards 不复制规则**。本轮裁决缓存的真实 4-model 预测（`source=cached_4model_485`）；缺则 **fail closed（503 best_quality_unavailable），不用 DeepSeek 冒充**。
- ✅ **薄适配**：router `mode=ai_draft` 加 `engine`（默认 `deepseek_fast` 不变 / `best_quality_4model` 走新服务）；前端加引擎切换 + 逐点 model_votes/裁决理由展示 + export 带 engine/authority/model_votes。**评分逻辑零前端/零 router**。
- ✅ **真实 smoke**：Q10/S2（exact_required 边界）best_quality 在 P4/P5/P6 **裁决取严纠正单模型放水**（DeepSeek/Opus partial/hit → 裁决 miss）；Q5/S3（list_rule）DeepSeek-fast 长题解析失败而 best_quality 稳健产出语义 partial。两样本 bad_certified=0。浏览器截图 `artifacts/luban_consensus_gold/best_quality_ai_draft_20260604/best_quality_panel_smoke.png`，对比 `comparison_deepseek_vs_best_quality.json` + `FINDING_best_quality_ai_draft_20260604.md`。
- 仍 QA-gated / dry_run / writeback=false / 不改 kernel / 不接 RAG / 不新增表 / 不新增 endpoint。**best_quality 是打造期最高能力，不是低成本生产模式；DeepSeek 仍是 production-cost 单模型候选，而不是整条 Learning Brain 的 blocker。**

## runtime v0 并行推进包（2026-06-04，能力补全 + 题目级 artifact + 写回预案 + 可复现 smoke）

四条线并行交付（dynamic workflow，互不冲突的独立文件），全部 TDD、确定性、无 live provider 依赖；合并测试 `69 passed`、`construction_grading` 全量 `100 passed` 无回归。

- ✅ **Stream A — best_quality 能力测试**：`tests/services/construction_grading/test_best_quality_ai_draft.py`（11 测试）。合成 `model_outputs` 在进程内验证四模型裁决：四模一致→该 label（score=同 label 均值）；exact_required GPT 放水/Opus 严/DeepSeek partial/Qwen miss → **取严裁 miss**（model_votes/adjudication_reason 保留）；2-2 硬分裂→high_risk_review 且不 auto_certified；list_rule 分歧→合理 partial；unsupported span→fail-closed；pending_review_score 携带真实非 0 且不计入认证分；schema 与 AI-Draft 兼容；`load_cached_4model_predictions` 陪审<3 → `BestQualityUnavailable`。
- ✅ **Stream B — 题目级 QuestionGradingArtifact 发布层**：`deeptutor/services/construction_grading/question_grading_artifacts.py`（+测试 10 个）。`build_question_grading_artifact(case_id)` 把 golden `gold_scoring_points` + 缓存 typed-policy packet 投影成 runtime 可读 artifact（`version_id=qga_v0_20260604`，每点带 policy_type/max_score/required_terms/list_rule/calculation_spec/penalty_rule/source_refs/source_status/auto_certifiable/knowledge_point_refs）。**20 题 97 点全可读**；未知 case_id → `artifact_missing`；强教材锚点 69 点 `source_status=ok·auto_certifiable=true`，无强源 28 点 `missing_or_weak·auto_certifiable=false` 且**绝不伪造教材锚点**；不改库。policy 分布：exact_required 40 / list_rule 31 / calculation 17 / high_risk_review 4 / figure_label 3 / penalty_rule 2。
- ✅ **Stream C — teacher-review 写回预案（dry-run 优先）**：`deeptutor/services/construction_grading/teacher_review_writeback.py`（+测试 9 个）。`build_teacher_review_writeback(review_json, *, dry_run=True, learner_state_service=None, user_id=None)` 把 QA 面板 review JSON 纯函数转换成**现有** `build_learning_evidence_payload`，**不造第二套 memory、不新增表**。权威规则：override→teacher 覆盖 AI 且可把 high_risk/unsupported 升为 mastery；reject→落 miss 不 mastery；confirm→AI draft 成立；high_risk/unsupported（非 override）降权 mastery_eligible=False 且强制 miss/0、并发 E03 错因事件。默认 dry_run 不触 DB（即使传入 service）；仅 `dry_run=False` 且传入 service（测试环境）才委托现有 `write_grading_error_events`。
- ✅ **Stream D — Best-Quality vs DeepSeek-Fast 确定性 smoke**：`scripts/run_luban_best_quality_smoke.py`（+测试 6 个）。**确定性复现**并把样本从 2 扩到 **5（覆盖 exact_required/list_rule/calculation/penalty_rule/figure_label 5 类）**：best_quality=对缓存 4-model 预测裁决（`cached_4model_485`），deepseek_fast=同源 deepseek_v4_flash arm 喂 `build_ai_draft`（`cached_deepseek_v4_flash_485`），**全程不调 live**。验收：best_quality 在 4 个 exact_required 点取严纠正单模放水、6 个 list_rule 语义 partial、**bad_certified=0**、unsupported（Q7-1A431000/S1 P2）**fail-closed**、字节级可复现。产物刷新：`smoke_results.json` / `comparison_deepseek_fast_vs_best_quality.json` / `FINDING_best_quality_ai_draft_20260604.md`（panel 截图 `best_quality_panel_smoke.png` 沿用）。

> 红线全部守住：未改 `CaseGradingSkillKernel`、未新增表、RAG 未进评分 authority、未接 production runtime、未重跑 485/QWK/consensus 大实验；缺 4-model 预测 fail-closed 不冒充。下一步并行推进：**(a) teacher-review writeback pilot**（用 Stream C 在测试环境 `dry_run=False`）和 **(b) 把 Best-Quality 能力蒸馏到 DeepSeek production-cost runtime**。其中 (b) 只影响未来自动写权，不阻塞 (a) 与 Learning Brain/GBrain 证据链建设。

## QA 可视面板已接线（2026-06-04，teacher-review 最小闭环）

- ✅ **QA-gated 可视面板**：在现有 `GET /wechat-harness`（`render_learning_brain_harness_html`）里**薄加**「鲁班评分引擎 · AI-Draft 阅卷」面板（case_id 输入 / 答案 textarea / 运行 / 导出按钮 / 三分数 summary / 逐采分点卡片）。前端只展示，**评分理解全在 `ai_draft_shadow.py`**（thin wrapper, fat skill）。
- ✅ **后端 service 抽出**：`deeptutor/services/construction_grading/ai_draft_shadow.py`（`build_ai_draft` + 守卫 + display_status + payload preview，单一来源）；router `mode=ai_draft` 与 script 都用它，**无第二套评分规则**。
- ✅ **真实浏览器 smoke**：QA server 起 `/wechat-harness` → 输入 Q5-1A432000 + 真实答案 → 运行（真实 DeepSeek）→ 7 采分点渲染：model_draft_score 3.43 / auto_certified_score 0 / pending_review_score 3.43 / bad_certified 0；6 绿(auto_certified) + 1 黄(pending_review) + 证据高亮 `<mark>`；`dry_run=true / writeback_performed=false`；server 日志 0 次写库。截图 `artifacts/luban_consensus_gold/ai_draft_panel_20260604/ai_draft_panel_smoke.png`。
- ✅ **teacher-review 本地草稿 + 导出**：每个采分点 accept/override hit·score + note，导出 review JSON（`point_reviews[]` 含 `teacher_hit/teacher_score/teacher_note/review_action`），纯前端 local state，不写库。
- ✅ **pending_review 非 0**：面板把待复核分单列、黄色、不当 0、不当已认证；unsupported 红色危险态。

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

## QuestionGradingArtifact Registry v0 —— runtime auto-certification 发布门（2026-06-04，已落地）

> **Registry v0 是 runtime auto-certification 的发布门（admission gate）。没有 published artifact 的题目，runtime 不得进入 auto_certified 流。** 文件层、无 DB、无生产 runtime、不改 kernel、不接 RAG、不伪造 source。

- **runtime 规则（由 Registry 强制）**：
  - `question_id` 有 **published** QuestionGradingArtifact → 可进入 auto_certified 流（`auto_certification_allowed=True`）。
  - 只有 **draft / weak** artifact → 仅 AI-Draft / high_risk，**不得** auto-certify（`auto_certification_allowed=False`）。
  - **缺 artifact** → `artifact_missing`，无 auto-grading（`found=False`）。
- **schema v0**：`deeptutor/services/construction_grading/question_grading_artifacts.py` 增强（保留原投影，未重写）补 `schema_version="question_grading_artifact.v0"` / `artifact_id` / `status(published|draft|blocked)` / `status_reason` / `source_profile` / `quality_gates{has_scoring_points,has_policy_type,has_max_score,source_refs_verified_rate,auto_certifiable_point_count,unsupported_required_terms,blocked_reasons}` / `provenance{compiler_version="qga_compiler_v0",content_hash}`；每个 source_ref 带 `verified`（仅真实 textbook quote+chunk 为 `verified=True`）。
- **发布门（v0）**：结构完整（≥1 采分点，每点有 point_id/label/max_score/policy_type）→ 否则 blocked；结构完整且 ≥1 点 auto_certifiable（强 textbook 源 **且** 满足 per-policy 最小要求）→ published；结构完整但 0 点 auto_certifiable → draft。`high_risk_review` 永不 auto。
- **Registry**：`deeptutor/services/construction_grading/question_grading_registry.py`（`QuestionGradingRegistry` + `ArtifactLookupResult` + runtime helper `get_question_grading_artifact(question_id)`，**helper only，未接生产 runtime**；duplicate question_id 取最新 version_id）。
- **编译 20 题**：`scripts/build_luban_question_grading_registry_v0.py` → `artifacts/luban_grading_artifacts/registry_v0_20260604/`（`question_grading_artifacts.jsonl` / `question_grading_registry.json` / `publish_report.json` / `FINDING_*.md`）。
- **实测结果**：**published=18 / draft=2（Q15-NA, Q20-1A413000）/ blocked=0**；97 采分点，**auto_certifiable=69 / weak=28**（28 弱源点恒 `auto_certifiable=False`）；typed_policy 覆盖 93/97；**未伪造任何教材锚点**（textbook source_ref 数=强源点数=69）。
- **测试**：`tests/services/construction_grading/test_question_grading_registry.py` + `tests/scripts/test_build_luban_question_grading_registry_v0.py`（20 题生成、schema 字段、unknown→artifact_missing、draft 不可 auto / published 可、weak 恒不 auto、verified 仅真实 textbook、content_hash 稳定、最新 version 胜出、publish_report 完整）。construction_grading 全套 114 passed 无回归。
- **下一步（仅两选一）**：(1) 把同一投影扩到全量题库；或 (2) 把 Registry 门接入 AI-Draft runtime 测试链。两者都**不新增 DB 表**。

## Registry 门已接入 AI-Draft runtime 测试链（2026-06-04，已落地）

> **QuestionGradingArtifact Registry 从"产物文件"升级为 runtime 安全边界**：AI-Draft / Best-Quality 在 QA runtime 中必须先过 artifact 门，模型输出不能绕过发布门。一道题/一个点是否允许自动认证，由 *published* artifact + 点级 `auto_certifiable` 决定，不由模型决定。

- **fat-skill gate**：`deeptutor/services/construction_grading/artifact_runtime_gate.py`
  - `resolve_runtime_artifact_gate(question_id) → ArtifactRuntimeGate{artifact_found, artifact_status, artifact_version_id, auto_certification_allowed, blocked_reason, point_auto_certification}`
  - `apply_runtime_artifact_gate(draft, gate)`：只降级不升级，重算 auto/pending 聚合，`pending_review_score` 不归 0。
- **runtime 行为**：
  - `published` → 点级 auto 允许，但**仅** artifact 中 `auto_certifiable=True` 的点；weak/source-missing 点降级 `point_not_auto_certifiable`。
  - `draft` → 可出 draft，但全点不 auto，降级 `artifact_not_published`。
  - `blocked` → 全点不 auto，`artifact_blocked`。
  - `missing` → fail closed，`artifact_missing`。
- **单一规则，两引擎共用**：两引擎都过 `build_ai_draft`，gate 在 router post-hoc 应用一次（grader wrapper 签名不动）；`build_ai_draft(..., artifact_gate=)` + `best_quality_draft(..., artifact_gate=)` 透传同一 `apply`，**无第二套 gate 规则**。
- **router**：`learning_brain.py` 的 `_run_ai_draft_harness` 解析一次 gate + 应用，响应增 `artifact_gate` 块；QA 面板 `/wechat-harness` 顶部薄展示 artifact_status/version/auto_certification_allowed + 点级 `review_reason`。
- **测试**：新增 `tests/services/construction_grading/test_artifact_runtime_gate.py`（12）+ harness 5 个 router 级用例；required 链 **68 passed**、construction_grading + learning_brain api 回归 **186 passed** 无回归。
- **smoke**：`scripts/run_luban_runtime_gate_smoke.py` → `artifacts/luban_grading_artifacts/runtime_gate_20260604/`：published `Q17-1A433000` 5 点中 **2 auto / 3 降级**、draft `Q20-1A413000` **0/9 auto**、missing **0/2 auto**，三例 `bad_certified=0`、pending 全保留。

### FINDING（11 问回答）

1. registry gate 是否已接入 AI-Draft？**是**（router post-hoc + `build_ai_draft(artifact_gate=)`）。
2. 是否已接入 Best-Quality？**是**（`best_quality_draft` 透传同一 gate，无重复逻辑）。
3. published / draft / missing 三类行为是否正确？**是**（smoke + 单测验证；blocked 亦覆盖 `Q15-NA`）。
4. weak point 是否不会 auto_certified？**是**（published 下非 `auto_certifiable` 点降级 `point_not_auto_certifiable`）。
5. pending_review_score 是否保留？**是**（gate 重算时 pending 吸收降级分，不归 0）。
6. unsupported / high_risk 是否仍优先？**是**（gate 只降级不升级，已有 unsupported/high_risk 不被翻成 auto）。
7. router 是否返回 artifact_gate？**是**（响应顶层 `artifact_gate`）。
8. 是否没有新增表？**没有**。
9. 是否没有改 kernel / RAG / production runtime？**没有**（gate 不引用 kernel/RAG，仅 QA harness）。
10. 测试输出：required 链 68 passed；回归 186 passed。
11. 下一步只能二选一：(1) 扩展 Registry 到全题库；(2) 接真实答题链路 runtime test。

> 停止条件均未命中（未需新表 / 未改 kernel / 未让 RAG 进评分 / 未接 production runtime / registry 20 题可运行 / gate 规则只此一套，未复制到两引擎）。

## 真实答题链路 runtime shadow test（2026-06-04，ready-to-wire，未硬接生产）

> **目标**：证明鲁班评分引擎能消费**真实 deep_question 案例题提交 shape**，作为 shadow 附加到结果，而**不替换 legacy、不写成绩、不写 Learning Brain、不接 production runtime**。

- **真实链路审计**（`real_chain_map.md`）：`/api/v1/ws` → `TurnRuntimeManager.start_turn` → `DeepQuestionCapability` → `resolve_submission_attempt` → `_build_submission_context`/`_build_batch_submission_context` → `attach_deep_question_grading_result`（deep_question_adapter.py:96）→ **`CaseGradingSkillKernel().grade()`（唯一评分 authority）**；`_emit_grading_result`（deep_question.py:2256）在 :2425 调 `_write_grading_error_events_for_context`（唯一 LB 写）+ :2430 把 `construction_grading_result` 放进 `result_payload`。`SubmissionGraderAgent` 是**解释器**不是分数 authority。另有 `POST /api/v1/assessment/{quiz_id}/submit`（assessment/testset，非案例题 subjective authority）。
- **adapter**：`deeptutor/services/construction_grading/runtime_shadow_adapter.py` —— `build_runtime_shadow_result(question_id, student_id, student_answer, engine=deepseek_fast|best_quality_4model, registry=None, qa_shadow=True)`，消费真实 `question_followup_context` shape，查 Registry + 应用 runtime gate，输出 `authority=luban_grading_engine_shadow / not_production_grade / writeback_performed=false / teacher_review_required`。
- **fail-closed 顺序**：非 QA/test 学生（id 非 `qa_`/`test_`）→ `qa_student_required`（不跑引擎）；缺 artifact → `artifact_missing`（不跑引擎）；provider/cache 不可用 → `engine_unavailable`（不冒充其他 engine）。gate 行为继承：published→点级 auto（仅 `auto_certifiable`）、draft/blocked→全点 pending、missing→fail-closed。
- **未硬接生产**（策略 C）：直接编辑 `_emit_grading_result` 会动 production grading 热路径（命中停止条件 / 红线「不接 production runtime」）。本轮停在 **ready-to-wire**：adapter + 真实 shape integration test + `real_chain_map.md` 标注最小接线点（`_emit_grading_result` :2430 之后、QA flag 门控、只 append `luban_grading_engine_shadow` key，不碰 legacy/kernel/writeback/stream）。
- **测试**：`tests/services/construction_grading/test_runtime_shadow_adapter.py`（published 出 shadow / draft 不 auto / missing 不跑引擎 / 非 QA 学生拒绝 / best_quality 不可用 fail-closed / 不调 kernel·RAG·writeback）；required 链 **55 passed**、construction_grading + learning_brain api 回归 **189 passed** 无回归。
- **smoke**：`artifacts/luban_consensus_gold/runtime_shadow_test_20260604/`（`real_chain_map.md` / `shadow_smoke_results.json` / `FINDING_runtime_shadow_test_20260604.md`）：published 出 point_results、draft 全点 pending(auto=0)、missing `artifact_missing` 不跑引擎，三例 `writeback_performed=false`。
- **下一步（仅两选一）**：(1) 开 QA 用户真实提交 runtime shadow 小批（接 `_emit_grading_result` QA-flag）；或 (2) 扩展 Registry 到全题库。

> 红线全守：shadow 非正式成绩、不破坏 legacy、artifact gate 控自动认证、teacher-final 控 LB 写入、未复核 AI-Draft 不写 LB、未把 fake integration 说成真实 DB（本轮明确**未**写库、**未**接 route）。

## QA/test 真实链路接线已落地（2026-06-04，QA-gated，默认 off）

> 上一轮停在 ready-to-wire；本轮把 shadow **真正接进** deep_question 真实链路，QA-gated、默认 off、legacy 字节级不变。

- **接线点**：`deep_question._emit_grading_result`（deep_question.py），在 legacy `result_payload["construction_grading_result"]` 之后调一行薄 wrapper `_maybe_attach_runtime_shadow(context, graded_context, result_payload)`。
- **flag**：`context.metadata["grading_engine_runtime_shadow"]`（或 `config_overrides` 同名）为真才启用；引擎 `grading_engine_runtime_shadow_engine`（默认 `deepseek_fast`）；student_id 必须 `qa_`/`test_` 开头（否则 adapter 返回 `qa_student_required` 不跑引擎）。**flag 缺省 → 完全 no-op，legacy payload 字节级不变。**
- **thin wrapper**：wrapper 只读 flag + question_id/student_id/student_answer，调 `build_runtime_shadow_result(...)`，把结果 append 到 `luban_grading_engine_shadow`；任何异常 fail-closed（`engine_unavailable`），legacy 永远返回。**零评分规则在 route/capability 层**（全在 `runtime_shadow_adapter` fat skill）。
- **不碰**：legacy `construction_grading_result` 不改、不调 kernel、不写 DB/Learning Brain（`writeback_performed=false`，只 `learning_evidence_payload_preview`）、RAG 不进评分、无新 endpoint、无新表。
- **测试**：`tests/services/construction_grading/test_runtime_shadow_integration.py`（8：no-flag→无 shadow key·legacy 不变 / flag+QA→shadow 出·positive 有 evidence_span / flag+非QA→qa_student_required 不跑引擎 / draft·blocked→auto=0 / missing→不跑引擎 / 引擎异常→engine_unavailable·legacy 仍返回 / 不调 kernel·writeback）；required 链 **47 passed**、construction_grading 全量 **170 passed**、deep_question 套件 20 passed 无回归。
- **小批产物**：`scripts/run_luban_qa_runtime_shadow_batch.py` → `artifacts/luban_consensus_gold/qa_runtime_shadow_batch_20260604/`（batch_inputs / legacy_outputs / shadow_outputs / legacy_comparison / FINDING）。6 样本（published 部分 auto·published exact_required·draft·blocked·missing·non-QA），**legacy flag-off vs flag-on 全样本字节相等（legacy_unchanged=True×6）**，positive 点恒有 evidence_span，writeback 全 false。
- **truth level（诚实标注）**：REAL=wire helper + flag gating + Registry + gate + legacy-untouched；SIMULATED=逐点预测为 fixture（hermetic，无 live 调用）；NOT-YET-REAL=完整 `/api/v1/ws` turn（TurnRuntime+stream+persist）——下一步用同一 flag 打真实 QA WS turn（live 引擎 + 异步 UX）+ 接 teacher 工作台。
- **下一步（仅两选一）**：(1) teacher-review 真实写回小批（shadow 已出 teacher_review_required + learning_evidence preview，teacher-final 控写入）；或 (2) 把同一 flag 接真实 QA `/api/v1/ws` live turn。

## Registry / Runtime Gate 单一权威收口（2026-06-04，已完成）

收口前 Registry 产物一度双轨（脚本默认写旧目录），现已统一为单一权威：

- **canonical 产物目录**：`artifacts/luban_grading_artifacts/registry_v0_20260604/`（`question_grading_artifacts.jsonl` / `question_grading_registry.json` / `publish_report.json` / `registry_report.json` / `FINDING_*.md`）。`scripts/build_luban_question_grading_registry_v0.py` 的 `DEFAULT_OUT` 与 `--out-dir` 默认均已改为此处。
- **superseded 产物目录**：`artifacts/luban_consensus_gold/question_grading_registry_v0_20260604/`（保留为陈旧快照，已写 `SUPERSEDED.md`，代码/脚本/文档不再当 authority）。
- **唯一 canonical 链**：`QuestionGradingArtifact Registry v0` → `ArtifactRuntimeGate` → `AI-Draft / Best-Quality` → `RuntimeShadowAdapter` → `QA/test real-chain shadow`。gate 规则只一套（`artifact_runtime_gate` 只 import registry；`build_ai_draft`/`best_quality_draft` 透传 `artifact_gate`、不复制；`runtime_shadow_adapter` 只 `resolve_runtime_artifact_gate` 消费；router 仅薄传递 + 展示 gate 状态）。
- **runtime status 单一来源**：published=18 / draft=1（Q20-1A413000 `no_auto_certifiable_points`）/ blocked=1（Q15-NA `zero_auto_certifiable_with_high_risk`）；Q17-1A433000 published；UNKNOWN artifact_missing；weak source 点恒 `auto_certifiable=False`，绝不伪造教材锚点。
- **职责边界**：artifact gate 管 auto-certification；teacher-final 管 Learning Brain 写入；二者不混（teacher-review / learning_evidence 不反向决定 artifact status）。
- 测试：指定 6 文件子集 73 passed；`construction_grading` 全量 162 passed 无回归。无新表 / 未改 kernel / RAG 未进评分 authority / 未接 production runtime。

## 全链路 e2e smoke v1 + teacher-review 真实文件后端写回（2026-06-04，已通）

> 把已分段打通的 1-4 段（真实 WS shadow / Registry·Gate / teacher-final 真实写回 / next suggestion）串成**一次真实端到端闭环**，并用**真实文件后端**（非 fake）证明 teacher-final 写入。

- **teacher-review 真实文件后端写回 v2**（`tests/integration/test_luban_teacher_review_real_writeback.py`，6 passed）：用**真实 `LearnerStateService`**（temp `DEEPTUTOR_USER_DATA_DIR`，文件后端）跑 `build_teacher_review_writeback(dry_run=False)` → 写 `MEMORY_EVENTS.jsonl`（on-disk 实测）→ readback → synthesis → next suggestion。exact_required override→miss=E03 gap、list_rule partial=E02 gap、calculation full-hit=mastery、high_risk/unsupported 未复核=非 mastery；非 QA 学生 `qa_user_id_required` 不写、`teacher_reviewed=false` 不写。**唯一 stub 是非授权 home-personalization 网络投影**（否则 6s/写），记忆写入授权链 `append_memory_event→MEMORY_EVENTS.jsonl` 全真实。脚本 `scripts/run_luban_teacher_review_real_writeback_v2.py` → `artifacts/luban_consensus_gold/teacher_review_real_writeback_v2_20260604/`。
- **e2e 全链路 smoke v1**（`scripts/run_luban_e2e_runtime_teacher_review_smoke.py` + `tests/integration/test_luban_e2e_runtime_teacher_review_smoke.py`，1 passed）：经**真实 FastAPI TestClient `/api/v1/ws`**（`entry_layer=fastapi_testclient_ws`）跑 3 样本（published Q17 / draft Q20 / published Q2 exact_required override）→ 每次产 legacy `construction_grading_result`（authority 不变）+ `luban_grading_engine_shadow` → 转 teacher-review payload → 真实文件后端写回 → readback + synthesis + next suggestion。实测：`ws_shadow_count=3`、`legacy_unchanged=true`、`shadow_writeback_performed=false`、`teacher_final_writeback_count=3`、`memory_events_jsonl_count=3`、`has_weakness=true`、`has_next_suggestion=true`、`high_risk_or_unsupported_mastery_ids=[]`、`teacher_reviewed_false_writeback_count=0`、`needs_new_table=false`。产物 `artifacts/luban_consensus_gold/e2e_runtime_teacher_review_smoke_20260604/`（ws_inputs / ws_shadow_outputs / teacher_review_payloads / writeback_outputs / readback_memory_events / learning_brain_synthesis / next_suggestion_preview / FINDING）。
- **truth level（诚实标注）**：REAL=`/api/v1/ws` TestClient 入口 + 真实评分链 + ArtifactRuntimeGate + 文件后端写入授权 + readback + synthesis；SIMULATED=逐点预测 fixture + teacher 决策 fixture（`qa_fixture_teacher_review`）+ fake agent/llm；STUBBED=非授权 home-personalization 网络投影。
- **测试命令**：`pytest tests/api/test_luban_runtime_shadow_live_route.py tests/integration/test_luban_teacher_review_real_writeback.py tests/integration/test_luban_e2e_runtime_teacher_review_smoke.py -q` → **15 passed**；`construction_grading` + teacher-review api + live-route 回归 **190 passed** 无回归。
- **红线**：不新增 endpoint/表、不改 kernel、RAG 不进评分、AI-Draft 未复核不写 LB、不写生产用户、**未把 fake service 当真实 DB**（真实文件后端 + on-disk 证据）。
- **下一步**：进入小范围 QA 产品测试前补：Best-Quality live jury（非 fixture 预测）优先跑、QA 老师工作台真人复核、outbox→Supabase sync 配置确认；DeepSeek live 跑作为 production-cost 单模型蒸馏/对齐轨道并行推进；随后并行做全题库采分点编译发布系统。
