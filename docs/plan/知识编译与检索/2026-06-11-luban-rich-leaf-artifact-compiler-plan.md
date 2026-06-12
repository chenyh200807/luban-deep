# 鲁班 Rich Leaf Artifact Compiler v0 计划

状态：`Proposed / awaiting user review`

日期：2026-06-11

本文是对 Nexus-like 知识编译下一阶段的冷静复盘与执行计划。目标不是继续补几个 `snippet`，而是把教材、规范、讲义、题库、评分工件和学习证据编译成 LLM 真正能消费的领域工作台，让鲁班评分、TutorBot、RAG、Learning Brain 和移动端提分闭环都能复用同一套结构化知识资产。

本文不执行代码、不写 runtime、不声明 release truth。用户审核通过后，再进入实施计划和 TDD 实现。

## 1. 背景判断

当前已经有不少源数据和中间编译资产：

| 层 | 当前规模 | 说明 |
|---|---:|---|
| canonical taxonomy leaves | 3158 | 知识叶子总量 |
| textbook records | 1303 | 教材编译记录 |
| standard records | 2355 | 标准条文记录 |
| lecture records | 540 | 讲义教学卡 |
| kb chunks | 3596 | 题库/知识 chunks |
| case rubric records | 1221 | 案例评分相关记录 |
| unified knowledge nodes | 395 | 已聚合进 canonical unified context 的 leaf |
| populated leaf rate | 12.5% | 当前最大结构性短板 |

上一批 P0 工作只处理了 `question_without_knowledge` 的 57 个叶子：

- 54 个 strong source candidates -> review-only candidate patch
- 3 个 weak leaves -> pollution refinement queue

这不是全量知识编译，只是 coverage gap repair。它证明了编译闭环形状成立：

```text
coverage gap
-> typed work order
-> source candidate evidence
-> strong/weak 分层
-> 审核/回归后进入 runtime
```

但它没有证明系统已经达到 Nexus-like 知识能力。现在的 compiled context 仍偏薄，主要像：

```text
leaf -> source snippets / counts / matched_terms / provenance
```

目标应升级为：

```text
leaf -> concepts / definitions / rules / procedures / constraints / exam patterns / mistakes / negative evidence / grading relevance / learner event templates
```

## 2. 为什么之前效果没有明显全面胜出

当前判断：Nexus-like 方向没有被证伪，真正问题是编译深度与 runtime consumption 都不足。

### 2.1 编译资产太薄

`snippet + matched_terms` 可以减少检索成本，但不能显著提升 LLM 的领域推理。LLM 仍要自己从片段中归纳规则、判断例外、识别考试模式和解释错因。

要让模型明显变强，编译层必须提前完成这些认知工作：

- 把概念定义从原文中抽出来。
- 把规范条文变成可执行 rule。
- 把施工流程变成 procedure。
- 把尺寸、时间、数量、阈值变成 numeric constraints。
- 把题库变成 exam pattern，而不只是 exercise chunk。
- 把常见错因变成 mistake taxonomy。
- 把污染源变成 negative evidence。
- 把评分采分点和知识叶子对齐成 grading relevance。
- 把可进入 Learning Brain 的事件模板提前定义出来。

### 2.2 评测指标没有直接测 rich compilation 的收益

之前 A/B 更多在测：

- artifact-first scoring protocol 是否比 current RAG 好。
- fail-open 是否下降。
- evidence span 是否存在。
- token/latency 是否改善。
- release gate / bucket / authority 是否合规。

这些重要，但不是 rich semantic compilation 的直接指标。新阶段必须专门测：

- LLM 是否更少误引。
- 是否能解释为什么错。
- 是否能识别近义误踩、术语不准、少项、错路径。
- 是否能更稳定生成 Learning Brain 事件。
- 是否能从同一 leaf 支撑评分、讲解、复练、下一题推荐。

### 2.3 过度保守导致 candidate 停留在 workbench

过去正确地避免了把 AI 候选误升为 truth，但副作用是很多候选只停在 artifact/report，没有进入 versioned runtime supply candidate。因此 runtime 并没有真正吃到足够强的 compiled context。

正确做法不是放松纪律，而是补齐中间层：

```text
candidate workbench
-> reviewed rich artifact candidate
-> versioned runtime_supply candidate
-> regression A/B
-> controlled default decision
```

## 3. 使用场景反推

RichLeafArtifact 不是为了好看，而是服务真实场景。

### 3.1 案例题评分

问题：学生答案是否命中采分点、哪里错、为什么错、该不该给部分分。

需要字段：

- `definitions`
- `rules`
- `procedures`
- `numeric_constraints`
- `exam_patterns`
- `rubric_link_index`
- `negative_evidence`
- `source_refs`

收益目标：

- 降低 fail-open。
- 降低 wrong-path citation。
- 改善 multi-part scoring。
- 改善 near-synonym / exact-required 判断。
- 让 runtime LLM judge 只裁决学生答案，不重新发明 rubric。

### 3.2 TutorBot 知识问答

问题：学生问任意建筑实务知识，系统要能准确、可引用、不过度拒答。

需要字段：

- `concepts`
- `definitions`
- `rules`
- `procedures`
- `teaching_cards`
- `source_refs`
- `negative_evidence`

收益目标：

- open-world teaching 不再只靠长 chunk RAG。
- 回答能给出稳定结构，而不是每次从片段现想。
- 遇到不确定内容能进入 candidate work order，不直接编造。

### 3.3 RAG / Compiled Context Pack

问题：runtime 需要按任务裁剪最有价值上下文，而不是塞全量材料。

需要字段：

- `source_refs`
- `concepts`
- `rules`
- `exam_patterns`
- `rubric_link_index`
- `retrieval_hints`
- `budget_profile`

收益目标：

- 编译层给 LLM “答案工作台”，不是只给 raw chunk。
- token 下降是结果，不是目标。
- 同一 leaf 可以被评分、问答、推荐复用。

### 3.4 Learning Brain / Grading-to-Brain Loop

问题：一次批改如何变成长期学习画像和下一步训练动作。

需要字段：

- `learner_memory_event_templates`
- `common_mistakes`
- `exam_patterns`
- `rubric_link_index`
- `teaching_cards`

收益目标：

- 批改结果能稳定写成 `learner_memory_events`。
- 错因不是一句泛化评语，而是可积累的 claim 证据。
- 下一题推荐能绑定同类 leaf、同类 mistake、同类 scoring point。

### 3.5 移动端提分闭环

问题：用户每天需要知道练什么、为什么练、练完怎么复测。

需要字段：

- `teaching_cards`
- `exam_patterns`
- `common_mistakes`
- `learner_memory_event_templates`
- `next_action_affordances`

收益目标：

