# 鲁班知识编译层系统性落地方案 v1.2

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for execution tracking.
>
> **Goal:** Build a Luban-owned knowledge compiler that turns 2026 一建建筑实务真题答案、教材、规范、讲义 into reviewed, versioned, evidence-backed grading artifacts for case-answer scoring, weakness diagnosis, and next-step training.
>
> **Architecture:** Offline compiler produces candidate artifacts from trusted source corpus; reviewer and eval gates promote artifacts to published runtime authority; `CaseGradingSkillKernel` consumes published artifacts before using RAG/LLM, and point-level results write back to learning evidence only after quality gates pass.
>
> **Tech Stack:** Python compiler services, JSONL artifacts, Supabase/Postgres target schema, pgvector optional retrieval support, existing `RAGService`, existing `construction_grading` / `deep_question` / learner evidence pipeline.

> Status: Proposed v1.2, scenario-stressed and delivery-hardened on 2026-05-31.
>
> Scope: 一建建筑实务案例题批改、采分点识别、教材/规范/讲义证据对齐、学情画像与下一题训练建议。
>
> Upstream context: [2026 source knowledge compiler v0.2](2026-05-24-luban-2026-source-knowledge-compiler-execution-plan-v0-2.md), [ACTION_LOOP 采分点空态诊断](2026-05-30-action-loop-empty-state-diagnosis.md), [RAG diagnostic-first PRD](2026-05-28-rag-diagnostic-first-prd.md).
>
> Research input absorbed in v1.1: attached `deep-research-report.md` on Pinecone Nexus and Luban codebase fit.
>
> v1.2 hardening: expands use-case pressure test, P0/P1/P2 delivery cutline, uncertainty register, validation plan, and fallback options.
>
> Local MVP evidence:
> - `artifacts/knowledge_compiler/2026/mvp-rubric-artifact-20q-20260531/rubric_quality_report.json`
> - `artifacts/knowledge_compiler/2026/mvp-rubric-ab-20q-20260531/answer_rubric_ab_eval_summary.json`
>
> Current MVP code:
> - `deeptutor/services/source_compiler/answer_rubric_extractor.py`
> - `deeptutor/services/source_compiler/rubric_evidence_aligner.py`
> - `scripts/compile_2026_rubric_artifact_mvp.py`
> - `scripts/run_answer_rubric_ab_eval.py`

---

## 0. 执行摘要

### 0.1 最终判断

鲁班应建设自己的 **Knowledge Compiler / Rubric Artifact Layer**，不要把核心阅卷能力交给外部 Nexus 类产品。当前实证已经证明：从 `docs/2026` 的真题答案、2026 教材、名师讲义、行业规范中，能批量生成可审核的案例题采分点 artifact，并显著优于现有 `grading_keywords/testing_focus/structured_rules` baseline。

当前最优路线：

```text
docs/2026 source corpus
  -> answer-derived rubric candidates
  -> textbook / standard / lecture evidence alignment
  -> review checklist and quality report
  -> published rubric artifacts
  -> CaseGradingSkillKernel artifact-first grading
  -> grading_point_matches
  -> learner_weaknesses / mistake book / review plan
  -> eval-driven continuous improvement
```

### 0.2 已验证事实

20 题 artifact MVP:

| 指标 | 结果 |
| --- | ---: |
| rubric candidates | 20 |
| scoring points | 86 |
| evidence records | 1048 |
| aligned points | 58 |
| point alignment rate | 67.4% |
| publishable candidates | 15 |
| review required | 2 |
| blocked | 3 |
| publishable rate | 75.0% |

跨 6 个真题文件的 A/B:

| 指标 | 当前 baseline | Artifact-first |
| --- | ---: | ---: |
| case rows | 134 | 134 |
| usable rubric cases | 0 | 95 |
| usable rate | 0.0% | 70.9% |
| scoring points | 0 | 576 |
| token proxy | 68084 | 7997 |
| token reduction proxy | - | 88.2% |
| publishable candidates | - | 80 |
| review required | - | 21 |
| blocked | - | 33 |

解释边界：

- 这不是 Pinecone Nexus 同 benchmark 复现。
- 这是鲁班内部任务的离线 A/B，证明 knowledge artifact 方法对一建建筑实务有效。
- 目前尚未证明批改分数准确率，因为还没有 100 份学生答案人工 golden。
- 下一阶段的核心不是继续证明“能拆答案”，而是证明“能稳定提升批改准确率、采分点 recall、错因准确率和学情质量”。

### 0.3 v1.1 research absorption

v1.1 吸收 `deep-research-report.md` 后做出 6 个强化决策：

| 报告发现 | v1.1 吸收方式 |
| --- | --- |
| 当前案例题主路径不是多步 Agentic RAG，而是 `CaseGradingSkillKernel` 的 deterministic rubric/keyword kernel | runtime 改造必须先喂给现有 kernel，不新建第二评分器 |
| `CaseGradingResult`、`learning_evidence.py`、`writeback.py` 已经形成 typed result -> learning evidence -> mistake book / projection 链路 | v1.1 不重建 learner memory，只补 point-level persistence 与 writeback eligibility |
| `assessment_sessions` 已经把 `client_questions_public` 与 `session_questions_private` 分离 | published artifact 只能进入 hidden/private grading artifact，不得泄露到 client public payload |
| `compiled_truth_source.py`、`exact_authority.py`、`source_compiler/*` 说明仓库已有 Nexus-like 地基 | 知识编译层是现有 compiler/authority 的垂直深化，不是新平台 |
| 当前缺少 `question_rubrics`、`scoring_points`、`grading_point_matches`、`eval_cases` 等标准化评分真相表 | v1.1 把这 4 类对象提升为 P0 schema，不再只用 generic JSON artifact |
| Nexus 的性能 claim 主要是厂商早期公开材料，中文主观题生产案例不足 | 不直接接入 Nexus；只吸收 context compiler、typed retrieval、provenance、eval-driven layer |

v1.1 的判断比 v1 更明确：鲁班的最大机会不是“更强检索”，而是把一建建筑实务的评分标准变成可审核、可版本化、可评测、可写回学情的私有资产。

未吸收内容：

- 不把 Pinecone Nexus / KnowQL 作为当前生产依赖。
- 不把 LangGraph / GraphRAG / Neo4j 作为 P0 基础设施。
- 不把运营素材生成、增长文案、教师后台统计纳入知识编译层主战场。
- 不把 `docs/2026` 原始 JSON 作为 runtime question bank。
- 不把 LLM 生成的临时标准答案写入长期学情。

### 0.4 v1.2 delivery hardening

v1.2 在 v1.1 基础上再收紧 4 件事：

1. **使用场景压力测试**：把学生作答、追问扣分、错题复习、老师审核、运营看覆盖、测评私有工件、申诉复核、2027 教材更新等场景逐一分级。
2. **交付切线**：P0 只证明 reviewer publishes artifact -> student submits answer -> kernel grades -> learner evidence writes safely，不做大平台。
3. **不确定性登记**：把学生答案分布、rubric 完整度、证据对齐精度、LLM verifier 可靠性、token 成本、reviewer 吞吐、版权边界全部变成验证项。
4. **替代方案**：每个关键失败点都有降级路径，例如只内部显示 citation、只做 provisional feedback、不写 learner memory、停留在 teacher-review 模式。

