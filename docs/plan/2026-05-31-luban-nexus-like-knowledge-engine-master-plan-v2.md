# 鲁班 Nexus-like Knowledge Engine 总体落地方案 v2.1

> **Status update 2026-05-31:** Superseded by [鲁班评分真相覆盖率 + Golden Eval 战役计划 v2.2](2026-05-31-luban-grading-truth-golden-eval-campaign-v2-2.md). This file is retained as a historical architecture risk study. Do not execute its generic Knowledge Engine / broad schema / standalone eval-service direction as P0/P1 work.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` before implementation. This file is a master implementation plan, not a concept note. Execute by work package, keep changes surgical, and update `docs/plan/INDEX.md` when this plan changes.
>
> **Goal:** Build a Luban-owned Nexus-like Knowledge Engine for 一建建筑实务: turn trusted sources, past exam answers, teaching materials, standards, learner attempts, teacher corrections, and evaluation results into versioned, typed, evidence-backed knowledge artifacts that improve case-answer grading, scoring-point diagnosis, weakness profiling, and next-step training.
>
> **Architecture:** Source compiler -> artifact registry -> evidence/provenance compiler -> human review and publish gate -> Luban typed query protocol -> runtime skills -> learner evidence ledger -> eval/governance loop -> compiler improvement.
>
> **Tech Stack:** Existing Python services, Supabase/Postgres, existing `RAGService`, optional `pgvector`, existing `CaseGradingSkillKernel`, existing `learning_evidence` writeback chain, existing assessment/session separation, offline compiler scripts, shadow schema first.

Status: Superseded by v2.2. Historical architecture risk study only.

Supersedes: [2026-05-31-luban-knowledge-compiler-systematic-implementation-plan-v1-2.md](2026-05-31-luban-knowledge-compiler-systematic-implementation-plan-v1-2.md) as the current strategy and architecture plan.

Relationship to v1.2: v1.2 remains a useful first delivery slice and prototype evidence for answer-derived rubric compilation, evidence alignment, review checklist, and A/B proxy testing. It is no longer the master plan.

Research basis:

- Attached `deep-research-report.md` on Pinecone Nexus, Nexus-like knowledge engines, codebase fit, and alternative architectures.
- Local code audit of `deeptutor/services/construction_grading/**`, `deeptutor/services/source_compiler/**`, learner evidence writeback, assessment session separation, and source compiler foundations.
- Local prototype evidence under `artifacts/knowledge_compiler/2026/**` generated from high-quality 2026 source materials.

Scope:

- Only 一建建筑实务.
- Core product surface: subjective case-answer training, grading, scoring-point feedback, mistake diagnosis, learning profile, review planning, teacher/admin review.
- This plan does not assume 二建 and must not introduce cross-exam abstractions before one-exam authority is stable.

---

## 0. 执行摘要

### 0.1 结论

这份计划必须重写。原因不是 v1.2 错，而是 v1.2 的中心过窄：它把最先可落地的 `grading rubric` 当成了系统主轴。鲁班真正要建设的是自研 Nexus-like Knowledge Engine，`grading rubric` 只是评分真相层的第一类高价值 artifact。

最终判断：

| 问题 | 决策 |
| --- | --- |
| 是否直接接入 Pinecone Nexus | 暂不接入 |
| 是否等待 Nexus 成熟后再考虑 | 保留外部观察，不作为当前路线依赖 |
| 是否自研 Nexus-like 层 | 是，作为鲁班长期技术壁垒 |
| 当前第一交付线 | 评分真相层，但必须嵌入全量知识引擎架构 |
| 最大风险 | 把 prototype 做成孤立脚本，或把 rubric 表误当成完整知识引擎 |
| 最值得吸收的思想 | 预编译知识、typed retrieval、task-specific context pack、field-level provenance、eval-driven release gate |

### 0.2 正确定位

鲁班 Nexus-like Knowledge Engine 不是一个检索组件，也不是一个大而泛的图谱平台。它是以下六层的组合：

```text
Source Intelligence Layer
  -> Knowledge Artifact Layer
  -> Evidence and Provenance Layer
  -> Luban Typed Query Protocol
  -> Runtime Skill Layer
  -> Learner State and Eval Governance Loop
```

每一层都有唯一 authority：

| 层 | 一等业务事实 | 唯一 authority |
| --- | --- | --- |
| Source | 原始来源是什么、版本是什么、是否可信 | Source Compiler / source inventory |
| Artifact | 某个题、采分点、知识点、错因、建议的结构化事实 | Artifact Registry |
| Evidence | 每个 artifact 的证据来自哪里 | Evidence Compiler |
| Query | Runtime 要什么类型知识、允许返回什么结构 | Luban Query Protocol |
| Runtime | 如何评分、解释、诊断、推荐 | Fat Skill / Service Kernel |
| Learner/Eval | 学员长期事实是否可信、系统是否变好 | Learning Evidence Ledger + Eval Gate |

### 0.3 v2.1 相对 v1.2 的关键修正

| 维度 | v1.2 倾向 | v2.1 修正 |
| --- | --- | --- |
| 计划定位 | 知识编译层落地方案，重心在 rubric | 自研 Nexus-like Knowledge Engine 总体方案 |
| 核心 artifact | `QuestionRubricArtifact`、`ScoringPointArtifact` | 全量 source/question/rubric/evidence/mistake/learner/review/eval/query artifact 家族 |
| Runtime 目标 | artifact-first grading | typed query protocol feeding grading, diagnosis, tutoring, recommendation, teacher review |
| 学情目标 | point-level writeback | learner state engine with weakness, trajectory, review plan, re-test, drift control |
| 治理目标 | review checklist | versioning, publish gate, correction loop, eval gate, quality report, source drift |
| 技术边界 | 不接 Nexus，自研 compiler | 不接 Nexus，自研 Knowledge Engine，保留未来替换/互操作能力 |
| 交付方式 | 20 题样例切片 | 分层工程路线，评分真相层只是 Phase 0/1 |

### 0.4 当前最优路径

```text
Phase 0: Knowledge Engine foundation and scoring truth core
Phase 1: Artifact-first grading runtime and point-level persistence
Phase 2: Learner diagnosis, mistake book, and review-plan engine
Phase 3: Typed tutor protocol and evidence-backed teaching dialogue
Phase 4: Eval-driven self-improving knowledge operation
```

第一阶段仍然从真题答案拆 rubric 做起，因为它最直接影响批改准确率和用户可解释性。但工程上必须按 Knowledge Engine 总体架构落地，不能只做一个 isolated rubric compiler。

### 0.5 deep-research-report 吸收追踪

v2.1 必须能回答一个审查问题：报告里的硬发现，到底变成了哪些执行要求。下表是当前计划的 traceability map。

| 报告硬发现 | 负责人级解读 | v2.1 落地要求 |
| --- | --- | --- |
| Nexus 的方向正确，但仍是 Early Access，30x/90% 等数字主要是官方或早期材料，缺少中文主观题生产验证 | 不能用外部宣传替代鲁班自己的任务指标 | 不直接接入 Pinecone Nexus；所有“是否接近 Nexus 宣称效果”的判断只看鲁班 A/B eval |
| Nexus 的本质是 Knowledge Engine：把推理从 retrieval 前移到 compilation，返回 typed/structured answers，而不是 raw chunks | 鲁班要复制的是编译型知识接口，不是 vendor service | 建 `Source -> Artifact -> Evidence -> Typed Query -> Runtime -> Eval` 六层；P0 query 返回 `RubricContextPack` 而非 chunk list |
| 当前 `CaseGradingSkillKernel` 已是 rubric/keyword deterministic kernel，不是多步 Agentic RAG | 不能另起第二评分器；必须把 artifact 喂给现有评分 authority | `ArtifactFirstGradingService` 只做 context pack and delegation；评分仍由 `CaseGradingSkillKernel` 执行 |
| `CaseGradingResult`、`learning_evidence.py`、`writeback.py` 已有 typed result -> learning evidence -> mistake book 闭环 | 不重建 learner memory；补点级事实和 artifact refs | `grading_point_matches`、`artifact_version_id`、`scoring_point_ids` 进入现有 writeback eligibility gate |
| `assessment_sessions` 已有 `client_questions_public` 与 `session_questions_private` 分离 | 隐藏评分工件不能泄露到学生端 public payload | Publish gate 必须包含 client leak scan；student-facing citation bundle 与 reviewer citation bundle 分开 |
| 缺少 `question_rubrics`、`scoring_points`、`common_mistakes`、`question_knowledge_edges`、`student_answer_grading_results`、`grading_point_matches`、`eval_cases`、`eval_runs` | 当前短板是评分知识没有独立成一等资产 | Phase 0/1 schema 以这些表为核心，先 normalized 评分点和点级命中，其他复杂内容先 JSONB |
| `assessment/scoring.py` 当前更偏 objective exact-match，题集测评与案例题深度批改未在 artifact 层打通 | 不能只改案例题孤岛；正式测评也要能引用同一 artifact version | Phase 1 先 shadow 写 `student_answer_grading_results`；Phase 2 再把 assessment report 接入 artifact refs |
| 替代方案中 Supabase/Postgres + structured artifacts + eval 最适合当前仓库 | 不引入重型图数据库或外部 orchestration 作为核心依赖 | Postgres/Supabase 为主；pgvector 只做 source span、相似题、表达变体辅助 |
| GraphRAG/LlamaIndex/LangGraph/DSPy 各有价值但不替代 artifact layer | 框架只能辅助，不是 authority | DSPy-style eval 可借鉴；Graph 只做知识点边；LangGraph 不进入 P0 |
| 2 周 POC 应比较 Baseline / RAG / Artifact-first | “效果好不好”必须通过任务内评测证明 | v2.1 增加 A/B/C 三路实测门槛，未通过不进入生产 runtime |

### 0.6 v2.0 二次审查结论

v2.0 的方向正确，但不足以作为负责人级执行文档，主要缺 4 件事：

1. 报告证据没有逐条绑定到工程动作，容易让后续执行者只记住“自研 Nexus-like”，忘记为什么不接 Nexus、为什么不重建评分器。
2. 计划说了 eval，但没有把 Baseline / RAG / Artifact-first 三路对照写成硬门槛。
3. 计划说了现有代码集成点，但没有按报告指出的核心文件路径形成优先级。
4. 计划说了风险，但没有把 Pinecone 官方 claim 的可信度和未来重评条件制度化。

v2.1 的补强目标是：让团队可以从这份计划直接进入 implementation queue，而不是再开一轮“怎么落地”的讨论。

---

## 1. 设计门槛

### 1.1 assumptions

- `FastAPI20251222/docs/2026` 是高质量源数据，可以作为 source compiler 的首批原料，但不能直接成为 runtime authority。
- 当前仓库已有评分和学习事实基础：`CaseGradingSkillKernel`、`CaseGradingResult`、`learning_evidence`、assessment private/public payload 分离、source compiler 和 graph projection 雏形。
- Pinecone Nexus 的核心思想可吸收，但当前不把 Pinecone Nexus、KnowQL 或 Pinecone hosted service 作为生产依赖。
- 鲁班的壁垒来自一建建筑实务场景的专业 artifact、人工审核、学生作答闭环和持续 eval，而不是通用 RAG 框架。
- LLM 是 compiler、verifier、feedback writer，不是唯一 truth authority。
- Published artifact 才能进入 runtime grading 和 learner state。Candidate artifact 只能用于 review、eval 或 shadow comparison。

### 1.2 simplest path

最短路径不是一次性上完整图数据库，也不是把所有内容塞进向量库，而是沿现有代码建立一条可验证主链路：

```text
trusted source
  -> source inventory
  -> candidate artifacts
  -> evidence alignment
  -> review and publish gate
  -> typed query protocol
  -> existing grading kernel
  -> point-level learning evidence
  -> eval and correction loop
```

### 1.3 change boundary

第一批允许触碰：

- `deeptutor/services/source_compiler/**`
- `deeptutor/services/construction_grading/**`
- `deeptutor/services/learner_state/**`
- `scripts/*rubric*compiler*.py`
- `scripts/*grading*eval*.py`
- `tests/services/source_compiler/**`
- `tests/services/construction_grading/**`
- `tests/fixtures/luban_case_grading_eval/**`
- Shadow-first Supabase migrations for artifact and eval tables
- Admin/reviewer console only after backend publish gate exists

第一批不允许触碰：

- 不新增聊天 WebSocket；继续遵守统一 `/api/v1/ws`。
- 不新建第二套 TutorBot runtime。
- 不让前端、RAG chunk、prompt 或 graph edge 直接决定分数。
- 不直接写生产 `questions_bank.grading_rubric`。
- 不把 `docs/2026` 本地 JSON 直接接到线上 runtime。
- 不把运营素材生成纳入核心 Knowledge Engine P0。

### 1.4 verification target

v2.1 的验收不是“生成了很多 artifact”，而是：

- 同一题的评分结论可追溯到 source、artifact version、evidence ref、review record、grading point match。
- Runtime 能通过 typed query 拿到任务专用 context pack，而不是每次临时 RAG 一堆 chunk。
- 学员长期画像只消费高置信、可追溯、可重放的 grading evidence。
- Eval gate 能持续衡量分数偏差、采分点 precision/recall、错因准确率、citation accuracy、hallucination rate、token、latency。
- 任何 artifact 变更都能 diff、review、rollback、re-run eval。

---

## 2. 单一 Authority 总纲

### 2.1 one business fact

鲁班要长期维护的核心事实是：

> 一名学员在一建建筑实务主观题训练中的每一个批改、解释、错因、知识点归因和下一步建议，都必须来自已发布、可版本化、可追溯、可评测的专业知识 artifact，而不是 runtime 临时拼出来的答案。

### 2.2 canonical authorities

| 业务事实 | Canonical authority | 当前仓库证据/落点 |
| --- | --- | --- |
| 原始来源身份与版本 | Source Compiler / source inventory | `deeptutor/services/source_compiler/**` |
| 题目、题干、标准答案 | Question Capsule artifact / existing question source | `questions_bank`、2026 source compiler |
| 采分点和分值 | Published rubric artifact | Future `question_rubrics` / `scoring_points` |
| 证据来源 | Evidence Compiler | Future `artifact_evidence_refs` |
| 批改执行 | `CaseGradingSkillKernel` | `deeptutor/services/construction_grading/case_kernel.py` |
| 批改输出结构 | `CaseGradingResult` | `deeptutor/services/construction_grading/**` |
| 采分点命中/漏点 | `grading_point_matches` | Future runtime table |
| 学习事实写回 | Learning evidence ledger | `learning_evidence.py` / `writeback.py` chain |
| 长期画像和推荐 | Learner state engine | Existing learner state services, future artifact-aware read models |
| 质量评测 | Eval cases/runs | Future `eval_cases` / `eval_runs` |
| 人审发布 | Review queue + release gate | Future reviewer workflow |

### 2.3 competing authorities to eliminate

| 竞争 authority | 风险 | 处理 |
| --- | --- | --- |
| `grading_keywords` | 只适合粗粒度关键词，不足以表达完整 scoring point | 降级为 fallback/feature，不作为评分真相 |
| LLM prompt 临时生成 rubric | 不可重放、不可审核、不可版本化 | 仅允许在 compiler shadow 阶段生成 candidate |
| RAG chunks | 返回文本片段，不等于 scoring contract | 作为 evidence retrieval，不直接评分 |
| 本地 `docs/2026` 文件 | 文件质量高，但 runtime 不能依赖本地路径 | 先编译成 artifact，再 publish |
| 前端隐藏答案 payload | 泄露 scoring artifact 风险 | 坚持 private grading artifacts |
| graph edge | 适合知识关系，不适合作为分数 authority | 作为 context expansion / diagnosis support |

---

## 3. 鲁班 Artifact 全量体系

### 3.1 artifact 分层

鲁班不能只做 `QuestionRubricArtifact`。完整体系至少包含 7 组 artifact：

```text
Source Artifacts
Question and Exam Artifacts
Scoring and Grading Artifacts
Evidence and Provenance Artifacts
Mistake and Learner Artifacts
Runtime Context and Query Artifacts
Eval and Governance Artifacts
```

### 3.2 Source Artifacts

| Artifact | 作用 | 优先级 | 存储策略 |
| --- | --- | --- | --- |
| `KnowledgeSourceArtifact` | 表示一本教材、一份规范、一份讲义、一份真题文件 | P0 | `knowledge_sources` |
| `SourceManifestArtifact` | 文件路径、hash、来源类型、年份、版本、是否可发布 | P0 | JSONB + unique hash |
| `SourceSpanArtifact` | 可引用的页、章、节、题号、条文、段落定位 | P0 | `artifact_evidence_refs` / JSONB |
| `SourceVersionArtifact` | 2026 教材/规范/讲义版本关系 | P1 | `artifact_versions` |
| `SourceCoverageArtifact` | 某专题、某题型、某规范覆盖情况 | P1 | coverage report JSONB |

### 3.3 Question and Exam Artifacts

| Artifact | 作用 | 优先级 | 存储策略 |
| --- | --- | --- | --- |
| `QuestionCapsuleArtifact` | 题干、材料、设问、标准答案、分值、年份、来源 | P0 | `question_capsules` or existing question table mapping |
| `SubQuestionArtifact` | 案例题多问拆分，一问一评分单元 | P0 | normalized table or JSONB array |
| `StandardAnswerSkeletonArtifact` | 标准答案结构、步骤、表达层级 | P1 | `standard_answer_skeletons` |
| `QuestionIntentArtifact` | 题目考查意图、隐含能力要求 | P1 | JSONB candidate, review before publish |
| `QuestionDifficultyArtifact` | 难度、易错点密度、综合度 | P2 | eval-backed read model |

### 3.4 Scoring and Grading Artifacts

| Artifact | 作用 | 优先级 | 存储策略 |
| --- | --- | --- | --- |
| `QuestionRubricArtifact` | 一道题/一问的评分标准总包 | P0 | `question_rubrics` |
| `ScoringPointArtifact` | 采分点、分值、同义表达、必要条件、扣分规则 | P0 | `scoring_points` |
| `ScoringPointExpressionArtifact` | 学生可能写法、口语化表达、可接受近义项 | P1 | JSONB on `scoring_points` |
| `PartialCreditRuleArtifact` | 部分得分、顺序依赖、缺项扣分 | P1 | JSONB, only after golden cases |
| `RegradePolicyArtifact` | 申诉/复核时如何重跑和解释 | P2 | service policy + table config |

### 3.5 Evidence and Provenance Artifacts

| Artifact | 作用 | 优先级 | 存储策略 |
| --- | --- | --- | --- |
| `EvidenceRefArtifact` | 采分点对应教材/规范/讲义/真题证据 | P0 | `artifact_evidence_refs` |
| `CitationBundleArtifact` | 给用户、老师、内部 reviewer 的不同 citation 视图 | P1 | generated read model |
| `ProvenanceChainArtifact` | source -> candidate -> review -> publish -> runtime result 全链路 | P1 | `artifact_versions` + lineage events |
| `EvidenceQualityArtifact` | evidence 对齐置信度、缺口、冲突 | P0 | quality report JSONB |

### 3.6 Mistake and Learner Artifacts

| Artifact | 作用 | 优先级 | 存储策略 |
| --- | --- | --- | --- |
| `CommonMistakeArtifact` | 某采分点常见错误、混淆、漏答方式 | P1 | `common_mistakes` |
| `ErrorPatternArtifact` | 多次作答中稳定出现的错因模式 | P1 | learner state derived table |
| `LearnerWeaknessArtifact` | 学员薄弱点，必须有 point-level evidence 支撑 | P1 | `learner_weaknesses` |
| `MistakeBookArtifact` | 错题集条目及其原因、证据、复习状态 | P1 | existing mistake book + new refs |
| `ReviewPlanArtifact` | 下次复习/训练计划，来自 weakness and mastery | P2 | `review_plans` |
| `TrainingIntentArtifact` | 下一题/下一组训练的具体意图 | P2 | maintain existing `study_plan` authority, add typed refs |

### 3.7 Runtime Context and Query Artifacts

| Artifact | 作用 | 优先级 | 存储策略 |
| --- | --- | --- | --- |
| `QueryShapeArtifact` | 定义 runtime 可以问什么 | P0 | code contract + tests |
| `ContextPackArtifact` | 为某任务编译好的最小上下文包 | P0 | service return object, optional cache |
| `RetrievalPolicyArtifact` | rubric/evidence/learner/history 的选择策略 | P1 | config + tests |
| `AnswerContractArtifact` | 每类 query 的 typed response schema | P0 | dataclass/pydantic schema |
| `RuntimeTraceArtifact` | query 使用了哪些 artifact、花费、命中质量 | P1 | observability payload |

### 3.8 Eval and Governance Artifacts

| Artifact | 作用 | 优先级 | 存储策略 |
| --- | --- | --- | --- |
| `EvalCaseArtifact` | 学生答案、人工分、人工采分点、错因 golden | P0 | `eval_cases` |
| `EvalRunArtifact` | 某版本 artifact/runtime 的评测结果 | P0 | `eval_runs` |
| `QualityReportArtifact` | compiler 质量、coverage、publishability | P0 | JSONB report |
| `CoverageReportArtifact` | 题目、章节、规范、知识点覆盖率 | P1 | report table |
| `DriftReportArtifact` | 教材/规范/题库版本变化影响 | P2 | report table |
| `ReleaseGateArtifact` | publish 前后的可执行门槛 | P0 | scripts + DB snapshot |
| `ReviewerCorrectionArtifact` | 人工修正如何回流 compiler | P1 | `artifact_corrections` |

---

## 4. Luban Typed Query Protocol

### 4.1 原则

鲁班不需要直接采用 KnowQL。需要的是自有 typed query protocol：runtime 不问“给我一些相关 chunks”，而是问“给我这个任务所需的结构化知识包”。

每个 query 必须返回：

- `query_type`
- `artifact_version_policy`
- `typed_payload`
- `evidence_refs`
- `confidence`
- `publish_status`
- `quality_flags`
- `trace`

### 4.2 P0 query shapes

```python
retrieveRubric(questionId, subQuestionId=None, versionPolicy="published")
```

返回：

- question rubric
- scoring points
- point scores
- accepted expressions
- evidence refs
- review status
- quality flags

```python
gradeCaseAnswer(questionId, studentAnswer, studentId=None, attemptId=None)
```

执行：

- retrieve published rubric
- compile context pack
- call `CaseGradingSkillKernel`
- produce `CaseGradingResult`
- persist `grading_point_matches` when eligible
- write learning evidence only when confidence gate passes

```python
explainScoringPoint(pointId, audience="student")
```

返回：

- point explanation
- why it matters
- accepted expressions
- common omissions
- short citation bundle

```python
runGradingEval(evalSetId, artifactVersion, runtimeVersion)
```

返回：

- score deviation
- point precision/recall
- mistake accuracy
- citation accuracy
- hallucination rate
- token and latency
- pass/fail gate

### 4.3 P1 query shapes

```python
diagnoseStudentWeakness(studentId, window="90d")
```

返回：

- weak knowledge points
- recurring missed scoring points
- error patterns
- evidence attempts
- confidence
- recommended next training intents

```python
recommendReviewPlan(studentId, goal="case_score_improvement")
```

返回：

- review priorities
- question set recommendation
- textbook/lecture spans
- re-test schedule
- explanation of why

```python
compareAttempts(studentId, questionId)
```

返回：

- point-level improvement/regression
- expression improvement
- remaining missing points
- recommended targeted drill

```python
retrieveEvidencePack(topicId=None, pointId=None, questionId=None, taskType="grading")
```

返回：

- selected source spans
- citation bundle
- conflict/coverage flags
- allowed use surface

### 4.4 P2 query shapes

```python
compileQuestionArtifact(questionId, sourcePolicy="2026-trusted")
```

用于 compiler/reviewer，不用于学生 runtime。

```python
reviewArtifactCandidate(candidateId, reviewerAction, correctionPatch)
```

用于人审和 correction loop。

```python
detectSourceDrift(sourceVersionA, sourceVersionB)
```

用于教材、规范、讲义更新后的影响分析。

---

## 5. 业务场景适配矩阵

| 场景 | 需要的 artifacts | 最合适技术 | 阶段 | 是否属于核心 |
| --- | --- | --- | --- | --- |
| 案例题批改 | `QuestionRubricArtifact`, `ScoringPointArtifact`, `EvidenceRefArtifact` | Artifact-first + deterministic kernel + LLM verifier | P0/P1 | 是 |
| 采分点识别 | `ScoringPointArtifact`, expression variants | Rule/semantic matcher + LLM judge fallback | P0/P1 | 是 |
| 标准答案拆解 | `StandardAnswerSkeletonArtifact`, rubric candidate | Offline compiler + human review | P0/P1 | 是 |
| 错因诊断 | `CommonMistakeArtifact`, `ErrorPatternArtifact` | Rules + LLM diagnosis with evidence | P1 | 是 |
| 知识点图谱 | `KnowledgePointArtifact`, `QuestionKnowledgeEdgeArtifact` | Structured DB + light graph projection | P1/P2 | 是 |
| 错题集归因 | `GradingPointMatchArtifact`, `LearnerWeaknessArtifact` | Structured writeback | P1 | 是 |
| 学员长期画像 | learner evidence, weakness artifacts | Event ledger + synthesis | P1/P2 | 是 |
| 学习路径推荐 | `ReviewPlanArtifact`, `TrainingIntentArtifact` | Policy + learner state + question inventory | P2 | 是 |
| 教材/规范/真题问答 | source spans, evidence packs | RAG + citations, artifact boost | P2 | 中 |
| AI 老师对话辅导 | context pack, learner weakness, rubric | Typed query protocol + TutorBot | P2/P3 | 是 |
| 题目相似度推荐 | question capsule, knowledge edges | DB filters + embeddings | P2 | 中 |
| 主观题表达优化 | skeleton, point expressions, common mistakes | LLM rewrite constrained by rubric | P1/P2 | 是 |
| 老师后台薄弱点 | learner weakness, coverage report | Read model + BI | P2 | 是 |
| 运营内容生成 | selected source/context | LLM content pipeline | P3 | 非核心 |
| 用户增长素材 | public-safe source summaries | Separate Hermes/growth pipeline | P3 | 非核心 |
| 申诉复核 | provenance chain, grading matches | Regrade policy + replay | P2 | 是 |
| 教材版本更新 | source version, drift report | Source diff + impact analysis | P2/P3 | 是 |

判断：

- 传统 RAG 适合教材/规范/真题问答、补充解释、citation retrieval。
- Nexus-like artifact 适合批改、采分点、错因、学情、推荐、复核。
- 知识图谱适合知识点关系、题目-知识点边、弱点聚合，不适合直接评分。
- 规则 + LLM 适合采分点匹配、表达变体、错因诊断。
- 结构化数据库足够处理题目、答案、批改结果、弱点、review queue、eval runs。
- 直接上 Nexus 会在当前阶段复杂化评分 authority，并带来 vendor lock-in 和中文教育场景适配不确定性。

---

## 6. 总体架构

### 6.1 架构图

```text
Trusted 2026 Sources
  - 教材
  - 历年真题与标准答案
  - 名师讲义
  - 行业规范
  - 人工标注与修正
          |
          v
Source Intelligence Layer
  - inventory
  - dataless/read guard
  - hash/version
  - source type classification
          |
          v
Knowledge Artifact Compiler
  - question capsule compiler
  - answer rubric compiler
  - evidence aligner
  - common mistake miner
  - knowledge edge projector
          |
          v
Artifact Registry and Versioning
  - candidates
  - published artifacts
  - artifact_versions
  - provenance chain
          |
          v
Review and Release Gate
  - human checklist
  - coverage report
  - eval gate
  - rollback plan
          |
          v
Luban Typed Query Protocol
  - retrieveRubric
  - gradeCaseAnswer
  - diagnoseWeakness
  - recommendReviewPlan
  - explainScoringPoint
          |
          v
Runtime Skills
  - CaseGradingSkillKernel
  - TutorBot teaching skill
  - learner diagnosis service
  - recommendation service
          |
          v
Learning Evidence Ledger
  - grading_point_matches
  - learner_memory_events
  - mistake book
  - learner_weaknesses
          |
          v
Eval and Governance Loop
  - eval_cases
  - eval_runs
  - drift report
  - reviewer corrections
  - compiler improvement
```

### 6.2 thin wrapper / fat skill split

| 层 | Thin wrapper 职责 | Fat authority 职责 |
| --- | --- | --- |
| API / CLI | 鉴权、输入归一化、调用 service、错误语义 | 无业务评分逻辑 |
| Query protocol | 参数校验、version policy、trace | 不自行评分 |
| Grading runtime | 调用 artifact and kernel | `CaseGradingSkillKernel` 决定评分执行 |
| Learner writeback | 接收 eligible result | learner evidence service 决定长期事实写入 |
| Reviewer console | 展示 diff 和动作 | artifact registry/publish gate 决定状态 |

任何 wrapper 中出现 prompt 拼接、采分点推断、错因推断、推荐策略，都要下沉到对应 service/kernel。

---

## 7. 数据库与存储设计

### 7.1 Phase 0 foundation schema

| 表 | 核心字段 | 说明 |
| --- | --- | --- |
| `knowledge_sources` | `id`, `source_type`, `title`, `year`, `version`, `origin_path`, `content_hash`, `metadata`, `created_at` | 原始来源注册 |
| `artifact_versions` | `id`, `artifact_type`, `artifact_key`, `version`, `status`, `source_hashes`, `created_by`, `published_at`, `superseded_by` | 版本与发布状态 |
| `question_capsules` | `id`, `question_id`, `source_id`, `exam_year`, `question_no`, `stem`, `sub_questions`, `standard_answer`, `score_total`, `metadata` | 题目结构化胶囊，可先 shadow |
| `question_rubrics` | `id`, `question_id`, `sub_question_id`, `artifact_version_id`, `rubric_text`, `score_total`, `status`, `quality_flags`, `metadata` | 评分标准总包 |
| `scoring_points` | `id`, `rubric_id`, `point_no`, `point_text`, `score`, `required`, `accepted_expressions`, `negative_patterns`, `confidence`, `metadata` | 采分点 |
| `artifact_evidence_refs` | `id`, `artifact_type`, `artifact_id`, `source_id`, `source_span`, `quote_hash`, `alignment_score`, `use_surface`, `metadata` | field-level provenance |
| `rubric_review_queue` | `id`, `artifact_version_id`, `review_status`, `reviewer_id`, `review_notes`, `blocking_flags`, `decision_at` | 人审工作台基础 |
| `eval_cases` | `id`, `eval_set_id`, `question_id`, `student_answer`, `human_score`, `human_point_matches`, `human_mistakes`, `metadata` | golden cases |
| `eval_runs` | `id`, `eval_set_id`, `artifact_version_id`, `runtime_version`, `metrics`, `gate_status`, `created_at` | 评测记录 |

### 7.2 Phase 1 runtime schema

| 表 | 核心字段 | 说明 |
| --- | --- | --- |
| `student_answer_grading_results` | `id`, `student_id`, `attempt_id`, `question_id`, `artifact_version_id`, `score`, `max_score`, `confidence`, `result_json`, `trace_json`, `created_at` | 批改结果快照 |
| `grading_point_matches` | `id`, `grading_result_id`, `scoring_point_id`, `match_status`, `awarded_score`, `evidence_text`, `reason`, `confidence` | 点级命中/漏点 |
| `standard_answer_skeletons` | `id`, `question_id`, `artifact_version_id`, `skeleton_json`, `status` | 答案结构 |
| `common_mistakes` | `id`, `scoring_point_id`, `mistake_type`, `mistake_text`, `diagnosis_hint`, `evidence_refs`, `status` | 常见错因 |
| `question_knowledge_edges` | `id`, `question_id`, `knowledge_point_id`, `edge_type`, `weight`, `evidence_refs`, `metadata` | 题目-知识点关系 |

### 7.3 Phase 2 learner and recommendation schema

| 表 | 核心字段 | 说明 |
| --- | --- | --- |
| `knowledge_points` | `id`, `code`, `title`, `parent_id`, `source_refs`, `metadata` | 一建建筑实务知识点 |
| `learner_weaknesses` | `id`, `student_id`, `knowledge_point_id`, `scoring_point_id`, `severity`, `confidence`, `evidence_attempts`, `last_seen_at` | 薄弱点 |
| `review_plans` | `id`, `student_id`, `plan_json`, `source_weakness_ids`, `status`, `created_at` | 复习计划 |
| `artifact_corrections` | `id`, `artifact_id`, `correction_type`, `patch_json`, `reviewer_id`, `reason`, `created_at` | 人工修正回流 |

### 7.4 JSONB 使用规则

允许 JSONB：

- `metadata`
- `quality_flags`
- `trace_json`
- `skeleton_json`
- `accepted_expressions`
- `negative_patterns`
- `human_point_matches`
- `metrics`

必须 normalized：

- source identity
- artifact version
- question rubric
- scoring point
- evidence ref
- grading result
- point match
- eval run

原因：normalized 字段承担 authority、join、eval、回滚；JSONB 用于探索性扩展和低频附属信息。

### 7.5 pgvector 使用边界

需要 pgvector：

- source span retrieval
- similar question recommendation
- accepted expression semantic match fallback
- evidence candidate discovery

不应由 pgvector 决定：

- scoring point 是否存在
- 分值多少
- 是否写入长期学情
- published artifact 状态

---

## 8. 服务层设计

### 8.1 core services

| Service | 职责 | Phase |
| --- | --- | --- |
| `SourceRegistryService` | source identity, hash, version, source type | P0 |
| `QuestionCapsuleCompiler` | 题目/标准答案结构化 | P0 |
| `RubricArtifactCompiler` | 从标准答案生成 rubric candidate | P0 |
| `EvidenceAlignmentService` | artifact field-level evidence 对齐 | P0 |
| `ArtifactRegistryService` | candidate/published/version lifecycle | P0 |
| `ArtifactReviewService` | review queue, publish, reject, correction | P0/P1 |
| `LubanKnowledgeQueryService` | typed query protocol | P0/P1 |
| `ArtifactFirstGradingService` | retrieve rubric -> kernel -> result | P1 |
| `PointMatchPersistenceService` | 保存 grading_point_matches | P1 |
| `LearnerWeaknessService` | 从 point matches 推导薄弱点 | P1/P2 |
| `ReviewPlanService` | 生成复习计划 | P2 |
| `KnowledgeEngineEvalService` | eval cases/runs/gates | P0/P1 |

### 8.2 service APIs

```python
retrieveRubric(questionId: str, subQuestionId: str | None = None) -> RubricContextPack
```

```python
gradeCaseAnswer(
    questionId: str,
    studentAnswer: str,
    studentId: str | None = None,
    attemptId: str | None = None,
) -> ArtifactBackedCaseGradingResult
```

```python
diagnoseWeakness(studentId: str, window: str = "90d") -> LearnerWeaknessReport
```

```python
recommendReviewPlan(studentId: str, goal: str = "case_score_improvement") -> ReviewPlan
```

```python
compileQuestionArtifact(questionId: str, sourcePolicy: str = "trusted_2026") -> ArtifactCandidateBundle
```

```python
runGradingEval(evalSetId: str, artifactVersionId: str, runtimeVersion: str) -> EvalRunResult
```

### 8.3 current code integration points

| 目标 | 当前文件/模块 | 改造方式 |
| --- | --- | --- |
| 评分 kernel 接收 artifact | `deeptutor/services/construction_grading/case_kernel.py` | 在 authority order 前增加 published artifact context，不删除现有 fallback |
| 学习证据写回 | `deeptutor/services/construction_grading/writeback.py` | 增加 point match refs 和 artifact version refs |
| Learning evidence normalize | `deeptutor/services/construction_grading/learning_evidence.py` | 保留现有结构，补 `artifact_version_id`, `scoring_point_ids` |
| Source compiler | `deeptutor/services/source_compiler/**` | 把 prototype compiler 升级为 service-level compiler |
| Eval scripts | `scripts/run_answer_rubric_ab_eval.py` | 升级为 golden-based `run_grading_eval` |
| Tests | `tests/services/source_compiler/**` | 增加 artifact schema and release gate tests |

### 8.4 report-driven path priority

报告指出的真实瓶颈不是“召回模块不够强”，而是评分事实未成为一等资产。因此文件优先级必须按“评分真相 -> 点级证据 -> 学习写回 -> 测评会话 -> source compiler”排序，不能从泛 RAG 或图谱平台开始。

| 优先级 | 文件/模块 | 当前事实 | v2.1 执行动作 | 不做什么 |
| --- | --- | --- | --- | --- |
| P0 | `deeptutor/services/construction_grading/case_kernel.py` | 现有主观题评分 authority，按 rubric/keyword 给分 | 增加 published artifact context adapter；保留现有 fallback；trace artifact version | 不新建第二评分 kernel |
| P0 | `deeptutor/services/construction_grading/schema.py` | `CaseGradingResult` 已是 typed result | 补 `point_id`、`artifact_ref`、`citation_ref`、`grading_run_id` 或等价字段 | 不把结构化结果退回纯文本 |
| P0 | `deeptutor/services/construction_grading/learning_evidence.py` | 已把 grading result 归一化为 learner evidence | 补 `scoring_point_hits/misses`、`artifact_version_id`、`provenance_bundle` | 不重建 learner memory |
| P0 | `deeptutor/services/construction_grading/writeback.py` | 已写 `learner_memory_events` 和 mistake book | 增加 writeback eligibility gate；未 publish/低置信结果只 shadow | 不让 candidate artifact 污染长期画像 |
| P0 | `deeptutor/services/source_compiler/answer_rubric_extractor.py` | 已有 answer-derived rubric prototype | 升级为 `RubricArtifactCompiler`，输出稳定 candidate schema | 不保持脚本孤岛 |
| P0 | `deeptutor/services/source_compiler/rubric_evidence_aligner.py` | 已有 evidence alignment prototype | 升级为 `EvidenceAlignmentService`，写 `artifact_evidence_refs` | 不把 citation 当展示装饰 |
| P1 | `deeptutor/services/assessment/session_repository.py` | `client_questions_public/session_questions_private` 已分离 | 在 private result/report 引用 artifact refs and eval metadata | 不泄露 hidden grading artifacts |
| P1 | `deeptutor/services/assessment/scoring.py` | 主要是 objective exact-match | 不强行改造成主观题评分器；先接 artifact refs and learner evidence bridge | 不把 objective scorer 扩成第二 rubric authority |
| P1 | `deeptutor/services/rag/compiled_truth_source.py` | 已有 compiled truth 思想 | 作为 read-side context source，与 artifact registry 对齐 | 不让 RAG truth source 覆盖 scoring artifact authority |
| P1 | `deeptutor/services/source_compiler/graph_projection.py` | 有 graph projection 雏形 | 只承接 `question_knowledge_edges` and weakness aggregation | 不用 graph edge 决定分数 |
| P2 | `deeptutor/services/source_compiler/lecture_compiler.py` | 讲义编译基础 | 作为 evidence and explanation enrich source | 不让讲义覆盖标准答案/规范证据 |

### 8.5 implementation invariants

以下约束来自报告中的代码审计和架构判断，实施时不可降级：

- `CaseGradingSkillKernel` 是 P0 runtime grading authority；新增服务只能给它提供 published context pack。
- `learning_evidence` 是学习事实写回主脊梁；新增表负责点级事实与 artifact refs，不创建平行 learner memory。
- `assessment_sessions.client_questions_public` 不能包含 scoring points、标准答案、hidden rubric 或 reviewer notes。
- `RAGService` 和 `pgvector` 只能用于 evidence candidate discovery、source span retrieval、相似题或表达变体辅助。
- `artifact_versions.status = published` 是 runtime 使用门槛；candidate/review-required/blocked 不进入学生长期画像。
- 所有 artifact publish 必须能重跑 eval；无法 eval 的 artifact 只能 internal shadow。

---

## 9. 分阶段路线图

### Phase 0: Knowledge Engine Foundation and Scoring Truth Core

目标：建立 artifact registry、rubric/scoring point/evidence/ref/eval 的最小可发布闭环。

交付物：

- `knowledge_sources`
- `artifact_versions`
- `question_capsules`
- `question_rubrics`
- `scoring_points`
- `artifact_evidence_refs`
- `rubric_review_queue`
- `eval_cases`
- `eval_runs`
- source/rubric/evidence compiler services
- publish gate CLI

验收标准：

- 20 道一建建筑实务案例题可复跑生成 artifact candidates。
- 每个 scoring point 有 source/evidence/ref 或明确 missing evidence flag。
- Reviewer 可以看到 publish/block/review-required 清单。
- Candidate -> published 状态流转可 diff、可 rollback。
- 至少 100 份学生答案 golden 样本 schema ready，即使数据尚未完全填充。

文件改动：

- `deeptutor/services/source_compiler/**`
- `scripts/compile_2026_rubric_artifact_mvp.py` rename/refactor into non-prototype compiler script
- `scripts/run_answer_rubric_ab_eval.py` evolve into artifact/eval runner
- `tests/services/source_compiler/**`
- `supabase/migrations/*knowledge_engine*.sql`

### Phase 1: Artifact-first Grading Runtime

目标：让 published artifact 真正进入案例题批改链路。

交付物：

- `LubanKnowledgeQueryService.retrieveRubric`
- `ArtifactFirstGradingService.gradeCaseAnswer`
- `student_answer_grading_results`
- `grading_point_matches`
- `CaseGradingSkillKernel` artifact context support
- learner evidence writeback eligibility gate

验收标准：

- 对同一题，runtime trace 记录 artifact version。
- 输出包含 point-level hit/miss/partial reason。
- 只有 published artifact 的 grading result 可写入长期 learner memory。
- Golden eval 达到初始门槛：平均分差、采分点 recall、hallucination rate、citation accuracy 均有可执行报告。

文件改动：

- `deeptutor/services/construction_grading/case_kernel.py`
- `deeptutor/services/construction_grading/learning_evidence.py`
- `deeptutor/services/construction_grading/writeback.py`
- `tests/services/construction_grading/**`

### Phase 2: Learner Diagnosis and Review-plan Engine

目标：从点级批改结果产生可解释、可复测的学情画像和训练建议。

交付物：

- `common_mistakes`
- `question_knowledge_edges`
- `knowledge_points`
- `learner_weaknesses`
- `review_plans`
- `diagnoseStudentWeakness`
- `recommendReviewPlan`
- `compareAttempts`

验收标准：

- 学员薄弱点可以点回具体题、具体采分点、具体作答、具体 evidence。
- Review plan 不能只给泛泛建议，必须给下一题/下一组训练 intent。
- 同一题多次作答能显示 point-level 进步和剩余缺口。

文件改动：

- `deeptutor/services/learner_state/**`
- `deeptutor/services/construction_grading/**`
- existing assessment/testset recommendation modules
- learner workspace read model modules

### Phase 3: Typed Tutor Protocol and Teaching Dialogue

目标：AI 老师对话不再临时 RAG，而是调用 typed query protocol 解释、追问、复盘。

交付物：

- `explainScoringPoint`
- `retrieveEvidencePack`
- tutor context pack integration
- student-facing citation bundle
- appeal/regrade support

验收标准：

- 学员问“为什么扣分”，系统能返回 point-level reason + accepted expression + evidence。
- 学员问“怎么改”，系统能基于 missed points 改写答案，不泄露未授权隐藏答案。
- TutorBot 继续复用统一 `/api/v1/ws`，不新增专用路由。

文件改动：

- TutorBot skill context builder
- `deeptutor/runtime/orchestrator.py` only as thin wrapper if needed
- `deeptutor/services/construction_grading/**`
- `deeptutor/services/learner_state/**`

### Phase 4: Eval-driven Knowledge Operations

目标：让鲁班知识层形成持续自改进能力。

交付物：

- artifact drift report
- coverage dashboard
- reviewer correction loop
- eval trend dashboard
- compiler quality regression gate
- yearly source update impact analysis

验收标准：

- artifact version 变更必须自动触发 eval。
- 新教材/规范导入能报告影响了哪些题、哪些采分点、哪些学员弱点解释。
- 低质量 source/evidence/candidate 不会自动 publish。

---

## 10. Work Packages

### WP0: Authority and Terminology Freeze

- [ ] 把 v2.1 标记为当前计划 authority。
- [ ] 在 `docs/plan/INDEX.md` 中将 v1.2 标记为被 v2.1 superseded。
- [ ] 禁止新增“rubric 中台”“新 RAG runtime”“Nexus clone”等平行概念。
- [ ] 明确 `grading rubric` 是 Scoring Truth Core，不是整个 Knowledge Engine。

### WP1: Source Registry and Artifact Versioning

- [ ] 建 `knowledge_sources` shadow schema。
- [ ] 建 `artifact_versions` shadow schema。
- [ ] 把 `docs/2026` source inventory 接到 Source Registry。
- [ ] 支持 source hash、source type、year、version、origin path。

### WP2: Question Capsule and Rubric Compiler

- [ ] 将 prototype extractor 升级为 `QuestionCapsuleCompiler` and `RubricArtifactCompiler`。
- [ ] 输出 `QuestionCapsuleArtifact`、`QuestionRubricArtifact`、`ScoringPointArtifact`。
- [ ] 继续支持 answer-derived rubric，但标记 confidence and flags。
- [ ] 处理多问、表格、图示、计算题、材料题。

### WP3: Evidence Alignment and Provenance

- [ ] 建 `artifact_evidence_refs`。
- [ ] 将教材/规范/讲义/truth answer evidence 分层。
- [ ] 输出 citation bundle and evidence quality flags。
- [ ] 对 missing/conflicting evidence 设置 blocking flag。

### WP4: Review and Publish Gate

- [ ] 建 `rubric_review_queue`。
- [ ] 支持 candidate diff、approve、block、request correction。
- [ ] Published artifact 才能进入 runtime。
- [ ] Publish 前必须过 coverage/eval/PII/client-leak gate。

### WP5: Luban Typed Query Protocol

- [ ] 定义 `RubricContextPack` schema。
- [ ] 实现 `retrieveRubric`。
- [ ] 定义 `ArtifactBackedCaseGradingResult` schema。
- [ ] 为 query trace 添加 artifact/version/evidence refs。

### WP6: Artifact-first Grading Runtime

- [ ] 在 `CaseGradingSkillKernel` 前接 published artifact context。
- [ ] 保留现有 `grading_key.scoring_points`、row rubric、projected rubric、open_skill fallback。
- [ ] 持久化 `student_answer_grading_results`。
- [ ] 持久化 `grading_point_matches`。
- [ ] 未过 confidence gate 不写长期 learner memory。

### WP7: Learner Diagnosis and Review Plan

- [ ] 从 point matches 生成 weakness evidence。
- [ ] 将 weakness 绑定 knowledge point and scoring point。
- [ ] 生成 review plan and next training intent。
- [ ] 支持 compare attempts。

### WP8: Eval and Governance

- [ ] 建 20 题、100 份学生答案 golden eval set。
- [ ] 指标：score deviation、point precision/recall、mistake accuracy、citation accuracy、hallucination、token、latency。
- [ ] 每次 artifact publish 前后跑 eval。
- [ ] reviewer correction 回流 compiler。

### WP9: Product Surfaces

- [ ] 学生端：point-level explanation and answer improvement。
- [ ] 老师端：review queue and weak-point dashboard。
- [ ] 运营端：coverage and quality dashboard。
- [ ] 内部端：eval trend and release gate。

### WP10: Drift and Yearly Update

- [ ] 2027 教材/规范导入后生成 source diff。
- [ ] 输出 impacted artifacts。
- [ ] 对 affected published artifacts 标记 re-review。
- [ ] 对学生历史报告保留 old version citation，不 retroactively rewrite。

---

## 11. 质量门槛

### 11.1 Phase 0 gates

| Gate | 阈值 |
| --- | --- |
| Source hash completeness | 100% |
| Candidate reproducibility | same input same artifact ids |
| Evidence alignment coverage | >= 70% for publishable set, missing evidence explicit |
| Publishable candidate rate | >= 70% on selected 20题 |
| Review checklist completeness | 100% candidate has action |
| Client leak scan | 0 private scoring artifacts in public payload fixtures |

### 11.2 Phase 1 gates

| Gate | 初始阈值 |
| --- | ---: |
| 平均分差 | <= 1 分 or <= 10% max score |
| 采分点 recall | >= 85% initial, target >= 90% |
| 采分点 precision | >= 80% initial |
| 错因诊断准确率 | >= 75% initial |
| hallucination rate | <= 3% |
| token cost | <= current baseline, target -40% |
| latency | <= current 1.5x |
| citation accuracy | >= 90% for published evidence refs |

### 11.3 Phase 2 gates

| Gate | 阈值 |
| --- | --- |
| Weakness evidence traceability | 100% weakness links to attempts and point matches |
| Review plan specificity | 100% plan has next action and evidence |
| Compare attempts accuracy | 95% point-level diff deterministic |
| Long-term writeback eligibility | only published/high-confidence results |

### 11.4 A/B/C validation design

报告明确要求不要用 Pinecone 的官方数字替代鲁班自己的结果。v2.1 把三路对照升级为 release gate：没有通过这个 gate，artifact-first 只能停留在 shadow，不进入生产主路径。

| 方案 | 输入 | Runtime | 输出 | 用途 |
| --- | --- | --- | --- | --- |
| A Baseline | 当前题目字段、现有 rubric/keywords/fallback | 现有 `CaseGradingSkillKernel` | 当前 `CaseGradingResult` | 衡量今天系统真实能力 |
| B RAG | 检索教材/规范/真题 chunks + 当前题目字段 | RAG context + constrained grader | grading result + citations | 判断传统 RAG 是否足够 |
| C Artifact-first | `QuestionRubricArtifact` + `ScoringPointArtifact` + `EvidenceRefArtifact` + optional mistakes/skeleton | published artifact context + existing kernel + verifier | point-level matches + provenance + learner evidence | 验证 Nexus-like 思想是否产生业务收益 |

实验集：

- 20 道一建建筑实务案例题，覆盖安全、质量、进度、合同索赔、材料、施工组织、规范条文类问题。
- 100 份学生答案，至少包含完整答案、半对答案、口号化答案、表达近义答案、漏关键条件答案、误用规范答案。
- 每份答案需要人工 gold：总分、点级命中、可接受表达、错因、证据来源。

硬指标：

| 指标 | 进入 shadow runtime | 进入生产 runtime |
| --- | ---: | ---: |
| 平均分差 | <= 1.5 分 or <= 15% max score | <= 1 分 or <= 10% max score |
| 采分点 recall | >= 85% | >= 90% |
| 采分点 precision | >= 80% | >= 85% |
| 错因诊断准确率 | >= 75% | >= 85% |
| citation accuracy | >= 85% | >= 90% |
| hallucination rate | <= 5% | <= 3% |
| token cost | 不高于 baseline | 比 baseline 低 >= 40% |
| latency | <= baseline 1.8x | <= baseline 1.5x |
| learning writeback pollution | 0 high-severity pollution | 0 pollution |

决策规则：

- C 明显优于 A 且 B 不稳定：继续 artifact-first。
- B 与 C 接近但 C 成本更低、可解释性更强：继续 artifact-first。
- C 分数准确率不优于 A：停止接 runtime，只保留 reviewer tooling。
- C citation 不达标：禁止学生端引用，只允许 reviewer 内部使用。
- C learner writeback 出现污染：关闭长期写回，只保留 grading result shadow。

### 11.5 Pinecone Nexus claim credibility gate

报告中的可信度评级必须转化成未来重评门槛，否则团队容易被新宣传再次带偏。

| Claim / 能力 | 当前可信度 | 可作为鲁班决策依据吗 | 重新评估条件 |
| --- | --- | --- | --- |
| Nexus 是 Knowledge Engine，把 retrieval 推进为 compilation + typed retrieval | A | 可以，作为架构思想 | 持续观察术语变化，但不影响自研路线 |
| Typed outputs / field-level citations | B | 可以吸收设计，不可假设现成满足中文教育 | 需要 SDK/API 示例、citation schema、迁移能力证明 |
| 30x faster / 90% token reduction / 90%+ task completion | B | 不可直接作为鲁班 ROI 依据 | 必须有鲁班 20题/100答 eval 或独立第三方 benchmark |
| 2.8M tokens -> 4000 tokens | C | 不进入规划指标 | 需要可复现实验或公开方法 |
| Nexus 已适合生产核心评分链路 | D | 不可作为当前路线 | 需要中文/主观题/高可解释评分生产案例，且可导出/回滚 |

因此，未来即便重新评估 Pinecone Nexus，也只能评估以下三种集成形态：

1. Offline comparison：把 Nexus 作为对照工具，验证 typed retrieval 质量。
2. Evidence retrieval accelerator：只加速 source/evidence retrieval，不碰 scoring authority。
3. Interop export/import：如果 Nexus artifacts 可导出，再考虑与鲁班 artifact registry 做互操作。

禁止的集成形态：

- 不允许 Nexus/KnowQL 直接决定分数。
- 不允许 Nexus artifacts 成为唯一评分真相。
- 不允许学生长期画像依赖不可导出的外部 artifact。

---

## 12. 风险与替代方案

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 把 rubric 表误当成完整系统 | 后续学情、对话、推荐继续碎片化 | v2.1 定义全量 artifact 家族和 query protocol |
| 源材料高质量但结构不统一 | compiler 出错、人工成本高 | Source capsule first, review flags, no auto publish |
| 标准答案不等于完整评分细则 | 点级评分偏差 | 人审 + student golden + partial credit eval |
| Evidence alignment 不稳定 | citation 误导用户 | evidence quality flags, internal-only citation until gate |
| LLM verifier 幻觉 | 错误扣分或误诊断 | deterministic kernel first, LLM only constrained by artifact |
| 人审吞吐不足 | 发布速度慢 | 先 20/100 核心题，按高频题优先 |
| 过度架构化 | 研发周期失控 | Phase 0/1 只打通 scoring truth core |
| Vendor lock-in | 未来迁移困难 | 不接 Pinecone Nexus，保持 Postgres/artifact-owned |
| 数据出境/版权 | 合规风险 | 本地/offline compiler, public/private use_surface |
| 学生答案样本不足 | 无法证明准确率 | 先构造+人工标注 100 份，再逐步接真实匿名样本 |

---

## 13. 不做什么

当前不做：

- 不直接接 Pinecone Nexus。
- 不把 KnowQL 作为鲁班 query language。
- 不引入 Neo4j/Memgraph/Kuzu 作为核心依赖。
- 不做全考试、多科目通用知识平台。
- 不新增聊天入口或专用 WebSocket。
- 不自动 publish LLM 生成的 artifact。
- 不让未审核 artifact 影响长期学情。
- 不把运营增长素材生成纳入核心 Knowledge Engine Phase 0/1。

未来可观察：

- Pinecone Nexus SDK/API 公开成熟后，可做离线互操作 POC。
- 如果 graph traversal 成为诊断瓶颈，再引入 dedicated graph DB。
- 如果 Postgres/pgvector retrieval 成本或质量不足，再局部接入专用向量服务。

---

## 14. v2.1 对 v1.2 的吸收

保留：

- answer -> rubric candidate 方法。
- 教材/规范/讲义 evidence alignment。
- review checklist and quality report。
- artifact-first grading 思路。
- point-level persistence。
- eval-driven release gate。
- 不直接接 Pinecone Nexus 的判断。

升级：

- 从 rubric-only 升级为 full artifact system。
- 从 compiler script 升级为 artifact registry and typed query protocol。
- 从 A/B proxy 升级为 golden eval gate。
- 从批改链路升级为 learner diagnosis/recommendation/tutor dialogue/review governance。
- 从一次性计划升级为持续知识运营系统。

撤销或降级：

- “Local prototype evidence”不再作为计划定位，只作为第一批实验证据。
- “P0 只做 rubric”不再成立；P0 是 Knowledge Engine foundation + scoring truth core。
- “Rubric Artifact Layer”不再作为总系统名称，只是 Scoring and Grading Artifacts 分组。

---

## 15. 第一批可交付执行清单

### Week 1

目标：把 v2.1 的 authority 和数据底座定住。

交付：

- [ ] v2.1 plan indexed as current authority。
- [ ] Shadow schema draft for `knowledge_sources`, `artifact_versions`, `question_rubrics`, `scoring_points`, `artifact_evidence_refs`, `eval_cases`, `eval_runs`。
- [ ] Rename/refactor prototype scripts away from `mvp` naming。
- [ ] `QuestionCapsuleArtifact` and `RubricArtifactCandidate` schema tests。
- [ ] 20 题 candidate generation reproducibility gate。

### Week 2

目标：完成 evidence + review + eval shell。

交付：

- [ ] Evidence alignment service returns field-level refs。
- [ ] Review queue JSON/DB shadow output。
- [ ] Publish/block/review-required decision report。
- [ ] 100 份学生答案 eval case schema and fixtures。
- [ ] Eval runner outputs score/point/citation/cost metrics skeleton。

### Week 3-4

目标：接入 runtime，但先 shadow，不污染长期学情。

交付：

- [ ] `retrieveRubric` service。
- [ ] `CaseGradingSkillKernel` artifact context adapter。
- [ ] Shadow `student_answer_grading_results` and `grading_point_matches`。
- [ ] Golden eval first pass。
- [ ] Learning evidence writeback gate。

### Week 5-8

目标：形成产品闭环。

交付：

- [ ] 学生端 point-level explanation。
- [ ] 错因诊断 and common mistake artifacts。
- [ ] learner weakness projection。
- [ ] review plan and next training intent。
- [ ] teacher/reviewer console first cut。
- [ ] eval trend and release gate report。

---

## 16. 最终建议

最终结论：

- 是否直接接入 Pinecone Nexus：暂不。
- 是否自研 Nexus-like 知识编译层：是，而且应升级为鲁班 Knowledge Engine 战略主线。
- 当前最优路径：以评分真相层为 Phase 0/1，但按全量 Knowledge Engine 架构建设 source、artifact、evidence、typed query、runtime、learner、eval/governance 六层。
- 未来重新评估 Pinecone Nexus 条件：公开 SDK/API 成熟、中文教育主观题案例可验证、支持自有 artifact/provenance 迁移、成本和数据合规明确、可离线/混合部署或低锁定集成。
- 第一优先级行动：将 prototype rubric compiler 改造成 Source Registry + Artifact Registry + Evidence Ref + Review Gate。
- 第二优先级行动：把 published rubric artifact 接入 `CaseGradingSkillKernel`，输出 point-level grading matches。
- 第三优先级行动：建立 20 题/100 答案 golden eval，证明分数准确率、采分点 recall、错因准确率和 citation accuracy。

本计划的核心判断是：鲁班不应追逐 Pinecone Nexus 本身，而应把 Nexus 的“编译型知识接口”思想转化为自己的专业教育数据资产和评测闭环。对鲁班而言，真正的壁垒不是拥有更多 chunks，而是拥有一建建筑实务主观题的可审核评分事实、可追溯证据链、可积累学员弱点图谱和可持续变好的 eval/governance loop。