- 移动端不是展示知识库，而是展示“今日最该训练的动作”。
- 复练任务能从同一个 rich artifact 生成。

### 3.6 教师/AI 审核工作台

问题：AI 编译的候选是否能被快速审查，不让 reviewer 淹没在 raw source。

需要字段：

- `source_refs`
- `field_authority`
- `candidate_confidence`
- `validator_findings`
- `negative_evidence`
- `audit_status`

收益目标：

- 审核对象是字段级 claim，而不是整篇材料。
- 一眼知道哪个字段来自教材、哪个来自题库、哪个只是 AI 候选。

## 4. RichLeafArtifact v0 Schema

建议 schema 名称：`luban.rich_leaf_artifact.v0`

顶层字段：

```json
{
  "schema": "luban.rich_leaf_artifact.v0",
  "artifact_id": "rich_leaf:<leaf_id>:<version>",
  "leaf_id": "...",
  "leaf_path": "...",
  "version": "candidate_20260611",
  "candidate_status": "candidate | reviewed_candidate | release_candidate | superseded",
  "authority": {},
  "concepts": [],
  "definitions": [],
  "rules": [],
  "procedures": [],
  "numeric_constraints": [],
  "common_mistakes": [],
  "exam_patterns": [],
  "source_refs": [],
  "negative_evidence": [],
  "teaching_cards": [],
  "rubric_link_index": [],
  "learner_memory_event_templates": [],
  "retrieval_hints": {},
  "runtime_profiles": {},
  "audit": {},
  "safety": {}
}
```

### 4.0 Core Schema vs Derived Views

为避免把一个计划写成多套 truth，v0 明确区分三类字段：

| 类别 | 字段 | 存放位置 | 原因 |
|---|---|---|---|
| Core artifact | `authority`, `source_refs`, `definitions`, `rules`, `procedures`, `numeric_constraints`, `negative_evidence`, `teaching_cards`, `rubric_link_index` | `RichLeafArtifact` | runtime 会直接消费，且可做 source/audit 验证 |
| Candidate-only extension | `common_mistakes`, `learner_memory_event_templates`, `retrieval_hints`, `runtime_profiles` | `RichLeafArtifact`，但默认 `candidate_only=true` | 有产品价值，但不能直接升 release truth |
| Derived view / audit report | `field_authority`, `candidate_confidence`, `validator_findings`, `audit_status`, `next_action_affordances`, `budget_profile` | validator/auditor/CompiledContextPack report | 这些是编译或 runtime 派生视图，不是 leaf 事实本身，不能写成第二套 authority |

因此，本文前面使用场景中提到的 `field_authority` / `candidate_confidence` / `validator_findings` / `audit_status` 不进入 `RichLeafArtifact` 顶层；它们由 validator/auditor 根据 core artifact 生成。`next_action_affordances` 也不进入 leaf artifact 顶层，而由 Learning Brain / mobile ViewModel 从 `teaching_cards + exam_patterns + learner_memory_event_templates` 派生。`budget_profile` 不属于 leaf truth，由 `CompiledContextPack.budget_policy` 在 runtime 组包时计算。

这是 thin wrappers / fat skills 的边界：RichLeafArtifact 是胖的 compiled context skill；surface adapter 只读它并派生自己的 view，不反向写回 leaf truth。

### 4.0.1 Field Claim Envelope

除 `source_refs`、`authority`、`audit`、`safety` 这类控制字段外，所有数组型语义字段的 item 必须包统一 claim metadata。没有 metadata 的字段不得进入 `reviewed_candidate`。

```json
{
  "field_id": "...",
  "field_type": "definition | rule | procedure | numeric_constraint | exam_pattern | teaching_card | rubric_link | mistake | learner_template",
  "claim_status": "source_backed | candidate_only | rejected | needs_review",
  "source_support": {
    "source_ref_ids": [],
    "support_type": "verbatim | normalized_summary | inferred_from_multiple_sources | question_pattern | learner_evidence",
    "minimum_support_span_required": true
  },
  "validator_result": {
    "status": "pass | fail | not_exercised",
    "validator_version": "...",
    "failure_reason": null
  },
  "reviewer_decision": {
    "status": "not_reviewed | accepted | accepted_candidate_only | rejected",
    "review_authority": "deterministic_validator | evidence_auditor | governance_council",
    "decision_id": null
  }
}
```

规则：

- `candidate_only` 默认不能被 runtime positive scoring 使用。
- `source_backed` 必须有 `source_ref_ids` 和 validator pass。
- `rejected` 字段保留在 audit/rejected report，不进入 positive context。
- `needs_review` 字段只能进入 review pack，不进入 student-facing answer。
- release gate 以 field item 为单位，不以整张 leaf artifact 为单位。

### 4.1 Authority

```json
{
  "taxonomy_authority": {
    "source": "canonical_taxonomy_index",
    "leaf_id": "...",
    "content_hash": "..."
  },
  "source_authority": [
    {
      "source_lane": "textbook | standard | lecture | question_bank | student_answer | rubric | residual",
      "authority_level": "source_truth | teaching_evidence | assessment_evidence | learner_evidence | candidate_only",
      "content_hash": "...",
      "path": "...",
      "record_id": "..."
    }
  ],
  "compiler_authority": {
    "compiler": "rich_leaf_artifact_compiler",
    "mode": "llm_assisted_candidate_plus_deterministic_validator",
    "model_roles": []
  }
}
```

原则：

- taxonomy 只来自 canonical taxonomy，不由 LLM 改。
- 教材/规范原文是 source truth。
- 讲义是 teaching evidence，不覆盖教材/规范。
- 题库是 assessment evidence，不自动成为规范事实。
- 学生答案是 learner evidence 或 sample evidence，不是 label truth。
- LLM 输出只能是 candidate organization，不是 source authority。

### 4.1.1 Source Lane Registry

RichLeafArtifact 不直接信任 `path + record_id`。Phase 0 必须先生成或引用 source lane registry：

```json
{
  "source_registry_id": "source_registry:docs2026:<date>",
  "source_dataset_id": "docs2026",
  "source_version": "2026-06-11",
  "extractor_version": "...",
  "lanes": [
    {
      "source_lane": "textbook",
      "authority_level": "source_truth",
      "root": "/Users/yehongchen/Documents/CYH_2/Markzuo/FastAPI20251222/docs/2026/2026教材/第二次加强",
      "content_hash": "...",
      "supersedes": []
    }
  ],
  "conflict_priority": ["standard", "textbook", "rubric", "question_bank", "lecture", "student_answer", "residual"]
}
```

规则：

