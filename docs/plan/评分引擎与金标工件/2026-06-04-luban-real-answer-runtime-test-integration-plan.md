# 鲁班评分引擎 · 真实答题链路 runtime test 接入方案（planning only）

> Status: `Proposed v0`（2026-06-04，Stream C）。**只读审计 + 设计，不写生产代码、不改 runtime、不接 production。** 设计一个 `grading_engine_runtime_test` flag 把鲁班评分引擎挂到真实答题链路的测试接入点，明确为何不制造第二套 authority、如何回滚、artifact missing 如何 fail-closed。
>
> 本文承接 `docs/plan/2026-06-04-luban-grading-engine-ai-draft-test-ab-plan.md`（AI-Draft A/B + Registry v0），不重复其内容，只补「真实答题链路在哪、test flag 怎么挂」。
>
> **红线复述**：Best-Quality 是当前能力天花板；DeepSeek 是未来生产成本线；**teacher-final 才是 Learning Brain 写入 authority**；**published artifact 才允许 auto_certified**；high_risk/unsupported 不自动变 mastery。**不新增表 / 不改 `case_kernel.py` / 不让 RAG 进评分 authority / 不写真实用户或生产库 / 不重跑 485-QWK / 不接 production runtime。**

---

## 1. 真实案例题提交/批改链路 —— 确切文件:行（已用 codegraph + Read 核验，2026-06-04）

### 1.1 生产热路径（学生真实作答 → 批改）

| 阶段 | 文件:行 | 角色 |
|---|---|---|
| 唯一聊天 WebSocket 入口 | `deeptutor/api/routers/unified_ws.py`（`/api/v1/ws`） | 唯一流式入口（AGENTS 硬约束，不得新增专用路由） |
| capability + TutorBot loop → deep_question 能力 | `deeptutor/capabilities/deep_question.py` `class DeepQuestionCapability`（manifest @ `:1446`） | 案例题作答的能力执行体 |
| 构造提交上下文 | `deep_question.py:2680` `_build_submission_context` / `:2700` `_build_batch_submission_context` | 把作答包成 graded_context |
| 调批改 adapter | `deep_question.py:2697`/`:2724` → `attach_deep_question_grading_result(...)` | 单一挂载点（薄适配） |
| 批改 adapter（薄适配层） | `deeptutor/services/construction_grading/deep_question_adapter.py:96` `attach_deep_question_grading_result` → `:30` `build_deep_question_grading_result` | 选 MCQ vs case；case 走 kernel |
| **案例题批改 authority（确定性 source-grounded）** | `deep_question_adapter.py:64` 调 `CaseGradingSkillKernel().grade(...)` → `deeptutor/services/construction_grading/case_kernel.py:27` `grade()` | **唯一案例题 source-of-truth 批改 authority**；确定性关键词匹配（`_official_keyword_matches`，`status="full" if matched else "miss"`，无 partial、无 LLM）；authority 优先级 `grading_key.scoring_points` > `grading_rubric` > projected > open_skill |

> 关键事实（核验后不变）：**生产案例题批改是确定性 kernel，不是 LLM。** kernel 输出标 `authority="construction_grading"`（adapter `:70`）。

### 1.2 另一条独立 LLM 路径（不调 kernel）

- `deeptutor/agents/question/agents/submission_grader_agent.py:35` `process(...)`：`BaseAgent`，prompt `grade_submission`，TutorBot/agent 路径上的 LLM 评分。**它不调 `case_kernel`，也不被鲁班引擎替换。** AI-Draft / 鲁班引擎绝不并入此 agent，否则就制造了第二套 production authority。

### 1.3 可见链路 QA harness（非生产，鲁班引擎的现有测试挂载点）

| 端点 | 文件:行 | 说明 |
|---|---|---|
| `POST /api/v1/learning-brain/harness-case-grading` | `deeptutor/api/routers/learning_brain.py:446` `run_learning_brain_harness_case_grading` | QA-gated（`_qa_enabled()` @ `:377`，`:463` 拦截）；docstring 明确「owns no grading or memory truth … production grading goes through the capability + TutorBot loop, not this endpoint」 |
| 旧链路分支（baseline / A 组） | `learning_brain.py:475-490` | `CaseGradingSkillKernel().grade(...)` → `write_grading_error_events(...)`（QA 测试 service，真实写 learner_memory_events） |
| **AI-Draft / 鲁班引擎分支（B 组，已落地）** | `learning_brain.py:472-473` `if payload.mode == "ai_draft": return _run_ai_draft_harness(payload)` → `:63` `_run_ai_draft_harness` | `engine=deepseek_fast`（默认，单模型 `_ai_draft_grader` @ `:40`）/ `engine=best_quality_4model`（四模型裁决 `_best_quality_grader` @ `:45`）；**candidate_only / dry_run / writeback_performed=False / 不触 kernel** |
| teacher-review 写回 | `learning_brain.py:548` `run_learning_brain_teacher_review_writeback`（`POST .../harness-case-grading-review`） | QA-gated；只有 `teacher_reviewed=true` + `writeback=true` 才走现有写回 |