---

## 1. Karpathy Gate

### 1.1 assumptions

- `FastAPI20251222/docs/2026` 是高价值源数据，但不是 runtime authority。
- 生产在线 authority 仍是现有 Supabase 表、`RAGService`、`CaseGradingSkillKernel`、`learner_memory_events`。
- 本计划只做一建建筑实务，不扩展到二建。
- 知识编译层是 offline compiler + review + publish pipeline，不是新的聊天入口，也不是新的 runtime RAG 替代品。
- 任何未发布的 rubric candidate 不能写入长期学情画像。
- LLM 可以用于表达扩展、错因候选、证据校验，但不能成为唯一评分 authority。

### 1.2 simplest path

最短路径不是上图数据库，也不是接 Pinecone Nexus，而是沿现有 source compiler 增加三段能力：

```text
standard answer -> rubric candidate
rubric candidate -> evidence aligned artifact
artifact -> review checklist and publish gate
published artifact -> grading kernel
```

### 1.3 change boundary

允许改动：

- `deeptutor/services/source_compiler/**`
- `deeptutor/services/construction_grading/**`
- `deeptutor/services/learner_state/**`
- `scripts/*rubric*compiler*.py`
- `scripts/*grading*eval*.py`
- `tests/services/source_compiler/**`
- `tests/services/construction_grading/**`
- `tests/fixtures/luban_case_grading_eval/**`
- `supabase/migrations/*knowledge_artifact*.sql`，shadow first
- `web` 或 BI review console，仅在后续阶段

不允许改动：

- 不新增聊天 WebSocket。
- 不绕开 `/api/v1/ws`。
- 不新建第二套 RAG runtime。
- 不直接写生产 `questions_bank.grading_rubric`。
- 不让 local JSON 成为 runtime question bank。
- 不把 graph projection 升级为评分 authority。

### 1.4 verification target

v1 的验收不是“生成很多 JSON”，而是：

- rubric candidate 可复跑、可 diff、可解释。
- 每个 published artifact 有 source provenance。
- Case grading 能用 artifact-first 路径批改。
- 学情写回只接受高置信 grading result。
- Eval gate 能量化分数偏差、采分点 recall、错因准确率、引用准确率、token 和 latency。

---

## 2. Single Authority Hard Gate

### 2.1 one business fact

鲁班要维护的核心业务事实是：

> 一道一建建筑实务案例题的每个批改结论，必须能追溯到题目标准答案、教材/规范/讲义证据、人工审核版本和具体采分点匹配记录。

### 2.2 one authority

| 业务事实 | Canonical authority |
| --- | --- |
| 原始文件身份 | `source_manifest` / source inventory |
| 题目原文和标准答案 | `questions_bank` 或 compiled question capsule |
| 采分点候选 | `rubric_artifact_candidates` shadow artifact |
| 已发布评分标准 | `published_rubric_artifacts` / future table |
| 批改执行 | `CaseGradingSkillKernel` |
| 采分点命中/漏点 | `grading_point_matches` |
| 长期学情画像 | `learner_memory_events` -> `learning_synthesis` |
| 证据链 | `artifact_evidence_refs` / source refs |
| eval 事实 | `eval_cases` and `eval_runs` |

### 2.3 competing authorities to prevent

- `grading_keywords` 被误当成完整 rubric。
- LLM runtime prompt 临时生成评分标准。
- RAG chunk 被直接当成评分标准。
- 本地 `docs/2026` JSON 被 runtime 直接读取。
- 前端或 TutorBot 自行解释采分点。
- graph edge 自行决定评分或学情。

### 2.4 canonical path

```text
docs/2026 raw source
  -> source inventory / dataless guard
  -> answer rubric extractor
  -> evidence aligner
  -> review queue
  -> published artifact
  -> CaseGradingSkillKernel
  -> grading result + point matches
  -> learning evidence
  -> compiled learner truth
```

---

## 3. Why This Is Better Than Direct Nexus For Luban

Pinecone Nexus 的可复制思想是：

- context compiler
- knowledge artifact
- typed retrieval
- provenance
- query protocol
- eval-driven improvement

鲁班需要吸收这些思想，但不应直接把核心 scoring authority 外包，因为：

- 一建建筑实务的评分体系是垂直知识资产，不是通用企业知识检索。
- 当前源数据已经高质量覆盖教材、真题、讲义、规范，最大缺口是 rubric artifact 编译。
- 生产学情画像需要稳定 provenance 和版本控制。
- 外部 Nexus early access 的 SDK/API/SLA/中文适配/价格/数据治理仍不确定。
- 自研知识编译层能成为产品壁垒，而不是依赖 vendor capability。

因此鲁班的目标不是“接入 Nexus”，而是做 **Luban Nexus-lite**：

```text
KnowQL-like protocol -> Luban Query Shape
Context Compiler -> Rubric / Evidence Compiler
Knowledge Artifact -> RubricArtifact / ScoringPointArtifact
Composable Retriever -> Artifact + RAG + DB hybrid retrieval
Field citations -> point-level evidence refs
```

---

## 4. Current Baseline And Gap

### 4.1 当前代码基础

已具备：

- `RAGService` 统一检索入口。
- Supabase read-only RAG pipeline。
- `retrieval_plan` 和 `provenance` ranking。
- `source_compiler` v0.2。
- `CaseGradingSkillKernel`。
- `learning_evidence` writeback。
- `learner_memory_events` 和 `learning_synthesis`。
- `rubric_coverage_report.py` 覆盖率审计。

代码实证基线：

| Area | Current fact | v1.1 implication |
| --- | --- | --- |
| Case grading authority | `deeptutor/services/construction_grading/case_kernel.py` 的 `CaseGradingSkillKernel.grade()` 明确 authority 顺序：`grading_key.scoring_points` -> `row.grading_rubric` -> projected rubric -> `open_skill` fallback | published rubric artifact 应以 `grading_key.scoring_points` 形态注入现有 kernel，避免另造 runtime scorer |
| Point matching today | `case_kernel.py` 当前按关键词包含关系给每个 rubric item `full` 或 `miss`，漏点写 `E02`，口号化表达可触发 `E04` | P0 不是替换 kernel，而是把 rubric spec 质量、point id、artifact version、semantic verifier 补上 |
| Learning evidence | `deeptutor/services/construction_grading/learning_evidence.py` 已输出 `rubric`、`rubric_items`、`evidence_refs`、`rag_evidence_refs`、`typed_edges`、`quality` | v1.1 要扩展 payload，不新建第二 learning evidence authority |
| Writeback | `deeptutor/services/construction_grading/writeback.py` 通过 `LearnerStateService.append_memory_event(..., memory_kind="learning_evidence")` 写入，并联动错题本和 home projection | low-confidence / unpublished artifact 必须 fail-closed，不能污染长期 learner profile |
| Assessment private artifact split | `supabase/migrations/20260524000100_assessment_sessions.sql` 已有 `client_questions_public` / `session_questions_private` / `result_report_json` / `learning_event_refs` / `mistake_book_refs` | scoring artifacts 必须沿 hidden/private lane 传递，public payload 只给题面和用户可见反馈 |
| Existing compiler foundation | `deeptutor/services/rag/compiled_truth_source.py`、`deeptutor/services/rag/exact_authority.py`、`deeptutor/services/source_compiler/graph_projection.py`、`lecture_compiler.py` 已存在 | v1.1 应复用 compiler/authority 思想，不把 GraphRAG 或 RAG chunk 升为评分真相 |