- `source_refs` 必须引用 `source_registry_id + source_lane + record_id + span_hash`。
- 标准和教材冲突时，不能由 LLM 自行裁决；进入 `source_conflict` audit。
- 讲义只能补教学表达，不能覆盖规范/教材。
- 题库解析只能生成 exam pattern / rubric link candidate，不能生成规范 rule。
- student answer/residual 只能进入 learner evidence 或 observed mistake，不进入 source truth。

### 4.2 Concepts

用途：定义本 leaf 的核心概念、别名、边界。

```json
{
  "concept_id": "...",
  "name": "...",
  "aliases": [],
  "scope_note": "...",
  "source_ref_ids": [],
  "authority_level": "source_backed | inferred_candidate"
}
```

风险：

- alias 不能被自动当成 exact-required 得分词。
- 概念边界不清时必须 candidate-only。

### 4.3 Definitions

用途：给 TutorBot、RAG、评分解释提供稳定定义。

```json
{
  "definition_id": "...",
  "text": "...",
  "source_ref_ids": [],
  "verbatim_span": "...",
  "normalized_summary": "...",
  "authority_level": "source_backed"
}
```

规则：

- 必须有 `source_ref_ids`。
- 如果没有原文 span，只能是 `inferred_candidate`。

### 4.4 Rules

用途：把规范/教材要求编译成可执行判断。

```json
{
  "rule_id": "...",
  "condition": "...",
  "requirement": "...",
  "consequence": "...",
  "rule_type": "mandatory | recommended | forbidden | classification | acceptance",
  "source_ref_ids": [],
  "validator_type": "deterministic_possible | llm_required | human_review_required"
}
```

规则：

- mandatory/forbidden 必须来自教材/规范/已签发 rubric。
- LLM 不能凭题库解析创造 mandatory rule。

### 4.5 Procedures

用途：施工流程、答题步骤、检查流程。

```json
{
  "procedure_id": "...",
  "name": "...",
  "steps": [
    {
      "order": 1,
      "action": "...",
      "required": true,
      "source_ref_ids": []
    }
  ],
  "source_ref_ids": [],
  "common_omissions": []
}
```

### 4.6 Numeric Constraints

用途：尺寸、时间、数量、比例、阈值。

```json
{
  "constraint_id": "...",
  "subject": "...",
  "operator": ">=",
  "value": 2,
  "unit": "扣",
  "condition": "...",
  "source_ref_ids": [],
  "deterministic_checkable": true
}
```

规则：

- numeric 不能只存在自然语言里，必须结构化。
- 单位、条件、适用对象缺一项则不能进入 `release_candidate`，更不能被外部 runtime pointer 指为 `controlled_default`。

### 4.7 Common Mistakes

用途：错因诊断和 Learning Brain claim。

```json
{
  "observed_mistakes": [
    {
      "mistake_id": "...",
      "mistake_type": "near_synonym | missing_item | wrong_path | unsupported_external_fact | calculation_error | vague_answer",
      "description": "...",
      "observed_from": "student_answer | residual | teacher_review | teacher_final",
      "evidence_refs": [],
      "learner_claim_hint": "...",
      "authority_level": "learner_evidence"
    }
  ],
  "hypothesized_mistakes": [
    {
      "mistake_id": "...",
      "mistake_type": "...",
      "description": "...",
      "observed_from": "synthetic_candidate | council_shadow | ai_review_suggestion",
      "candidate_reason": "...",
      "authority_level": "candidate_only"
    }
  ]
}
```

规则：

- common mistake 不是教材事实。
- 没有真实学生答案/残差/审核证据时，只能是 synthetic candidate。
- 不能用 synthetic mistake 写 canonical learner truth。
- `observed_mistakes` 可以进入 Learning Brain evidence loop，但仍需真实 grading event 触发。
- `hypothesized_mistakes` 只能进入 review queue 或教学提示候选，不得写 learner claim。
- `council_shadow` / AI 专家团输出默认属于 `hypothesized_mistakes`，不能标 `learner_evidence`，不能 release 为 learner fact。只有当它绑定真实学生作答、真实 grading event、teacher-final 或 canonical claim gate disposition 后，才可通过 Learning Brain authority 形成 learner evidence。

### 4.8 Exam Patterns

用途：真题考法、题型模式、常见采分方式。

```json
{
  "pattern_id": "...",
  "question_type": "mcq | case_subquestion | calculation | list | judgment",
  "pattern": "...",
  "expected_answer_shape": "...",
  "rubric_link": "...",
  "question_refs": [],
  "sample_count": 0,
  "corpus_id": "...",
  "question_set_version": "...",
  "time_range": "...",
  "frequency_hint": "low | medium | high | unknown"
}
```

规则：

- exam pattern 来自题库，不等于教材规范。
- `frequency_hint` 必须由 `sample_count + corpus_id + question_set_version + time_range` 推导；缺任一项则只能为 `unknown`。

### 4.9 Source Refs

用途：所有字段的可追溯底座。

```json
{
  "source_ref_id": "...",
  "source_lane": "textbook | standard | lecture | question_bank | rubric | student_answer",
  "path": "...",
  "record_id": "...",
  "content_hash": "...",
  "span": "...",
  "span_hash": "...",
  "authority_level": "...",
  "license_or_visibility": "internal_training_source"
}
```

规则：

- source refs 是全 schema 的硬地基。
- 字段没有 source_ref 时不得升 release_candidate，除非该字段明确允许 candidate-only。

#### 4.9.1 Source Span Hash Policy

为避免 verifier 在中文空白、表格、公式和 OCR 噪声上不稳定，v0 统一 `span_hash` 计算规则：

1. `raw_span` 必须来自可读 `source_path + record_id`。
2. `normalized_span = normalize(raw_span)`，规则为：
   - Unicode NFKC。
   - 中文全角/半角归一。
   - 连续空白折叠为单个空格。
   - Markdown 表格保留单元格文本，去除对齐符 `:---:`。
   - LaTeX/公式保留原始 token，不做数值重排。
   - 不删除中文标点；只归一常见等价标点。
3. `span_hash = sha256(normalized_span)`.
4. validator 必须同时记录 `raw_span_preview` 与 `span_hash`。
5. 如果 source 是图片/OCR 或 docx render，只能标 `ocr_span_candidate`，不能 release_candidate，除非有文本源二次校验。

任何字段如果只能通过“同词出现在同一大段”证明，而不能给出最小支持 span，必须降级为 `candidate_only` 或 `needs_review`。

### 4.10 Negative Evidence

用途：防 wrong-path、source pollution、过度给分。

```json
{
  "negative_id": "...",
  "negative_type": "wrong_path | generic_path_term_only | near_synonym_not_accepted | external_source_required | unsupported_positive",
  "description": "...",
  "blocked_terms": [],
  "blocked_source_refs": [],
  "reason": "...",
  "validator_action": "fail_closed | needs_review | exclude_candidate"
}
```