> **结论：真实答题链路（1.1）与鲁班引擎测试链路（1.3）在生产代码里已经物理分离。** 鲁班引擎现状只活在 `harness-case-grading?mode=ai_draft`（QA-gated），从未进 `/api/v1/ws` → deep_question 热路径。本计划要做的，是设计一个 **flag**，让「真实作答经由 harness 喂给鲁班引擎做 shadow 对比」成为可控的测试接入，而**不是**把鲁班引擎塞进 1.1 的生产热路径。

---

## 2. 当前 RAG / prompt 批改路径

| 路径 | RAG/prompt 角色 | 是否进评分 authority |
|---|---|---|
| 生产 case 批改（`case_kernel.grade`） | RAG 仅作 `evidence_rows` 来源（`deep_question_adapter.py:77` `_evidence_rows_from_context`，从 `evidence_refs` 取 `rag_content` 等）；kernel 用的是 source-grounded 关键词匹配，**RAG chunk 不决定得分**，只作 evidence_refs 携带 | **否**（RAG 不是评分 authority；符合红线） |
| LLM submission_grader（`submission_grader_agent.py:35`） | prompt `grade_submission` + `grounding_context`（RAG 注入 prompt） | 这是独立 LLM 路径的 authority，**与 case_kernel 并列，鲁班引擎不并入它** |
| 鲁班 AI-Draft（`deeptutor/services/construction_grading/ai_draft_shadow.py` `build_ai_draft`） | **不接 RAG**。evidence 来源 = `student_answer` 本身的 `evidence_span` 守卫（`_span_in_answer`：span 必须逐字出现在作答，否则 `unsupported=true` fail-closed） | **否**（rubric/采分点来自 golden fixture + typed-policy packet，不是 RAG 召回） |
| 鲁班 Best-Quality（`best_quality_ai_draft.py` `best_quality_for_golden`） | 复用 `ai_draft_shadow` guards，对缓存 4-model 预测裁决，**同样不接 RAG** | **否** |

> **红线确认：鲁班引擎（AI-Draft / Best-Quality）的评分 authority 不依赖 RAG。** 采分点来自 golden fixture（`luban_case_grading_golden_v1.json` 的 `gold_scoring_points`）+ 题目级 published artifact（`question_grading_artifacts.py`），evidence 靠 span guard 锚定在学生作答里。本计划的 test flag **不得**改变这一点：不允许把 RAG chunk 接成鲁班引擎的采分依据。

---

## 3. Learning Brain 写回路径（`write_grading_error_events` 真实调用方，已用 codegraph_callers 核验）

`write_grading_error_events`（`deeptutor/services/construction_grading/writeback.py:17`）是**唯一写回口**。12 个调用方分两类：

### 3.1 生产写回（真实 learner_memory_events）

| 调用方 | 文件:行 | 触发 |
|---|---|---|
| **生产热路径写回** | `deeptutor/capabilities/deep_question.py:1421` `_write_grading_error_events_for_context` → `:1434` 调 `write_grading_error_events(...)`（用 `get_learner_state_service()`） | 由 `deep_question.py:2256` `_emit_grading_result` 在真实作答批改后触发；写入 `construction_grading_result`（即 kernel 输出） |
| member console 学情信号 | `deeptutor/services/member_console/service.py:679` `_write_assessment_learning_signals` | 会员侧评测信号 |
| learning report e2e 脚本 | `scripts/run_learning_report_read_model_e2e.py:150` | 报表读模型 e2e |

### 3.2 测试 / QA / 鲁班引擎写回（非生产库）

| 调用方 | 文件:行 | 说明 |
|---|---|---|
| QA harness baseline | `learning_brain.py:482`（A 组旧链路） | QA-gated，写测试 service |
| **teacher-review 写回（鲁班引擎闭环的唯一写入 authority）** | `deeptutor/services/construction_grading/teacher_review_writeback.py:44` `build_teacher_review_writeback` → 内部 `:写回` 调 `write_grading_error_events` | **默认 `dry_run=True`，纯转换不触 DB**；仅 `dry_run=False` **且**传入 `learner_state_service`（测试 service）才委托写回 |
| 单元测试 8 处 | `tests/services/construction_grading/test_audit_and_writeback.py` / `tests/services/learner_state/test_learning_report_read_model.py:1262` | 测试夹具 |