### 4.2 当前断点

当前断点不是没有资料，而是没有生产级 rubric artifact。

已知问题：

- `questions_bank.grading_rubric` 生产覆盖为 0%。
- 现有 `compile_rubric_candidate` 只是从 `grading_keywords/testing_focus` 再派生。
- 对 `grading_keywords=0` 的案例题，旧 compiler 无法创造新采分点。
- 学情页采分点 map 的价值被 rubric 覆盖率限制。
- 评分结果仍缺少稳定的 `point_id`、`artifact_version`、`evidence_span` 与 `grading_result_id`。
- `result_report_json`、`payload_json`、`session_questions_private` 可以保存快照，但不能长期替代规范化的 scoring point truth。
- RAG evidence 现在可以作为证据来源，但不能直接成为 scoring authority。
- graph edge 适合做知识点关系和弱点聚合，不能决定得分。

### 4.3 本轮 MVP 证明的新能力

新增 MVP 证明：

- 可以直接从历年真题标准答案拆出采分点。
- 可以自动推断大量分值。
- 可以用教材/规范/讲义做 point-level evidence alignment。
- 可以生成 published 前的人审清单。
- 可以用 publish gate 阻断低置信、缺分值、图示类答案。
- 可以显著降低 runtime context token proxy。

---

## 5. Target Architecture

### 5.1 模块图

```text
Source Layer
  docs/2026
  Supabase exports
  manual review corrections

Compiler Layer
  SourceInventory
  QuestionCapsuleCompiler
  AnswerRubricExtractor
  EvidenceAligner
  RubricQualityGate
  ReviewChecklistGenerator

Artifact Layer
  QuestionRubricArtifact
  ScoringPointArtifact
  EvidenceRef
  CommonMistakeArtifact
  StandardAnswerSkeletonArtifact
  QuestionKnowledgeEdgeArtifact

Runtime Layer
  retrieveRubric(question_id)
  gradeCaseAnswer(question_id, answer, student_id)
  diagnoseWeakness(student_id)
  recommendReviewPlan(student_id)

Eval Layer
  eval_cases
  eval_runs
  scoring_point_recall
  score_delta
  hallucination_rate
  citation_validity
  cost_latency
```

### 5.2 Runtime principle

运行时不能再临时做大规模知识发现。运行时只应该：

1. 按 `question_id` 取 published artifact。
2. 用 grading kernel 对学生答案做 point-level match。
3. 保存 `grading_point_matches`。
4. 只把高置信结果写入 learner memory。
5. 低置信结果返回给用户，但不污染长期画像。

---

## 6. Artifact Schemas

### 6.1 QuestionRubricArtifact

```json
{
  "artifact_id": "rub_...",
  "artifact_type": "question_rubric",
  "question_id": "...",
  "question_source_id": "qsrc_...",
  "exam_year": 2022,
  "node_code": "1A432000",
  "total_score": 20.0,
  "version": "2026-rubric-v1",
  "status": "draft | review_ready | published | rejected",
  "scoring_points": [],
  "evidence_alignment_summary": {},
  "publishability": {},
  "provenance": {},
  "compiler_version": "...",
  "run_id": "..."
}
```

### 6.2 ScoringPointArtifact

```json
{
  "point_id": "sp_...",
  "ordinal": 1,
  "subquestion_index": 1,
  "label": "还包括：复打法、反插法",
  "expected_answer": "复打法、反插法",
  "max_score": 2.0,
  "match_type": "enumeration_or_step",
  "acceptable_expressions": ["复打法", "反插法", "复打法、反插法"],
  "common_mistake_candidates": [],
  "evidence_refs": [],
  "confidence": "A-",
  "review_status": "pending"
}
```

### 6.3 EvidenceRef

```json
{
  "source_type": "exam_answer | textbook | standard | lecture_bundle",
  "source_path": "...",
  "source_record_id": "...",
  "node_code": "1A432000",
  "title": "...",
  "content_preview": "...",
  "alignment_score": 0.85,
  "method": "term_overlap_node_boost | embedding | llm_verifier"
}
```

### 6.4 Publishability

```json
{
  "gate": "publishable_candidate | review_required | blocked",
  "reasons": ["missing_score", "low_evidence_alignment"],
  "requires_human_review": true
}
```

### 6.5 Future database tables

v1.1 schema rule:

> Normalize the scoring truth; keep flexible education content in JSONB until eval proves it needs first-class columns.

P0 shadow schema:

| Table | Why first-class | Core fields |
| --- | --- | --- |
| `knowledge_sources` | provenance root | `source_id`, `source_type`, `title`, `source_uri`, `content_hash`, `effective_from`, `effective_to`, `metadata_jsonb` |
| `artifact_versions` | version and compiler authority | `artifact_version_id`, `artifact_family`, `schema_version`, `compiler_version`, `source_snapshot_hash`, `status`, `created_at` |
| `question_rubrics` | question-level grading truth | `rubric_id`, `question_id`, `artifact_version_id`, `total_score`, `grading_mode`, `provenance_jsonb` |
| `scoring_points` | point-level scoring truth | `point_id`, `rubric_id`, `ordinal`, `subquestion_index`, `criterion`, `max_score`, `required_meaning`, `keywords_jsonb`, `acceptable_expressions_jsonb`, `evidence_requirements_jsonb` |
| `artifact_evidence_refs` | field / point provenance | `evidence_ref_id`, `artifact_version_id`, `point_id`, `source_id`, `source_record_id`, `source_span_jsonb`, `alignment_score`, `method` |
| `rubric_review_queue` | human publish gate | `review_id`, `artifact_version_id`, `rubric_id`, `status`, `reviewer_id`, `decision_jsonb`, `created_at`, `reviewed_at` |
| `eval_cases` | quality gate input | `eval_case_id`, `question_id`, `sample_answer`, `gold_score_jsonb`, `gold_point_matches_jsonb`, `split`, `source_ref_jsonb` |
| `eval_runs` | quality gate result | `eval_run_id`, `strategy`, `artifact_version_id`, `params_jsonb`, `metrics_jsonb`, `started_at`, `finished_at` |

P1 runtime persistence:

| Table | Why first-class | Core fields |
| --- | --- | --- |
| `student_answer_grading_results` | attempt-level grading run | `grading_result_id`, `user_id`, `question_id`, `quiz_id`, `attempt_ref`, `artifact_version_id`, `raw_answer`, `total_score`, `max_score`, `result_jsonb`, `token_cost`, `latency_ms`, `created_at` |
| `grading_point_matches` | explainability and learner weakness basis | `grading_result_id`, `point_id`, `match_status`, `awarded_score`, `matched_text`, `evidence_span_jsonb`, `citation_jsonb`, `confidence` |
| `learner_weaknesses` | read model, not source of truth | `user_id`, `knowledge_point_id`, `weakness_type`, `confidence`, `evidence_refs_jsonb`, `suggested_actions_jsonb`, `updated_at` |

JSONB-first until proven:

- `standard_answer_skeletons`
- `common_mistakes`
- `review_plan`
- `teacher_feedback`
- `compiler_debug`

Do not create all production tables at once. Start with shadow tables and no runtime writes. Promote only after:

1. compiler rerun diff is stable;
2. reviewer approves at least 20 artifacts;
3. eval cases exist for the same artifacts;
4. `CaseGradingSkillKernel` consumes published artifacts behind a flag;
5. hidden/private payload checks prove no scoring key leaks through `client_questions_public`.

---

## 7. Compiler Design

### 7.1 AnswerRubricExtractor

Responsibilities:

- detect case-study answer records
- normalize escaped newline artifacts
- split explicit subquestion scores
- split `A/B/C` blank-fill answers
- split circled items `①②③`
- split parenthesized items `(1)(2)`
- split semicolon parallel clauses
- assign `max_score` when explicit or safely inferable
- mark low-confidence diagram / drawing / network-plan answers
- output point-level provenance

Non-responsibilities:

- no database write
- no runtime grading
- no learner memory write
- no final publish decision

### 7.2 EvidenceAligner

MVP:

- term overlap
- domain-term boosting
- `node_code` prefix boost
- source-type boost for standards

Next version:

- pgvector or local embedding retrieval over evidence records
- BM25 + vector hybrid
- LLM verifier with constrained schema
- citation exact-span selection
- evidence contradiction detection

### 7.3 QualityGate

Candidate gates:

| Gate | Required conditions |
| --- | --- |
| `publishable_candidate` | no missing score, no low-confidence point, evidence alignment above threshold |
| `review_required` | structurally good but evidence weak |
| `blocked` | missing score, low confidence, diagram answer, malformed answer, or low evidence |

Important: `publishable_candidate` still requires human review. It means machine gate passed, not production publication.

### 7.4 ReviewChecklistGenerator

Human review rows must include:

- candidate id
- point id
- question source
- point label
- expected answer
- max score
- confidence
- evidence aligned yes/no
- best evidence preview
- publish gate
- review decision
- review notes

---

## 8. Runtime Integration

### 8.1 retrieveRubric(questionId)

Behavior:

```text
questionId
  -> find published artifact version
  -> return rubric, scoring_points, evidence_refs, artifact_version
  -> if missing, return rubric_pending with reason
```

Must be read-only.

### 8.2 gradeCaseAnswer(questionId, studentAnswer, studentId)

Flow:

```text
retrieveRubric(questionId)
  -> CaseGradingSkillKernel artifact-first
  -> point-level matcher
  -> optional LLM semantic verifier for ambiguous points
  -> grading result
  -> grading_point_matches
  -> learning_evidence if confidence gate passes
```

### 8.3 Point-level matching

Three-tier matcher:

1. deterministic exact / keyword / numeric / unit match
2. embedding similarity for paraphrase
3. LLM verifier only for ambiguous cases

LLM verifier must return:

```json
{
  "status": "hit | partial | miss",
  "confidence": 0.0,
  "matched_text": "...",
  "reason": "...",
  "must_not_write_long_term": false
}
```

### 8.4 学情写回

Only write when:

- artifact version is published
- grading confidence is above threshold
- point match confidence is above threshold
- no unresolved contradiction
- no hidden-answer leakage

Otherwise:

- user can see provisional feedback
- long-term learner state is not updated

### 8.5 Assessment payload secrecy

v1.1 must preserve the existing `assessment_sessions` split:

| Lane | Allowed content | Forbidden content |
| --- | --- | --- |
| `client_questions_public` | stem, options if any, public metadata, user-visible progress | answer key, scoring points, artifact ids that expose answer, hidden rationale |
| `session_questions_private` | hidden answer key, rubric artifact refs, published `artifact_version_id`, internal scoring metadata | unreviewed compiler candidate unless explicitly marked shadow |
| `result_report_json` | post-submit explanation, visible hit/miss summary, citation labels safe for learner | unpublished source snippets that reveal future items |
| `learning_event_refs` / `mistake_book_refs` | references to committed learning evidence and mistake book rows | provisional low-confidence grading refs |

Release gate:

```text
public payload redaction snapshot
  + private artifact presence snapshot
  + post-submit result visibility snapshot
  + hidden-key leakage negative tests
```

This prevents the compiler from improving grading while accidentally degrading exam integrity.

---

## 9. Eval System

### 9.1 Required eval set

Minimum production-decision eval:

- 20 one-construction-exam case questions
- 100 student answers
- human expected score
- expected point matches
- expected common mistakes
- expected knowledge point edges
- citation validity labels

### 9.2 Metrics

| Metric | Threshold for MVP |
| --- | ---: |
| average absolute score delta | <= 1 point |
| scoring point recall | >= 90% |
| scoring point precision | >= 85% |
| mistake diagnosis accuracy | >= 80% |
| citation validity | >= 95% |
| hallucination rate | <= 3% |
| token reduction | >= 40% |
| latency | <= 1.5x baseline |
| long-term writeback false-positive rate | <= 2% |

### 9.3 A/B groups

| Group | Description |
| --- | --- |
| A Baseline | current `projected_rubric` / prompt / source signals |
| B RAG | retrieve chunks then grade |
| C Artifact-first | published rubric artifact then grade |
| D Artifact-first + verifier | artifact-first plus semantic verifier |

### 9.4 Current proxy results

Current result is strong but not final:

- usable rubric case: 0% -> 70.9%
- token proxy reduction: 88.2%
- actual grading accuracy: not yet measured

The next gating milestone must measure actual grading accuracy.

---

## 10. Product Surface

### 10.1 Teacher / reviewer console

Core screens:

- candidate queue
- rubric diff
- point-level evidence preview
- accept / edit / reject
- version history
- publish gate status
- eval failure cases

High-frequency reviewer actions:

- edit point label
- edit max score
- add acceptable expression
- attach evidence
- mark point as not scorable
- split / merge points
- publish version

### 10.2 Student-facing behavior

Student should see:

- score
- hit / miss / partial points
- missing scoring points
- standard answer skeleton
- next practice suggestion

Student should not see:

- hidden grading key before submission
- internal confidence score
- private review notes
- raw compiler metadata

### 10.3 Teacher-facing behavior

Teacher should see:

- class weak points
- common missed scoring points
- evidence-backed mistakes
- which artifact version graded which answer
- review backlog and eval failures

---

## 11. Delivery Roadmap

### Week 1: Compiler hardening

Goals:

- make answer-derived rubric extraction deterministic and diffable
- expand source coverage from 134 case rows to all readable historical case rows
- keep all outputs shadow-only

Deliverables:

- `answer_rubric_extractor.py` v0.2
- `rubric_evidence_aligner.py` v0.2
- source readability report
- 100-question artifact sample
- review checklist

Acceptance:

- tests pass
- no production write
- candidate output is stable across reruns
- blocked/review/publishable gates are populated

### Week 2: Evidence alignment v2 and review workflow

Goals:

- improve point evidence alignment
- add reviewer-ready output
- create first 20 human-reviewed artifacts

Deliverables:

- hybrid retrieval aligner
- LLM verifier prompt and schema, if needed
- review checklist CSV/JSONL
- reviewed artifact JSONL

Acceptance:

- evidence alignment >= 80% on 20-question sample
- reviewer can complete 20 questions in under 2 hours
- all published candidates have point scores and evidence refs

### Week 3-4: Runtime integration MVP

Goals:

- artifact-first grading behind flag
- point-level matches
- eval runner over 100 student answers

Deliverables:

- `retrieveRubric(questionId)`
- `gradeCaseAnswer(...)` artifact-first branch
- `grading_point_matches` shadow storage
- eval fixture and eval runner

Acceptance:

- score delta <= 1 point on eval set
- point recall >= 90%
- point precision >= 85%
- citation validity >= 95%
- no long-term writeback from low-confidence results

### Week 5-8: Productization

Goals:

- reviewer console
- artifact versioning
- teacher insight
- controlled rollout

Deliverables:

- Supabase shadow tables
- review UI
- artifact publish workflow
- staging rollout
- monitoring dashboard
- release gate

Acceptance:

- 100+ published artifacts
- eval gate in CI or release process
- staging traffic proves latency and cost
- teacher can inspect and correct rubric errors

---

## 12. Engineering Work Packages

### WP0: Authority and schema hardening

Files:

- `deeptutor/services/construction_grading/case_kernel.py`
- `deeptutor/services/construction_grading/schema.py`
- `deeptutor/services/construction_grading/learning_evidence.py`
- `deeptutor/services/construction_grading/writeback.py`
- `deeptutor/services/assessment/session_repository.py`
- `deeptutor/services/assessment/writeback.py`
- `supabase/migrations/*knowledge_artifact*.sql`

Tasks:

- document current `CaseGradingSkillKernel` authority order in tests
- add `point_id`, `artifact_version_id`, `grading_result_id`, `evidence_span` to grading result contract behind compatibility defaults
- add shadow schema for `question_rubrics`, `scoring_points`, `eval_cases`, `eval_runs`
- add public/private payload redaction snapshot around `assessment_sessions`
- add negative tests proving RAG chunks, graph edges, and runtime LLM output cannot become scoring authority

### WP1: Compiler

Files:

- `deeptutor/services/source_compiler/answer_rubric_extractor.py`
- `deeptutor/services/source_compiler/rubric_evidence_aligner.py`
- `deeptutor/services/source_compiler/rubric_quality_gate.py`
- `scripts/compile_2026_rubric_artifacts.py`

Tasks:

- normalize all answer forms
- add diagram/network-plan classifier
- add numeric/unit point splitting
- add duplicate candidate detection
- add artifact diff

### WP2: Evidence

Files:

- `deeptutor/services/source_compiler/rubric_evidence_aligner.py`
- `deeptutor/services/rag/retrieval_plan.py`
- `deeptutor/services/rag/provenance.py`

Tasks:

- build evidence index
- add hybrid retrieval
- add citation exact-span extraction
- add evidence confidence
- add contradiction check

### WP3: Review

Files:

- `scripts/export_rubric_review_queue.py`
- future BI / admin pages

Tasks:

- JSONL/CSV review export
- accept/edit/reject schema
- artifact version diff
- publish manifest

### WP4: Runtime

Files:

- `deeptutor/services/construction_grading/case_kernel.py`
- `deeptutor/services/construction_grading/deep_question_adapter.py`
- `deeptutor/services/construction_grading/schema.py`
- `deeptutor/services/construction_grading/learning_evidence.py`
- `deeptutor/services/construction_grading/writeback.py`
- `deeptutor/services/assessment/session_repository.py`
- `deeptutor/services/assessment/writeback.py`

Tasks:

- artifact-first branch
- point-level matching
- confidence gate
- writeback eligibility
- hidden/private artifact propagation through assessment sessions
- public payload redaction checks

### WP5: Eval

Files:

- `scripts/run_luban_grading_artifact_eval.py`
- `tests/fixtures/luban_case_grading_eval/**`

Tasks:

- create eval set
- compare baseline/RAG/artifact-first
- compute score delta, point precision/recall, citation validity
- produce release gate report

---

## 13. Risk Register

| Risk | Severity | Mitigation |
| --- | ---: | --- |
| wrong rubric contaminates learner profile | High | no writeback until published artifact + confidence gate |
| evidence alignment false positive | High | human review + verifier + exact span |
| diagram/network plan answers mis-split | Medium | classify as blocked; specialized extractor later |
| missing scores | Medium | block publish; reviewer must fill |
| source file dataless / iCloud timeout | Medium | source inventory and read probe before compile |
| overfitting to one year | Medium | cross-year eval |
| reviewer burden too high | Medium | prioritize high-frequency clusters |
| token proxy misleading | Medium | measure actual model usage in runtime eval |
| second authority drift | High | artifact layer feeds existing grading kernel only |
| premature UI launch | Medium | release only when eval gate passes |
| RAG chunk becomes scoring authority | High | RAG can supply evidence only; scoring point must come from published artifact |
| graph edge becomes scoring authority | High | graph supports diagnosis/recommendation only; score comes from `scoring_points` |
| JSON snapshot replaces canonical truth | Medium | keep `result_report_json` as snapshot; normalize point truth and matches |
| hidden scoring key leaks to student payload | High | keep artifact refs in private lane; add redaction snapshot tests |
| unreviewed candidate enters runtime | High | shadow status cannot be consumed by runtime unless explicit eval/debug flag |

---

## 14. Decision Gates

### Gate 0: Authority gate

Pass when:

- `CaseGradingSkillKernel` remains the only runtime case-answer grading executor.
- published artifact is injected through `grading_key.scoring_points` or an equivalent single-authority path.
- RAG evidence, graph edges, and LLM verifier output cannot create new scoring points at runtime.
- `client_questions_public` snapshot contains no answer key, scoring point, hidden rationale, or artifact body.
- unreviewed candidates are blocked from learner-memory writeback.

### Gate A: Compiler gate

Pass when:

- 100 case artifacts generated
- publishable rate >= 60%
- blocked reasons classified
- rerun diff stable

### Gate B: Evidence gate

Pass when:

- evidence alignment >= 80% on reviewed sample
- citation validity >= 95%
- no unsupported source used

### Gate C: Grading gate

Pass when:

- average score delta <= 1
- point recall >= 90%
- point precision >= 85%
- hallucination <= 3%

### Gate D: Learner writeback gate