规则：

- negative evidence 是防 fail-open 的关键，不是附属字段。
- 所有污染源修复都应沉淀到这里，而不是只留在一次性报告。

### 4.11 Teaching Cards

用途：面向学生解释、复习、移动端训练。

```json
{
  "card_id": "...",
  "audience": "beginner | exam_cram | advanced | mistake_repair",
  "title": "...",
  "explanation": "...",
  "micro_examples": [],
  "source_ref_ids": [],
  "not_for_official_scoring": true
}
```

规则：

- teaching card 可更口语，但不能引入无源事实。
- `not_for_official_scoring=true` 必须默认存在。

### 4.12 Rubric Link Index

用途：把 leaf 与采分点、rubric、评分工件建立引用索引。它不复制评分规则，不执行 partial credit，不改变 rubric。

```json
{
  "rubric_link_id": "...",
  "scoring_artifact_id": "...",
  "rubric_version": "...",
  "question_ids": [],
  "scoring_point_ids": [],
  "rubric_source_ref_ids": [],
  "link_reason": "same_leaf | source_ref_overlap | explicit_rubric_binding",
  "link_status": "candidate_only | source_backed | reviewed"
}
```

规则：

- 只能存 `scoring_artifact_id / rubric_version / scoring_point_id / source_ref_ids` 等引用。
- 禁止复制 `policy_type`、`required_terms`、`partial_credit_policy`、`high_risk_flags` 等可执行评分规则。
- Runtime GradingPacket 必须回读 canonical scoring artifact/rubric；RichLeafArtifact 只帮助定位相关 rubric。
- 若 rubric 不存在或未签发，该 link 只能是 `candidate_only`。

### 4.13 Learner Memory Event Templates

用途：把评分结果稳定转成 Learning Brain 事件。

```json
{
  "template_id": "...",
  "event_type": "case_grading_completed",
  "trigger_conditions": [],
  "required_bindings": {
    "grading_result_id": "...",
    "scoring_artifact_version": "...",
    "scoring_point_id": "...",
    "student_answer_span": "...",
    "evidence_span": "...",
    "mistake_id": "...",
    "teacher_final_or_review_source": "none | teacher_final | qa_review | council_shadow_candidate",
    "claim_gate_disposition": "not_exercised | candidate | accepted | rejected",
    "retest_target": {
      "leaf_id": "...",
      "question_family_id": "...",
      "success_condition": "same_scoring_point_hit | mistake_type_absent | score_delta_positive"
    }
  },
  "claim_candidates": [],
  "next_action_hints": [
    {
      "next_action_type": "review_source | retry_same_point | near_transfer_question | terminology_drill | teacher_review",
      "personalization_level": "none | generic | evidence_backed | teacher_final_backed"
    }
  ],
  "canonical_write_allowed": false
}
```

规则：

- template 不是 learner truth。
- 真实 learner claim 仍由 Learning Brain / canonical claim gate 决定。
- 没有 `grading_result_id + scoring_point_id + student_answer_span/evidence_span` 的 event template 只能生成教学建议，不能生成 learner claim candidate。
- `council_shadow_candidate` 只能作为 review source，不得把 `claim_gate_disposition` 置为 accepted。
- mobile/PCP 输出必须携带 `personalization_level`，避免 generic hint 被展示成个性化主治建议。

## 5. Field-level Authority Matrix

| 字段 | 唯一 authority | LLM 可做 | validator 必做 | release 条件 |
|---|---|---|---|---|
| `leaf_id`, `leaf_path` | canonical taxonomy | 不可改，只可引用 | 校验存在 | taxonomy hash 匹配 |
| `concepts` | source refs + taxonomy | 归纳候选 | source span / alias 风险校验 | source-backed 或 candidate-only |
| `definitions` | 教材/规范/讲义 | 摘要/规范化 | span/hash 校验 | 有 source_ref |
| `rules` | 教材/规范/rubric | 抽取候选 | rule type + source 校验 | mandatory 必须 source-backed |
| `procedures` | 教材/规范/讲义 | 拆步骤 | 顺序/source 校验 | source-backed |
| `numeric_constraints` | 教材/规范/rubric | 抽取候选 | 数值/单位/条件校验 | deterministic checkable |
| `common_mistakes` | 学生答案/residual/teacher/council | 聚类/命名 | evidence provenance 校验 | 非 synthetic 才可 release |
| `exam_patterns` | 题库 | 归纳题型 | question refs 校验 | 样本量标注 |
| `source_refs` | source lanes | 不可伪造 | path/hash/span 校验 | 必须可读 |
| `negative_evidence` | audit/residual/source pollution | 解释候选 | blocker 校验 | 进入 validator |
| `teaching_cards` | source-backed artifact | 生成表达 | factuality/source 校验 | not_for_official_scoring |
| `rubric_link_index` | scoring artifact/rubric | 连接候选 | rubric id 校验 | 只存引用，不复制 rubric policy |
| `learner_memory_event_templates` | Learning Brain schema | 生成模板 | no canonical write 校验 | canonical_write_allowed=false |

## 6. 单一权威设计

RichLeafArtifact 不能成为第二套真相库。它是 compiled context authority，但不是所有事实的 source authority。

### 6.1 一等业务事实

本阶段维护的唯一业务事实：

```text
给定 canonical leaf，系统能拿到一份可追溯、可裁剪、字段级授权的 rich context，用于评分、讲解、复练和学习证据生成。
```

### 6.2 单一 authority 划分

| 事实 | 单一 authority |
|---|---|
| 知识树结构 | canonical taxonomy |
| 教材/规范/讲义原文 | docs/2026 source lanes + source hashes |
| 题库考法 | question bank compiled records |
| 评分采分点 | scoring artifact/rubric |
| learner truth | Learning Brain / canonical claim gate |
| compiled runtime context | versioned runtime_supply rich leaf bundle |
| release promotion | deterministic release gate + governance sign-off |

### 6.2.1 Lifecycle Transition Matrix

`candidate_status` 是 artifact 内部状态；`controlled_default` 不是 artifact 自带状态，而是外部 runtime pointer / release manifest 的指向结果。任何推进都必须通过下表，禁止手动把 candidate 翻成 release，禁止让 artifact 自我声明已默认上线。