### 3.3 payload 与 mastery 规则（核验自 `teacher_review_writeback.py:1-23` docstring）

- payload 由 `build_learning_evidence_payload()`（`learning_evidence.py:18`）产出（含 rubric / error_events / quality），**不新增第二套 memory builder、不新增表**（复用 `learner_memory_events`，`memory_kind="learning_evidence"`）。
- **mastery 硬规则**：一个采分点成为 confident MASTERY 证据，当且仅当其 final disposition 是 full hit 且（teacher-confirmed 或 AI-auto_certified）且 **非** high_risk/unsupported —— **除非 teacher override 升权**。
- high_risk / unsupported（非 override）：`awarded_score=0`、status 永不 `full`、`mastery_eligible=False`、并发 E03 错因事件。
- **AI-Draft 单独绝不写库**；teacher override 是更高 authority。

---

## 4. `grading_engine_runtime_test` flag 设计

### 4.1 目的与一句话定义

> **`grading_engine_runtime_test`：一个 QA/测试环境开关，决定「真实学生作答样本（经 harness）是否额外跑一遍鲁班评分引擎做 shadow 对比」。**
> - `off`（默认）：旧链路一字不动 —— 真实作答只走 §1.1 生产 kernel 路径，鲁班引擎完全不介入。
> - `on`：在 **QA harness 层**（§1.3，`_qa_enabled()` 已为前置门）把同一份作答额外喂给鲁班引擎（`mode=ai_draft`），产出 **shadow draft + 与 kernel 的逐点对比**，**不替换 kernel 输出、不进 `/api/v1/ws` 热路径、默认不写库**。

### 4.2 挂载点（why here）

- **挂在 `learning_brain.py` harness 层，复用现有 `mode=ai_draft` 分支（`:472`）+ `_run_ai_draft_harness`（`:63`）。** 这两个已经存在、已 QA-gated、已 candidate_only/dry_run。flag 只新增「A 组 kernel + B 组鲁班引擎一次跑出、并排返回对比」的**薄编排**，评分理解仍全在 `ai_draft_shadow.py` / `best_quality_ai_draft.py`（fat skill）。
- **绝不挂在 `deep_question.py` / `deep_question_adapter.py` / `submission_grader_agent.py` / `unified_ws.py`。** 这四处是生产热路径，挂在这里就等于把鲁班引擎变成第二套 production authority，违红线。
- flag 的实现位置（实现轮，本轮不写）：
  - 读取：`_qa_enabled()` 旁新增 `_grading_engine_runtime_test_enabled()`（读环境变量，默认 False），**不新增 router、不新增 endpoint**，只在现有 `run_learning_brain_harness_case_grading` 内多一个「A/B 并排」返回分支。
  - 数据范围：先限 golden fixture（`luban_case_grading_golden_v1.json`，`_golden_case` @ `learning_brain.py:51`）或 QA 手输真实题，**不接真实用户库**。

### 4.3 为何不制造第二套 authority（设计约束）

1. **生产 authority 唯一不变**：`on`/`off` 都不改 §1.1 的 `case_kernel.grade` 是案例题 source-of-truth 这一事实。鲁班引擎输出永远标 `authority="ai_draft_shadow"` / `"best_quality_4model_shadow"` + `candidate_only=true` + `not_production_grade=true`（`_run_ai_draft_harness:85-95` 已固定），**永不冒充 `authority="construction_grading"`**。
2. **写入 authority 唯一不变**：Learning Brain 写入仍只经 `write_grading_error_events`（§3），且鲁班引擎结果**只有经 teacher-review（§3.2）才写**。flag `on` 不放开 AI-Draft 直写：`_run_ai_draft_harness` 永远 `writeback_performed=False`、`writeback_requested_ignored_this_round=bool(payload.writeback)`。
3. **不接 RAG 进评分**（§2）：flag `on` 只把作答文本喂给鲁班引擎，rubric 仍来自 golden/published artifact，evidence 仍靠 span guard，**不引入 RAG 召回当采分依据**。
4. **不新增表 / 不新增 memory store**：shadow 对比结果是 HTTP 响应里的临时 JSON（A/B 并排），落盘只落 `artifacts/`（gitignore，可复现），**不进 DB**。