Pass when:

- false-positive weakness writeback <= 2%
- low-confidence grading never writes long-term memory
- attempt detail can trace to artifact version

### Gate E: Product gate

Pass when:

- teacher can review and publish artifacts
- student sees clear hit/miss feedback
- no hidden scoring keys leak before answer
- staging latency and cost within budget

---

## 15. Systemic Plan Recommendation

Move forward with the system plan.

Recommended immediate sequence:

1. Freeze current `CaseGradingSkillKernel` behavior with authority-order tests.
2. Add shadow `question_rubrics`, `scoring_points`, `eval_cases`, `eval_runs`.
3. Generate 100 artifact candidates from `docs/2026`.
4. Review 20 high-confidence artifacts manually.
5. Build 100-answer eval set with human score and point-match gold.
6. Integrate artifact-first grading behind flag through the existing kernel.
7. Add `student_answer_grading_results` and `grading_point_matches` only after runtime consumes published artifacts.
8. Run baseline / RAG / artifact-first A/B.
9. Only then design production promotion and BI review workflow.

Do not:

- directly apply candidates into `questions_bank.grading_rubric`
- let LLM runtime create grading criteria
- use unreviewed candidates for learner profile
- build graph database before point-level artifact workflow is proven
- use `result_report_json` or `payload_json` as the only durable point-level truth
- put hidden scoring artifacts into `client_questions_public`

---

## 16. Definition Of World-Class For This Layer

This layer is world-class only if it satisfies all of the following:

1. **Evidence first**: every scoring point has provenance.
2. **Typed artifacts**: runtime retrieves scoring structures, not chunks.
3. **Human correctable**: teacher can review, edit, reject, publish.
4. **Versioned**: every grading result records artifact version.
5. **Eval-driven**: no publish without metric gates.
6. **Fail closed**: low confidence blocks writeback.
7. **Single authority**: artifact-first grading flows through `CaseGradingSkillKernel`.
8. **Traceable learning**: every weakness claim points back to attempts and points.
9. **Cost aware**: compile offline, grade with compact artifacts.
10. **Continuously improving**: review corrections become new compiler training examples.
11. **Exam integrity**: hidden scoring artifacts never leak before submit.
12. **Schema discipline**: point truth and point matches are normalized; flexible teaching content stays JSONB until eval justifies promotion.

If any one of these is missing, it is just another RAG wrapper. If all are present, it becomes鲁班自己的知识壁垒。

---

## 17. Operating Model

顶级团队不会把这件事交给“一个模型一次性生成”。这是一条人机协同生产线，角色、责任和 gate 必须清楚。

### 17.1 Roles

| Role | Responsibility | Cannot do |
| --- | --- | --- |
| Source Owner | 确认教材、真题、讲义、规范来源和版权边界 | 不能修改评分规则 |
| Rubric Compiler Owner | 维护 extractor、aligner、quality gate、diff | 不能绕过 review publish |
| Teaching Reviewer | 审核采分点、分值、可接受表达、错因 | 不能直接写 learner memory |
| Assessment QA | 维护 eval cases、student answer golden、metric gate | 不能只看单题样例下结论 |
| Runtime Owner | 接入 `CaseGradingSkillKernel`、writeback gate、trace | 不能在 runtime prompt 临时造 rubric |
| Product Owner | 决定学生/老师可见形态和灰度范围 | 不能降低 evidence gate 换速度 |

### 17.2 Weekly operating cadence

```text
Mon: source inventory and compiler run
Tue: reviewer queue triage
Wed: 20-50 artifacts reviewed and published
Thu: grading eval run + failure cluster analysis
Fri: runtime/staging smoke + teacher feedback review
```

### 17.3 Artifact lifecycle

```text
draft_candidate
  -> review_ready
  -> reviewer_editing
  -> publishable_candidate
  -> published
  -> deprecated
  -> superseded
```

Rules:

- `draft_candidate` can never grade a real student answer.
- `publishable_candidate` can never write learner memory.
- only `published` can be used by runtime artifact-first grading.
- any reviewer edit creates a new artifact version.
- any eval failure can move an artifact to `deprecated` or `needs_review`.

---

## 18. Economics And ROI

### 18.1 Why this matters economically

The economic unit is not “one LLM call”. The economic unit is:

> one reliable subjective-practice improvement loop.

Without compiled rubric artifacts, every answer requires long-context prompt construction, repeated RAG, unstable explanation, and weak learning-state writeback. With artifacts, the expensive work moves offline, and runtime becomes compact and auditable.

### 18.2 Cost model

| Cost component | Baseline | Artifact-first |
| --- | --- | --- |
| Runtime context | stem + answer + analysis + RAG chunks | compact rubric + relevant evidence refs |
| Repeated reasoning | repeated every attempt | compiled once, reused many times |
| Teacher review | ad hoc failure review | structured queue |
| Debugging | prompt inspection | artifact version + point match trace |
| Learner state quality | noisy | evidence gated |

Current proxy from 134 case rows:

- baseline token proxy: 68084
- artifact token proxy: 7997
- reduction: 88.2%

This does not equal final billing reduction, but it shows the right order of magnitude. The real ROI must be measured after runtime integration:

```text
runtime_token_cost_per_grading
runtime_latency_p50/p95
human_review_minutes_per_artifact
student_answer_eval_score_delta
retention impact of better feedback
```

### 18.3 Investment principle

Invest in artifacts only when they are reusable:

- real exam questions
- high-frequency node_code clusters
- case-study patterns that recur
- mistakes that drive repeated learner weakness

Do not over-invest in one-off malformed, diagram-heavy, or low-frequency questions until the core clusters are covered.

---

## 19. Red-Team And Failure Modes

### 19.1 Critical failure modes

| Failure | Example | Consequence | Defense |
| --- | --- | --- | --- |
| false rubric split | one answer sentence split into wrong points | unfair scoring | human review + eval cases |
| false evidence alignment | point matched to wrong教材/规范 | fake explainability | exact span + verifier |
| score hallucination | missing point scores inferred incorrectly | score drift | block missing score |
| diagram answer mishandled | network plan drawing treated as text point | bad feedback | diagram classifier blocks |
| learner memory pollution | provisional grading writes weakness | long-term profile damage | writeback gate |
| answer leakage | scoring points exposed before answer | exam product failure | payload redaction tests |
| source drift | 2026教材 changes, old artifact remains | stale grading | artifact versioning |
| reviewer rubber-stamp | low quality artifacts published | systemic errors | eval gate + random audit |

### 19.2 Red-team checks before launch

- adversarial student answer with copied keywords but wrong causal relation
- answer with correct conclusion but wrong unit
- answer with synonyms not in standard answer
- answer with multiple points in one sentence
- answer with negation or “不应/不得” reversed
- answer with irrelevant but domain-looking terms
- prompt-injection text in student answer
- hidden answer leakage in public payload

### 19.3 Fail-closed policy

When uncertain:

- grade as provisional
- show cautious feedback
- do not write long-term memory
- send case to review/failure queue