| From | To | 唯一 writer | 必需证据 | 禁止条件 | 回滚/退出 |
|---|---|---|---|---|---|
| raw source | candidate | LLM semantic structurer via compiler runner | source inventory、source candidate pool、compiler prompt/version、candidate artifact hash | LLM mint source_ref、无 source_path/record_id | 删除 candidate，保留 work order |
| candidate | reviewed_candidate | evidence auditor + deterministic validator | schema pass、source_ref pass、field disposition、rejected fields report | unsupported mandatory rule、unsupported numeric、accepted pollution | 降回 candidate 或 rejected |
| reviewed_candidate | release_candidate | release compiler gate | validator report 100% required pass、auditor threshold pass、manifest/hash/pointer、safety flags | `canonical_truth_written=true`、`official_score_allowed=true`、未审字段混入 release fields | supersede candidate bundle |
| release_candidate | controlled_default pointer | user/governance authorization + runtime A/B gate | A/B pass、runtime pack smoke、rollback pointer、observability plan、explicit authorization | production/default flag 无授权、A/B not_exercised、source pollution regression、artifact 自带 controlled_default 字段 | kill switch / pointer rollback |
| any active | superseded | runtime_supply release manager | superseding artifact id、reason、rollback plan | 删除历史 artifact、覆盖旧 hash | 保留 immutable artifact 和 pointer history |

状态机不授予评分权。即使外部 pointer 指向某个 bundle 作为 `controlled_default`，`official_score_allowed` 仍由 scoring/release gate 决定；teaching context 的 controlled default 不等于 official answer key。

### 6.3 明确禁止

- 禁止 LLM 改 taxonomy。
- 禁止 LLM 把题库解析变成规范事实。
- 禁止把学生答案当 label authority。
- 禁止 rich artifact 直接写 learner truth。
- 禁止每个 surface 自己拼一套 context。
- 禁止原地改当前 `canonical_unified_knowledge.json`。
- 禁止未审核 candidate 被外部 pointer 指为 controlled default。

## 7. Compiler Pipeline

推荐流水线：

```text
source inventory
-> leaf source gatherer
-> LLM semantic structurer
-> deterministic field validator
-> evidence auditor
-> conflict resolver
-> rich artifact candidate
-> versioned runtime_supply candidate
-> slice A/B runtime consumption
-> release decision
```

### 7.1 Source Inventory

输入：

- textbook records
- standard clauses
- lecture cards
- question bank records
- case rubric records
- source alignment repairs
- student answer / residual samples

输出：

- per-leaf source candidate pool
- source coverage counts
- missing lanes
- source conflict flags

### 7.2 Leaf Source Gatherer

职责：

- 按 leaf_id/leaf_path/keywords/node_code 收集候选 source records。
- 应用 source alignment repairs 和 negative evidence。
- 区分 strong/weak/polluted/missing。

不做：

- 不生成最终概念。
- 不签发 truth。

### 7.3 LLM Semantic Structurer

职责：

- 从 source pool 生成 rich field candidates。
- 抽 concepts/definitions/rules/procedures/numeric/exam_patterns/mistakes。
- 对每个 field 绑定 source_ref 或标 candidate-only。

要求：

- 每个 field 必须给 `source_ref_ids` 或 `candidate_reason`。
- LLM 不允许 mint source_ref。
- LLM 不允许改 scoring rubric。

### 7.4 Deterministic Field Validator

职责：

- 验证 source path/record/span/hash。
- 验证 numeric constraints 的数值、单位、条件。
- 验证 mandatory/forbidden rule 是否来自高 authority source。
- 验证 rubric_link_index 是否引用真实 rubric/scoring point，且未复制评分规则。
- 验证 learner templates 不允许 canonical write。

### 7.5 Evidence Auditor

职责：

- 抽样/全量检查 field 是否真的被 source 支撑。
- 标记 generic path term pollution。
- 标记 source conflict。
- 标记 hallucinated field。
- 输出 per-field disposition：

```text
accepted
accepted_candidate_only
needs_review
rejected_pollution
rejected_unsupported
external_source_required
```

### 7.6 Runtime Supply Candidate

通过 schema/validator/auditor slice gate 后生成非默认候选 bundle，供 A/B 消费：

```text
deeptutor/services/construction_grading/runtime_supply/v_rich_leaf_artifacts_candidate_<date>/
```

注意：

- 不覆盖旧 `v_canonical_unified_knowledge`。
- 使用 manifest + content_hash + pointer。
- `candidate_status` 初始为 `candidate` 或 `reviewed_candidate`，artifact 本身不能写 `controlled_default`。
- A/B 必须读取这个 versioned candidate bundle；不得直接读取散落 workbench artifact。
- pointer 只写 candidate pointer，不切 system-wide default。

## 8. Runtime Consumption Design

RichLeafArtifact 必须进入 `CompiledContextPack`，否则只是离线报告。

### 8.1 CompiledContextPack 最小形状

```json
{
  "pack_id": "...",
  "task": "grading | tutoring | rag_answer | next_action | review",
  "leaf_artifacts": [],
  "question_context": {},
  "rubric_context": {},
  "learner_context": {},
  "source_context": {},
  "diagnostic_policy": {},
  "budget_policy": {},
  "consumption_trace": {
    "bundle_version": "...",
    "manifest_hash": "...",
    "consumed_field_ids": [],
    "stripped_candidate_field_ids": [],
    "rejected_field_ids": [],
    "fail_closed_reasons": [],
    "canonical_write_allowed": false,
    "production_write_count": 0
  },
  "personalization_level": "none | generic | evidence_backed | teacher_final_backed",
  "safety": {}
}
```

`retrieval_hints`、`runtime_profiles` 和 `budget_policy` 都是 pack builder 的裁剪输入或派生输出，不是 leaf truth：

- `retrieval_hints` 只影响召回排序/别名扩展，不得新增 facts。
- `runtime_profiles` 只表达任务包形态，如 `minimal_grading`、`tutoring_explain`、`next_action`，不得改变 field authority。
- `budget_policy` / `budget_profile` 由 pack builder 依据 token、latency、surface 和 risk 计算，不写回 RichLeafArtifact。
- 任何 surface 只能消费 `CompiledContextPack`，不能绕过 pack builder 直接读取 raw RichLeafArtifact。

### 8.1.1 Selection Policy

`CompiledContextPack` 是 thin runtime adapter，不能成为第二套知识库。它只按任务从 RichLeafArtifact 中裁剪上下文。

通用排序规则：

1. 先按 `task` 过滤字段：
   - `grading`: `rubric_link_index`, `rules`, `numeric_constraints`, `negative_evidence`, `source_refs`；实际评分 policy 必须回读 canonical scoring artifact
   - `tutoring`: `concepts`, `definitions`, `procedures`, `teaching_cards`, `source_refs`，如有本次 grading context，可附 `rubric_link_index` 和 observed mistake candidate，但不得重新评分
   - `rag_answer`: `definitions`, `rules`, `procedures`, `retrieval_hints`, `source_refs`
   - `next_action`: `exam_patterns`, `teaching_cards`, `common_mistakes`, `learner_memory_event_templates`
   - `review`: `audit`, `source_refs`, rejected/candidate fields