### 4.4 published artifact 才允许 auto_certified

- runtime 进入 auto_certified 流的**发布门（admission gate）= QuestionGradingArtifact published**（`question_grading_artifacts.py` `build_question_grading_artifact` 的 `_resolve_status -> 'published'/'draft'`；Registry `question_grading_registry.py` `get_question_grading_artifact`）。
- flag `on` 时的硬约束（实现轮强制）：对某 `question_id`，**只有其 artifact `status="published"` 时，鲁班引擎逐点结果才允许 `auto_certified=true`**；`draft`/`weak` artifact → 该题逐点 `auto_certified=false`（只能 high_risk / pending_review）；**缺 artifact → `artifact_missing`，整题不进 auto_certified 流**（见 §4.6 fail-closed）。
- 这一门**复用现有 Registry，不新建第二套发布逻辑**。

### 4.5 teacher-final 才写 mastery

- flag `on` 产出的 shadow draft **永远不写 mastery**。mastery 写入唯一路径 = §3 teacher-review writeback：teacher-final（`teacher_reviewed=true` + `writeback=true`）经 `build_teacher_review_writeback` → `write_grading_error_events`。
- high_risk / unsupported（非 teacher override）永远 `mastery_eligible=False`、`awarded_score=0`（§3.3）。flag 不开任何「自动把 shadow 结果升 mastery」的口子。

### 4.6 artifact missing → fail-closed（设计）

复用现有 fail-closed 语义，flag `on` 不放松：

| 缺失场景 | 现有处置（文件:行） | flag `on` 时行为 |
|---|---|---|
| golden case 缺失 | `_run_ai_draft_harness:67-68` → `HTTPException(404, "golden case not available for ai_draft mode")` | 整题不评，404；A 组 kernel 不受影响 |
| Best-Quality 缓存 4-model 预测不足（陪审<3） | `best_quality_ai_draft.py` raise `BestQualityUnavailable` → `_run_ai_draft_harness:75-77` → `HTTPException(503, {"error":"best_quality_unavailable"})` | **fail closed，绝不用单次 DeepSeek 冒充 best-quality** |
| evidence_span 不在作答里 | `ai_draft_shadow.py` `_span_in_answer` → `unsupported=true` | 该点 `unsupported`、不计认证分、不进 mastery |
| **QuestionGradingArtifact 缺失** | Registry `artifact_missing`（`found=False`） | **该 `question_id` 不进 auto_certified 流**：逐点 `auto_certified=false`，整题降级到 high_risk / pending_review 视图，**绝不伪造教材锚点 / 绝不默认放行**（实现轮在 A/B 编排里强制查 Registry，缺则 fail-closed 标 `auto_certification_allowed=false`） |

> 原则：**任何上游产物缺失，鲁班引擎都向「不自动认证 / 报告缺失」收敛，绝不向「默认通过」收敛。** 这是 fail-closed 的核心。

### 4.7 回滚

| 维度 | 回滚方式 |
|---|---|
| flag 本身 | `_grading_engine_runtime_test_enabled()` 默认 False；置 False（或删环境变量）即下线 B 组，harness 回到 §1.3 现状（只有 A 组 kernel + 现有 `mode=ai_draft` 手动分支） |
| QA 门 | 整个 harness 由 `_qa_enabled()`（`:377`）前置门控；生产 `_qa_enabled()` 为 False，flag 即使误置也打不开 |
| 生产热路径 | flag `on`/`off` **都不碰** §1.1（`unified_ws` / `deep_question` / `deep_question_adapter` / `case_kernel`），生产作答批改零影响，无需回滚 |
| 写库副作用 | flag `on` 默认 dry_run、`writeback_performed=False`，**无写库副作用**；teacher-review 写回若误写，可按 `source_id` 清理（复用现有 append_memory_event 的 source 维度） |
| 产物 | shadow 对比只落 `artifacts/`（gitignore），删目录即清，不入库不入 git |

---

## 5. 数据流图（flag on 的测试态 A/B）