This is non-negotiable. A learning profile damaged by false weakness is more expensive than a single conservative grading result.

---

## 20. Data And Quality Governance

### 20.1 Quality score

Every artifact should receive a quality vector:

```json
{
  "structure_score": 0.0,
  "evidence_score": 0.0,
  "review_score": 0.0,
  "eval_score": 0.0,
  "runtime_score": 0.0,
  "overall_grade": "A|B|C|D"
}
```

Minimum for publish:

- structure_score >= 0.8
- evidence_score >= 0.8
- review_score == 1.0
- eval_score present for production rollout

### 20.2 Review sampling

Even after artifacts become publishable:

- 100% review for first 100 artifacts
- 30% random audit after stable production
- 100% audit for high-error artifacts
- 100% audit for artifacts with student complaint or teacher correction

### 20.3 Drift detection

Drift triggers:

- new 2026/2027教材 version
- standard/spec updated
- repeated eval failure
- large mismatch between human and AI score
- high student dispute rate
- reviewer edits same point multiple times

Drift response:

```text
mark artifact needs_review
stop learner-memory writeback for affected question
rerun compiler
rerun eval
publish new artifact version
```

---

## 21. What A Top Expert Team Would Do Next

The next move is not to expand blindly. The next move is to turn the promising compiler into a measured production system.

### 21.1 Immediate 10-day plan

| Day | Deliverable |
| --- | --- |
| 1 | Freeze current kernel authority tests and add public/private payload leakage snapshots |
| 2 | Add shadow schema draft for `question_rubrics`, `scoring_points`, `eval_cases`, `eval_runs` |
| 3 | Expand compiler to all readable historical case rows and classify blocked reasons |
| 4 | Add better evidence retrieval: BM25 + embedding over textbook/standard/lecture evidence |
| 5 | Create reviewer checklist for 50 high-confidence artifacts |
| 6 | Human-review 20 artifacts; produce reviewed JSONL |
| 7 | Build 100 student-answer eval fixture |
| 8 | Implement artifact-first branch behind flag through `CaseGradingSkillKernel` |
| 9 | Run grading A/B: baseline vs RAG vs artifact-first vs artifact+verifier |
| 10 | Analyze score delta / point recall failures and produce go/no-go for 4-week MVP |

### 21.2 Strategic moat

The moat is not “we have PDFs” and not “we call an LLM”.

The moat is:

```text
exam-specific scoring artifacts
+ source provenance
+ reviewer corrections
+ learner-answer eval data
+ point-level weakness history
+ next-question training loop
```

Every student attempt should improve either:

- the learner profile
- the eval set
- the artifact quality
- the next training recommendation

If attempts do not improve the system, the product is just a chatbot. If they do, the product becomes a compounding education engine.

---

## 22. v1.2 Scenario Pressure Test

This section tests the plan against real product and operating scenarios. The point is to avoid building an elegant compiler that only works in a demo.

### 22.1 Scenario classification

| Scenario | User / actor | What they need | Best mechanism | Priority | Why |
| --- | --- | --- | --- | --- | --- |
| 学员提交案例题答案 | student | 公平、可解释、能指出漏点 | published rubric artifact + `CaseGradingSkillKernel` + point matches | P0 | Core product value |
| 学员追问“为什么扣分” | student | 能看到具体采分点、自己原答案片段、依据 | `grading_point_matches` + safe evidence refs | P0 | Trust and retention |
| 学员要求答案表达优化 | student | 在不泄露未答题答案前提下补全表达 | standard answer skeleton after submit | P1 | High value, but depends on published artifact |
| 学员错题复习 | student | 知道错在哪、下次练什么 | point misses -> `learner_weaknesses` -> review plan | P1 | Requires stable point ids |
| 学员长期学情画像 | student / teacher | 薄弱点不是泛泛标签 | aggregated point misses + knowledge point edges | P1 | Needs more attempts |
| 老师审核采分点 | reviewer | 快速判断 artifact 能否发布 | review queue + evidence preview + diff | P0 | No review, no production artifact |
| 老师纠正错误 rubric | reviewer | 纠正后能形成新版本并回归 eval | artifact versioning + eval rerun | P1 | Prevents silent drift |
| 运营看专题质量 | ops | 哪些专题已可上线，哪些需要教研 | artifact coverage + publishability dashboard | P1 | Guides launch scope |
| 题库预生成测评 | system | 隐藏评分规则，公开题面 | `session_questions_private` carries artifact refs | P0 | Exam integrity |
| AI 老师对话辅导 | TutorBot | 在对话中引用学生真实漏点 | query published artifact / learner evidence, not raw chunks | P1 | Useful after grading loop works |
| 教材/规范问答 | student / teacher | 准确引用条文和教材点 | RAG + typed evidence, not scoring artifact | P2 | Related but not P0 scoring loop |
| 题目相似推荐 | system | 推荐相似错因/知识点题 | pgvector / metadata over knowledge points and question edges | P2 | Important later; not P0 |
| 申诉/复核 | student / teacher | 能复查当时用的版本和命中证据 | immutable grading result + artifact version + point matches | P1 | Needed before paid scale |
| 2027 教材更新 | system / reviewer | 能重编译、diff、阻断旧 artifact | source versioning + drift gate | P2 | Not needed before v1 launch, but design must allow |
| 内容增长素材 | ops | 生成短视频/图文素材 | ordinary LLM + curated examples | Not in layer | Does not need scoring authority |

### 22.2 P0 scenario cutline

P0 only needs to prove four scenarios end-to-end:

```text
reviewer publishes artifact
student submits answer
kernel grades with artifact
learner evidence writes only if quality gate passes
```

Anything else is secondary until those four are real.

P0 should not include:

- full knowledge graph UI
- 3D or force-directed knowledge map
- fully automated rubric publishing
- cross-subject expansion
- operational content generation
- direct Pinecone Nexus integration
- new chat route

### 22.3 P1 expansion after P0 passes

P1 starts only after P0 grading gate passes. It should add:

- student-facing “扣分依据” detail;
- reviewer correction loop;
- mistake-book point-level aggregation;
- weak-point review plan;
- teacher/ops coverage dashboard;
- regrade / dispute workflow for internal review.

### 22.4 P2 expansion after real usage

P2 should be driven by production data:

- knowledge-point graph expansion;
- similar-question recommendation;
- 2027 source drift workflow;
- cohort A/B for retention and improvement;
- optional external knowledge-engine re-evaluation.

---

## 23. Delivery-Hardened Architecture

### 23.1 Three lanes

The system should be delivered as three independent but connected lanes:

```text
Lane A: Compiler and review
  raw source -> candidate -> evidence alignment -> review -> published artifact

Lane B: Runtime grading
  published artifact -> CaseGradingSkillKernel -> point matches -> provisional / committed result

Lane C: Eval and governance
  eval cases -> eval runs -> release gate -> drift / rollback decision
```

If one lane fails, the others must fail closed:

| Failure | System behavior |
| --- | --- |
| compiler fails | keep existing published artifacts, do not publish new candidates |
| evidence aligner weak | mark review_required, do not auto-publish |
| runtime artifact missing | fallback to current kernel path but mark `rubric_pending`; do not write artifact-versioned weakness |
| LLM verifier unavailable | deterministic matcher still works; ambiguous points remain provisional |
| eval gate fails | block promotion; runtime keeps previous artifact version |
| public payload leakage test fails | block release even if grading accuracy improves |

### 23.2 Minimum build units

Each build unit must be independently shippable:

| Unit | Files | Acceptance |
| --- | --- | --- |
| Kernel authority guard | `tests/services/construction_grading/test_case_grading_kernel.py` | proves `grading_key.scoring_points` remains top authority |
| Shadow schema | `supabase/migrations/*knowledge_artifact*.sql` | local SQL lint / migration dry-run; no production write path |
| Compiler expansion | `deeptutor/services/source_compiler/**`, `scripts/compile_2026_rubric_artifacts.py` | generates deterministic JSONL and diff |
| Review export | `scripts/export_rubric_review_queue.py` | reviewer can approve/edit/reject 20 artifacts |
| Eval harness | `scripts/run_luban_grading_artifact_eval.py` | baseline/RAG/artifact-first metrics produced |
| Runtime flag | `deeptutor/services/construction_grading/**` | artifact-first can be toggled off without data loss |
| Redaction gate | `tests/services/assessment/**` | no scoring keys in public payload snapshots |

### 23.3 P0 must not depend on new infrastructure

P0 must run on:

- current Python service layout;
- current Supabase/Postgres;
- current `CaseGradingSkillKernel`;
- current `learner_memory_events`;
- current source compiler folder.

No P0 dependency on:

- Pinecone Nexus;
- Neo4j / Kuzu / Memgraph;
- LangGraph rewrite;
- new WebSocket route;
- production BI UI.

This is the practical delivery constraint that keeps the project shippable.

---

## 24. Uncertainty Register And Verification Plan

### 24.1 Known uncertainties

| Uncertainty | Why it matters | Verification | Fallback |
| --- | --- | --- | --- |
| Student-answer distribution is unknown | Artificial answers may overestimate accuracy | collect 100 real or teacher-written answers across easy/medium/hard | use internal teacher-authored adversarial set before public launch |
| Standard answer may not equal complete grading rubric | Some exam answers omit acceptable variants or partial credit | reviewer compares 20 artifacts against teacher scoring judgment | keep `review_required`; do not auto-publish |
| Evidence alignment precision is unproven | False citation damages trust | manual citation audit on 100 aligned points | show source label only until exact-span validity >= 95% |
| Deterministic keyword matcher may under-credit synonyms | Student may express correct meaning differently | add eval columns for semantic hit / keyword miss | use LLM verifier only for ambiguous points |
| LLM verifier may over-credit fluent wrong answers | Semantic verifier can be too generous | adversarial eval: wrong causal relation, wrong unit, negation reversal | deterministic score wins unless verifier confidence and evidence both pass |
| Token proxy may not equal actual cost | Offline proxy can mislead ROI | instrument runtime token/latency per strategy | keep artifact-first only if actual cost improves or accuracy gains justify |
| Reviewer throughput unknown | Human review may bottleneck launch | measure minutes per artifact for first 20 | prioritize high-frequency/high-confidence artifacts only |
| Copyright / licensing boundary of source snippets | User-visible citations may expose too much source text | legal/content review of citation preview policy | store exact span internally, show short citation labels to users |
| 2026 source coverage may be uneven | Some topics may have no reliable evidence | coverage report by node_code and source type | launch only covered topics; mark others as rubric_pending |
| Learner memory pollution risk | Wrong weakness can degrade personalization | delayed writeback for low-confidence / first-run artifacts | provisional feedback only; no long-term write |

### 24.2 Validation experiments

Run experiments in this order:

1. **Rubric validity audit**: 20 artifacts, reviewer labels each point as correct / merge / split / wrong / missing.
2. **Citation audit**: 100 point-evidence links, reviewer labels exact / related / weak / wrong.
3. **Grading A/B**: 100 student answers across baseline / RAG / artifact-first / artifact+verifier.
4. **Leakage audit**: snapshot public/private assessment payloads before submit and after submit.
5. **Writeback audit**: verify low-confidence results never enter `learner_memory_events`.
6. **Cost audit**: capture actual model tokens and latency, not just proxy.

### 24.3 Go / no-go decision

Move to 4-week MVP only if:

- reviewed artifact acceptance >= 70%;
- citation exact-or-acceptable >= 90%;
- average score delta <= 1 point;
- point recall >= 90%;
- point precision >= 85%;
- hallucination <= 3%;
- no hidden scoring key leakage;
- false-positive learner weakness writeback <= 2%;
- actual runtime latency <= 1.5x current baseline, or accuracy gain is explicitly accepted by product owner.

If these thresholds fail:

| Failure | Decision |
| --- | --- |
| rubric acceptance low | pause runtime integration; improve extractor and review workflow |
| citation quality low | keep evidence internal; do not show user-facing citations |
| score delta high | do not write learner memory; use artifact for teacher review only |
| recall low but precision high | add acceptable expressions and semantic verifier |
| precision low | tighten matcher; avoid LLM verifier |
| latency too high | deterministic-only path for P0; async explanation later |

---

## 25. Current Optimal Answer

Under current conditions, the strongest, most responsible plan is:

1. **Do not buy or directly integrate Pinecone Nexus now.** Its architecture is directionally right, but public maturity and Chinese subjective-grading validation are not enough for our core chain.
2. **Do not build a generic knowledge platform.** Build a scoring artifact layer for 一建建筑实务 case grading first.
3. **Keep `CaseGradingSkillKernel` as runtime authority.** Feed it better, reviewed, versioned rubrics; do not replace it with an agent.
4. **Normalize only the facts that must be queried and audited.** `question_rubrics`, `scoring_points`, `grading_point_matches`, `eval_cases`, and `eval_runs` deserve tables; teaching copy and review notes can remain JSONB.
5. **Ship behind a flag and fail closed.** Provisional feedback is allowed; learner-memory writeback requires published artifact, confidence gate, and no contradiction.
6. **Make eval a product asset.** The 100-answer grading set is as important as source PDFs; without it the compiler cannot be trusted.
7. **Use reviewer corrections as compounding data.** Every correction should improve compiler rules, acceptable expressions, and future eval cases.
8. **Launch by topic coverage, not by corpus size.** A small set of reliable topics beats a broad unreliable knowledge layer.
9. **Treat citation as trust infrastructure.** Internal exact span first; user-facing citation only after audit.
10. **Use production behavior to decide P2.** GraphRAG, knowledge maps, similar-question recommendations, and external Nexus re-evaluation should wait for point-level grading data.

This plan is intentionally conservative. It is not conservative in ambition; it is conservative in where it allows errors to enter the system.

The product advantage comes from:

```text
reviewed scoring artifacts
+ point-level grading records
+ learner answer eval set
+ teacher correction loop
+ versioned provenance
+ controlled writeback
```

That is the defensible education asset. The compiler is only the machine that grows it.