2. 再按 authority 排序：
   - `source_truth`
   - `assessment_evidence`
   - `teaching_evidence`
   - `learner_evidence`
   - `candidate_only`
3. 再按 negative evidence 约束：
   - 如果命中 `wrong_path` / `generic_path_term_only`，该 source candidate 不进入 positive context，只进入 warning。
   - 如果命中 `external_source_required`，pack 必须带 `needs_review_reason`，不得让 LLM positive certify。
4. 再按 token budget 裁剪：
   - required policy fields 优先于 teaching prose。
   - minimal source span 优先于长 chunk。
   - numeric/rule/procedure 优先于 example。
5. 去重：
   - 同一 `source_ref_id` 只出现一次。
   - 同一 `rule_id` 多 source 支撑时合并 source_refs。
   - conflicting rules 不合并，进入 `diagnostic_policy.conflict`.

降级策略：

| 情况 | Pack 行为 |
|---|---|
| 没有 release_candidate artifact | 使用 current RAG + diagnostic work order，不伪造 rich context |
| 只有 candidate_only 字段 | 可用于教学提示，但不得用于 official scoring |
| source_ref 校验失败 | 字段从 positive context 移入 rejected context |
| token budget 不足 | 保留 rules/numeric/negative_evidence，丢弃 teaching prose |
| learner context 不可用 | grading/tutoring 可继续；next_action 降级为 generic practice hint |

所有 pack 必须输出 `consumption_trace`。验收时不只看 pack 是否可构建，还要看 LLM prompt/judge 实际消费了哪些 `field_id`，哪些 candidate-only 字段被剔除，是否触发 fail-closed，以及 `canonical_write_allowed=false` 是否贯穿到底。

### 8.2 Surface 复用

| surface | 消费方式 |
|---|---|
| Runtime GradingPacket | 通过 `CompiledContextPack builder` 读取 rules/procedures/numeric/rubric_link_index/negative_evidence；评分 policy 回读 canonical scoring artifact |
| TutorBot | 只消费 `CompiledContextPack(task=tutoring)`；可解释本次错因，但不写 learner truth、不重新判分 |
| RAG | 只消费 `CompiledContextPack(task=rag_answer)`；rich artifact 作为 retrieval rerank / answer scaffold，不替代 raw source |
| Learning Brain | 只消费 grading result 产生的 `learning_evidence_candidate`；再由 canonical claim gate 决定，不直接读 raw artifact 写 truth |
| Mobile next action | 只消费 Learning Brain / ViewModel 输出；必须展示 `personalization_level` |
| Review queue | 只消费 `CompiledContextPack(task=review)` 和 auditor report |

## 9. 分阶段交付计划

### Phase 0: Schema and Authority Lock

目标：

- 固化 `RichLeafArtifact v0` schema。
- 固化 field-level authority。
- 固化 candidate/review/release 生命周期。
- 明确和现有 `canonical_unified_knowledge`、`LubanContextPack`、Learning Brain 的关系。

交付物：

- schema 文档
- JSON schema 或 Python dataclass
- authority matrix
- source lane registry
- field claim envelope
- lifecycle transition matrix
- source span hash policy
- deterministic sampler spec
- `CompiledContextPack` contract
- validator checklist
- negative examples

GO 条件：

- 能回答每个字段“谁唯一写、谁唯一读、谁能签发”。
- 能区分 source truth / teaching evidence / assessment evidence / learner evidence / candidate-only。
- 能证明不制造第二套 taxonomy、第二套 learner truth、第二套 rubric。

NO-GO：

- 任一字段无法确定 authority。
- common_mistakes 或 learner templates 有可能被误写为 canonical learner truth。
- LLM 可直接写 release字段。

### Phase 1: 50 Leaf Rich Slice

目标：

用 50 个代表 leaf 验证 schema 是否真的有用。

建议样本：

| 类别 | 数量 | 目的 |
|---|---:|---|
| textbook-strong | 10 | 测定义/流程/教学卡 |
| standard-strong | 10 | 测 mandatory rule/numeric constraints |
| lecture-strong | 10 | 测教学表达/迁移解释 |
| question-bank-strong | 10 | 测 exam patterns/grading relevance |
| weak/polluted/sparse | 10 | 测 negative evidence/source missing/fail-closed |

同时每个入选 leaf 必须尽量绑定至少一个 `task_pair`。如果没有可绑定任务，仍可用于 schema/source 验证，但不得进入 Phase 2 runtime A/B 分母。

```json
{
  "leaf_id": "...",
  "bucket": "textbook-strong",
  "task_pairs": [
    {
      "task_type": "grading | tutoring | rag_answer | next_action | review",
      "question_id": "...",
      "student_answer_id": "...",
      "scoring_artifact_id": "...",
      "learner_event_id": "...",
      "expected_outcome_authority": "official_key | shadow_gold | teacher_final | qa_review | diagnostic_only"
    }
  ]
}
```

新增 learner-centered mini-slice：

| learner slice | 数量 | 目的 |
|---|---:|---|
| QA/真实学生作答 + grading result | >= 10 task pairs | 验证诊断 evidence 能进入 event candidate |
| teacher-final / qa-review 样本 | >= 5 task pairs | 验证 observed mistake 与 claim gate |
| retest before/after 样本 | >= 5 task pairs | 验证 next action 是否能绑定复测成功条件 |
| mobile next-action 场景 | >= 5 task pairs | 验证 personalization_level 和行动可执行性 |

如果当前缺真实样本，该 learner-centered slice 标 `not_exercised`，Phase 2 不能宣称 Grading-to-Brain GO，只能宣称 rich source/teaching slice 结果。

#### Phase 1 Deterministic Sampler

50 leaf slice 必须可复现，不能后验挑选。sampler 输入：

- `canonical_taxonomy_index.content_hash`
- `canonical_unified_knowledge.content_hash`
- `source_alignment_repairs.content_hash`
- fixed seed: `rich_leaf_phase1_20260611`

候选集合定义：

| bucket | 入选条件 | 排序 |
|---|---|---|
| textbook-strong | `counts.textbook > 0` 且无 repair negative hit | `(-counts.textbook, leaf_id)` |
| standard-strong | `counts.standard > 0` 且含 mandatory/numeric 来源优先 | `(-counts.standard, leaf_id)` |
| lecture-strong | `counts.lecture > 0` 且 `counts.textbook=0 or teaching_card_gap=true` 优先 | `(-counts.lecture, leaf_id)` |
| question-bank-strong | `counts.question > 0` 且有 rubric/scoring/question refs | `(-counts.question, leaf_id)` |
| weak/polluted/sparse | 现有 `question_without_knowledge`、weak reanchor、source pollution work order、missing lanes | `(risk_rank, leaf_id)` |

抽样规则：