```
真实/QA 作答样本 (golden case 或 QA 手输, 非真实用户库)
        │
        ▼  POST /api/v1/learning-brain/harness-case-grading   ← _qa_enabled() 门
        │                                                       ← _grading_engine_runtime_test_enabled() 门 (新, 默认 off)
        ├── A 组 (baseline, 不变): CaseGradingSkillKernel.grade  → kernel 结果 (authority=construction_grading)
        │
        └── B 组 (鲁班引擎 shadow, flag on 才跑): _run_ai_draft_harness
                 ├── engine=deepseek_fast    → ai_draft_shadow.build_ai_draft  (span guard fail-closed)
                 └── engine=best_quality_4model → best_quality_for_golden       (缓存4模型裁决; 缺→503 fail-closed)
                       │
                       ├── 查 QuestionGradingArtifact Registry
                       │     published → 允许 auto_certified
                       │     draft/weak/missing → auto_certification_allowed=false (fail-closed)
                       │
                       ▼  candidate_only / not_production_grade / dry_run / writeback_performed=False
                 返回 A/B 逐点对比 (HTTP JSON) + 落 artifacts/ (gitignore)
                       │
                       ▼  (人工) teacher-review 面板复核
        POST /api/v1/learning-brain/harness-case-grading-review (teacher_reviewed=true + writeback=true)
                 build_teacher_review_writeback → write_grading_error_events  ← 唯一写入 authority
                 (mastery 只在 teacher-final 且 非 high_risk/unsupported 或 override 时写)
```

---

## 6. 边界清单（实现轮严守，本轮不写代码）

### 只动（实现轮）
- `deeptutor/api/routers/learning_brain.py`：新增 `_grading_engine_runtime_test_enabled()` + harness 内「A/B 并排」薄编排分支（QA-gated）。**不新增 endpoint、不新增 router。**
- `artifacts/`（gitignore）：落 A/B 对比产物，可复现。

### 绝不碰
- `deeptutor/services/construction_grading/case_kernel.py`（案例题批改 authority）
- `deeptutor/capabilities/deep_question.py` / `deep_question_adapter.py`（生产热路径 + kernel 调用方）
- `deeptutor/agents/question/agents/submission_grader_agent.py`（独立 LLM 路径）
- `deeptutor/api/routers/unified_ws.py`（唯一聊天入口）
- `writeback.py` / `learning_evidence.py` / `teacher_review_writeback.py`（写回 authority，复用不改逻辑）
- consensus gold 产物、`CaseGradingSkillKernel` runtime authority、BI/billing、第二套 learner memory/eval

### 停止条件（命中即停并报告）
新增数据库表 / 改 `case_kernel.py` / 让 RAG 进评分 authority / 写真实用户或生产库 / 把未复核 AI-Draft 写入 Learning Brain / 重跑 485-QWK-consensus / 接 production runtime。

---

## 7. 验收结论（planning only）

1. **真实案例题提交/批改入口/route/service 确切文件:行**：`/api/v1/ws`（`unified_ws.py`）→ `deep_question.py` `DeepQuestionCapability`（`:1446`，`_build_submission_context:2680`）→ `deep_question_adapter.py:96/30` → `deep_question_adapter.py:64` 调 `case_kernel.py:27 grade()`（案例题 authority）。LLM 旁路 `submission_grader_agent.py:35`。QA harness `learning_brain.py:446`（B 组 `:472`/`:63`）。— **§1 已逐行列出。**
2. **RAG/prompt 批改路径**：生产 kernel 把 RAG 仅作 evidence_refs 不计分；LLM agent 用 prompt+grounding；鲁班引擎不接 RAG。— **§2，确认 RAG 不进鲁班评分 authority。**
3. **Learning Brain 写回路径**：唯一口 `writeback.py:17`；生产触发 `deep_question.py:1421`（由 `:2256` `_emit_grading_result` 调）；鲁班闭环唯一写入 = teacher-review `teacher_review_writeback.py:44`。— **§3 已列 12 调用方。**
4. **flag 设计**：`grading_engine_runtime_test`（on=harness 层并排跑鲁班引擎 shadow / off=旧链路不变）；挂在 `learning_brain.py` harness（复用现有 `mode=ai_draft`），不挂生产热路径；不制造第二套 authority（§4.3）；回滚=置 flag False + QA 门 + 不碰热路径 + dry_run 无副作用（§4.7）；artifact missing → 向「不自动认证/报告缺失」收敛 fail-closed（§4.6）。
5. **不新增第二套 authority**：明确（§4.3）。
6. **回滚**：明确（§4.7）。
7. **artifact missing fail-closed**：明确（§4.6）。
8. **published artifact 才 auto_certified（§4.4）；teacher-final 才写 mastery（§4.5）**：明确。

> 本文为 planning only，未写任何生产代码、未改 runtime、未接 production。下一步若实现，按 §6 边界，只在 `learning_brain.py` 加 QA-gated flag + 薄 A/B 编排，先 golden 20 题 smoke。