1. 每个 bucket 先按排序取前 30 作为 candidate pool。
2. 对 candidate pool 用 `sha256(seed + leaf_id)` 排序。
3. 每个 bucket 取前 10。
4. 如果 leaf 同时属于多个 bucket，只保留其最高风险 bucket；空位由该 bucket 下一个候选补齐。
5. 输出 `sample_manifest.json`，记录所有输入 hash、bucket rule、候选池、入选原因、排除原因。
6. 输出 `task_pair_manifest.json`，记录每个 leaf 是否绑定 grading/tutoring/rag/next_action/review task，以及 label/expected outcome authority。

这保证任何 agent 在同一输入 hash 下得到同一 50 leaf slice。

交付物：

- 50 个 rich leaf candidate artifacts
- per-field source refs
- validator report
- auditor report
- rejected fields report
- missing source work orders

GO 条件：

- field source validity >= 95%
- unsupported mandatory rules = 0
- unsupported numeric constraints = 0
- generic path pollution accepted = 0
- candidate-only 字段没有进入 release_candidate
- 50 leaf 中至少 35 个能生成可用 teaching card
- 至少 20 个能生成 exam pattern 或 grading relevance

NO-GO：

- LLM 生成大量无源字段。
- source_refs 只能证明同词，不能证明语义。
- weak leaf 被误收进 release_candidate。

### Phase 2: Runtime Consumption A/B

目标：

验证 rich context 是否让系统真的变强。

四臂：

| arm | 说明 |
|---|---|
| A current RAG + fixed judge | 当前基线，固定同一 judge/prompt/budget |
| B thin compiled context + fixed judge | 当前 snippets/counts 版，只替换 context |
| C rich compiled context + fixed judge | RichLeafArtifact 版，只替换 context |
| D rich compiled context + artifact-constrained LLM judge | 在 C 基础上单独测试 judge 变化 |

归因规则：

- A/B/C 固定同一 judge、同一 prompt family、同一 max token、同一 provider fallback 策略，只改变 context source。
- C/D 固定同一 rich context，只改变 judge/adjudication mode。
- 若 C 优于 B，才能说 rich artifact 有 context dividend。
- 若 D 优于 C，才能说 artifact-constrained LLM judge 有 judge dividend。
- 如果只有 D 赢，不能把收益归因给 rich artifact。

样本与 label authority：

- 每个 A/B 样本必须来自 `task_pair_manifest.json`。
- `expected_outcome_authority` 必须显式标为 `official_key | shadow_gold | teacher_final | qa_review | diagnostic_only`。
- `diagnostic_only` 样本不得进入 scoring MAE/accuracy 分母，只能用于 citation/explanation/fail-closed。
- AI-only shadow gold 只能给 directional 结论，不能写 release truth。

指标：

- scoring MAE / accuracy
- point precision/recall
- fail-open rate
- unsupported-positive rate
- evidence citation quality
- explanation usefulness
- common mistake correctness
- Learning Brain event usefulness
- token
- latency
- source pollution rate

GO 条件：

- rich compiled context 至少不差于 current RAG。
- 在 evidence quality、fail-open、explanation usefulness 上明显优于 thin context。
- rich + LLM judge 在高风险点上优于 deterministic-only。
- token/latency 不得恶化到不可接受；如果准确率明显提升，可接受小幅成本上升。

量化阈值：

| 指标 | 最低 GO 阈值 | 说明 |
|---|---:|---|
| `score_mae` | `rich <= current_rag` 且 `rich+judge <= legacy_or_thin + 5% relative` | 不能为了解释更好牺牲主评分 |
| `point_precision` | `>= thin_context` | 防止 rich context 引入过度命中 |
| `point_recall` | `>= current_rag` | 至少不比 RAG 漏更多 |
| `fail_open_rate` | `<= thin_context - 20% relative` 或绝对 `<= 2%` | rich 的核心价值之一是低误放 |
| `unsupported_positive_rate` | `0` | 无源 positive 直接 NO-GO |
| `citation_support_rate` | `>= 95%` | citation 必须能回到 source span |
| `wrong_path_citation_rate` | `0` on slice | 50 leaf slice 不容忍已知 wrong-path |
| `explanation_usefulness` | `>= 80%` auditor usable | auditor 判断是否能帮助学生理解错因 |
| `learning_event_usable_rate` | `>= 80%` for eligible grading cases | 不是所有 leaf 都必须生成 LB event，但 eligible 时要可用 |
| `token_delta` | `<= +25%` unless quality gate improves by `>=20% relative` | token 是约束，不是第一目标 |
| `latency_delta` | `<= +30%` unless high-risk fallback 明显下降 | 高质量允许小幅慢，但不能不可用 |

若 rich context 在 TutorBot/Teaching 指标显著提升，但 scoring 指标未达标，则只能进入 `teaching_context_candidate`，不能进入 scoring runtime default。

Grading-to-Brain GO 额外硬门：

```text
grading result
-> learning_evidence_candidate / learner_memory_event_candidate
-> QA/test learner readback
-> synthesis projection
-> mobile/PCP next action
-> retest target / delta condition
```

要求：

- 只允许 QA/test learner 或 hermetic fixture。
- `canonical_write_allowed=false`，除非另有独立授权。
- `production_write_count=0`。
- GBrain/Learning Brain 只消费评分诊断证据，不重新评分。
- 若该链路未跑，Phase 2 最多声明 `rich_context_runtime_shape_pass`，不得声明 Grading-to-Brain convergence。

NO-GO：

- rich context 让 LLM 更自信地错。
- citation 质量下降。
- Learning Brain event 变得更泛化。
- fail-open 上升。

### Phase 3: Full Candidate Compile

目标：

对 3158 leaves 做全量 candidate 编译，但仍不直接 controlled default。

交付物：

- full rich leaf candidate bundle
- coverage report
- field validity report
- source lane report
- missing source work orders
- pollution report
- token/size/capacity report
- regression A/B report

GO 条件：

- populated leaf rate 从当前 12.5% 提升到至少 35% 才可称 Phase 3 coverage GO；若低于 35% 只能称 partial candidate compile。
- high-priority exam leaves 覆盖率至少 80% source-backed 或 reviewed_candidate。
- source-backed field pass rate：high-risk fields 100%，overall >=95%。
- pollution accepted = 0；wrong_path accepted = 0。
- source-backed fields 和 candidate-only fields 严格分离。
- auditor 抽检通过。

NO-GO：

- 为追求覆盖率牺牲 source validity。
- 大量 leaf 只有泛路径命中。
- runtime packet builder 无法稳定消费。

### Phase 4: Governed Runtime Supply Candidate

目标：

把审核通过的 rich artifacts 编译成 versioned runtime supply candidate。

交付物：

```text
runtime_supply/v_rich_leaf_artifacts_candidate_<date>/
  rich_leaf_artifacts.jsonl
  manifest.json
  source_index.json
  validator_report.json
  pointer.json
```

GO 条件：

- manifest/hash/pointer 完整。
- 不覆盖旧 bundle。
- fail-closed 读路径可用。
- regression A/B 达标。

NO-GO：

- 任何 release truth 字段被手动翻 true。
- 无审核字段进入 controlled default。

## 10. 验证矩阵

| 验证 | 目的 | 阈值 |
|---|---|---|
| schema validation | 字段形状稳定 | 100% |
| source ref validation | source path/span/hash 可追溯 | 100% required fields |
| field support audit | 字段被 source 支撑 | high-risk fields 100%；low-risk aggregate >=95% |
| numeric validator | 数值/单位/条件正确 | 100% |
| rule authority validator | mandatory/forbidden 来源正确 | 100% |
| rubric link validator | 不复制 scoring policy，只引用 scoring artifact | 100% |
| pollution audit | 泛路径/错路径不被收 | accepted pollution = 0 |
| runtime pack smoke | 能被 pack builder 消费 | 100% slice |
| runtime consumption trace | LLM/judge 实际消费正确字段 | 100% sampled tasks have consumed_field_ids / stripped_candidate_field_ids |
| A/B quality | 证明效果 | rich >= RAG, key metrics better |
| Learning Brain dry-run | 只产 event candidate，不写 truth | canonical_write_allowed=false, production_write_count=0 |
| Learning Brain readback slice | QA/test learner 读回闭环 | required only for Grading-to-Brain GO; otherwise not_exercised |
| safety invariant | 不越权 | production_write=0, canonical_truth_written=false |

field support 分桶：

| 字段族 | 阈值 |
|---|---:|
| `source_refs` | 100% |
| `mandatory/forbidden rules` | 100% |
| `numeric_constraints` | 100% |
| `rubric_link_index` | 100% |
| `negative_evidence` | 100% for accepted blockers |
| `definitions/procedures` | >=95% |
| `teaching_cards/exam_patterns` | >=90%，且 unsupported factual claim = 0 |
| `observed_mistakes` | 100% require real grading/student/teacher evidence |
| `hypothesized_mistakes` | candidate-only, excluded from release truth |

## 11. 不确定性与验证方案

### 11.1 LLM 是否能稳定抽 rich fields

不确定。

验证方案：

- 50 leaf slice 用多模型 compiler workers。
- 同 leaf 用 2 个模型交叉生成，第三个模型做 prosecutor。
- deterministic validator 只收 source-backed fields。

替代方案：

- 如果 LLM 结构化质量不稳，先只做 `definitions/rules/numeric/source_refs` 四个高确定字段。

### 11.2 Common mistakes 是否有足够真实证据

不确定。

验证方案：

- `observed_mistakes` 只允许 `observed_from=student_answer/residual/teacher_review/teacher_final`，并且必须绑定真实 grading event 或 QA/teacher review artifact。
- `council_shadow`、`synthetic_candidate`、`ai_review_suggestion` 只能进入 `hypothesized_mistakes`，默认 candidate-only。
- 没有真实证据时只进 review queue，不进入 learner claim。

替代方案：

- Phase 1 先不 release common_mistakes，只产 review queue。

### 11.3 全量 3158 leaves 成本

不确定。

验证方案：

- Phase 1 统计每 leaf token、latency、审核成本。
- 外推 3158 leaves 的成本区间。

替代方案：

- 先编 high-priority 300 leaves，而不是一次性 3158。

### 11.4 Rich context 是否真的提升 runtime

不确定。

验证方案：

- 四臂 A/B 必须跑。
- 不以“schema 更漂亮”作为成功标准。

替代方案：

- 如果 rich artifact 对评分不显著提升，但对 TutorBot/Teaching 提升明显，则先作为 teaching_context default，不进入 scoring default。

### 11.5 Schema 是否过宽

有风险。

验证方案：

- Phase 1 每个字段统计 fill rate、audit pass rate、runtime consumed rate。

替代方案：

- 把低消费字段降级为 optional extension，不进核心 v0。

## 12. 推荐的最小可交付版本

为了稳健，不建议第一版就强行填满全部字段。建议 v0 core 分层：

### Core Required

- `leaf_id`
- `leaf_path`
- `authority`
- `source_refs`
- `definitions`
- `rules`
- `numeric_constraints`
- `negative_evidence`
- `audit`
- `safety`

### Core Optional

- `concepts`
- `procedures`
- `exam_patterns`
- `rubric_link_index`
- `teaching_cards`

### Candidate-only Extension

- `common_mistakes`
- `learner_memory_event_templates`
- `retrieval_hints`
- `runtime_profiles`

理由：

- 先保证 source-backed correctness。
- 再扩展 exam/teaching/grading。
- 最后接 Learning Brain，避免把 synthetic learner signal 误写 truth。

## 13. 当前最优执行顺序

建议用户审核通过后按以下顺序执行：

1. 写 `RichLeafArtifact v0` schema + validator tests。
2. 写 50 leaf sampler，覆盖五类 leaf。
3. 写 source gatherer，复用现有 compiled shards 和 repair overlay。
4. 写 LLM compiler prompt / offline mock contract，先不用 live 全量。
5. 写 deterministic validator。
6. 写 evidence auditor。
7. 生成 50 leaf candidate bundle。
8. 写 CompiledContextPack adapter。
9. 跑四臂小样 A/B。
10. 根据结果决定是否扩到 300 high-priority leaves 或全量 3158。

## 14. 审核问题

请先审核以下决策点：

1. 是否同意 `RichLeafArtifact` 是新 compiled context authority，但不是 source truth、learner truth、rubric truth？
2. 是否同意 v0 core 先收窄到 source-backed 字段，common_mistakes / learner templates 先 candidate-only？
3. 是否同意先做 50 leaf slice，而不是直接全量 3158？
4. 是否同意 A/B 必须验证 runtime 效果，不以离线 schema 完成作为 GO？
5. 是否同意通过审核的 rich artifacts 必须发新 runtime_supply version，禁止原地改当前 bundle？

## 15. 当前裁决

当前阶段裁决：

```text
Rich semantic compilation: REQUIRED
Current thin compiled context: INSUFFICIENT FOR NEXUS-LIKE CLAIM
Full release: NO-GO
Next action: approve plan -> implement Phase 0/1 slice
```

换句话说，之前表现不够突出，很可能是因为编译深度不够；现在应从补洞式 candidate patch 升级为 rich semantic artifact compiler。但必须继续保持单一权威和 release discipline，先用 50 leaf slice 证明它真的让 runtime 变强，再谈全量。
