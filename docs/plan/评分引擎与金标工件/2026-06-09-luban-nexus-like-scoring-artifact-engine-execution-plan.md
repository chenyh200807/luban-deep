# M35 Luban Nexus-like Scoring Artifact Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Luban's one-build-construction-practice case grading from ad-hoc rubric/prompt judgment into a versioned, traceable, evaluable scoring artifact engine that powers point-level grading, mistake diagnosis, learner evidence, and executable review plans.

**Architecture:** Reuse the existing canonical knowledge stack, KB/RAG substrate, `LubanContextPack`, `question_grading_artifacts.py`, `rubric_compiler.py`, `rubric_grader_v1.py`, `CaseGradingSkillKernel`, and Learning Brain evidence pipeline. Compiler workers produce candidate scoring artifacts; deterministic gates sign release candidates; runtime consumes only tracked runtime supply / canonical manifests; LLMs adjudicate student language against signed scoring points but do not mint answer keys, rewrite rubrics, or write canonical learner truth.

**Tech Stack:** Python 3.11 services, Pydantic/dataclass style typed payloads already used in `construction_grading`, JSONL/JSON runtime supply, Supabase/Postgres only after shadow gates, existing KB v5/RAG retrieval, existing `/api/v1/ws`, pytest, release-gate runner artifacts.

---

## 0. Why This Plan Exists

This plan supersedes the current vague interpretation of "Nexus-like" for Luban. The core product win is not a general chat RAG upgrade. The core win is:

```text
exam reference answer + textbook/spec/lecture/real-question evidence
  -> compiled scoring artifacts
  -> point-level student-answer adjudication
  -> stable mistake diagnosis
  -> learning evidence
  -> weakness profile
  -> review plan and retest
```

The attached research report is correct on the strategic point: Pinecone Nexus is useful to study because it moves work from retrieval time to compilation time and returns typed, provenance-backed knowledge. Luban should not bind the scoring core to Pinecone Nexus now. Luban should build a domain-owned Nexus-like scoring artifact layer on top of the codebase that already exists.

M34 tried to make general TutorBot knowledge answers benefit from compiled context. That remains useful, but the fresh shadow work showed a hard lesson: broad compiled teaching context can be low-recall, source-polluted, or weaker than RAG-only unless the compiler artifacts are typed, evaluated, and source-clean. M35 therefore returns to the highest-value, strongest-structure lane: case-question scoring artifacts.

### 0.1 Review Hardening Delta (2026-06-09)

This revision tightens the original M35 plan before implementation. The plan is still a POC/shadow execution plan, but four gates now become non-negotiable:

1. **Status semantics must be reconciled before runtime wiring.** Existing `question_grading_artifacts.py` v0 uses `published/draft/blocked`; M35 must not let that local v0 `published` word be confused with a production published registry or official score authority.
2. **The 20-question / 100-answer pack must prove label authority.** A file that only has `gold_point_matches` is not enough. Every answer needs `label_authority`, sample bucket, point-level label provenance, and a directionality flag.
3. **A/B must be three-tiered.** A hermetic judge stub proves shape only; cached/live judge replay proves scoring behavior. Quality claims may not be made from stub-only results.
4. **Learning Brain success means readback, not just payload shape.** M35 is not complete until point-level evidence can be read back into a weakness/read-model/review-plan projection while `canonical_truth_written=false`.

Known prior failure must stay visible: the earlier human validation slice reported `human-vs-artifact-first` point-hit agreement `0.5267` and mean absolute score delta `4.6091`. M35 exists to beat that failure mode, not to relabel it as success.

### 0.2 Nexus + GBrain Convergence Charter (2026-06-09)

M35 is the first scoring-artifact vertical slice. It is not the final product state by itself. The final Luban target is the convergence of:

```text
Nexus-like scoring artifact engine
  -> point-level grading evidence
  -> GBrain-inspired Learning Brain evidence ledger
  -> stable learner claims / typed graph / weakness projection
  -> PersonalizationContextPack + NextBestAction
  -> retest / improvement proof
  -> teacher or governed promotion
  -> compiler feedback and next artifact version
```

This means the system is only truly "Nexus-like + GBrain-like" when both sides are connected:

| Side | What it means for Luban | Must be proven |
|---|---|---|
| Nexus-like | compile source-backed scoring knowledge once, serve typed/cited artifacts many times | artifact version, source refs, release gate, typed query, A/B lift |
| GBrain-like | turn grading evidence into learner memory, claims, action, retest, and feedback loops | `learner_memory_events`, readback projection, `PersonalizationContextPack`, `NextBestAction`, retest delta |

M35 must therefore avoid two opposite failures:

1. stopping at a beautiful offline scoring artifact that never changes learner behavior;
2. writing point matches directly into learner truth without Learning Brain's evidence, claim, retest, and teacher/governed promotion gates.

The rule for later workers is:

```text
No Grading-to-Brain Loop claim unless the same attempt can be traced through:
artifact_version -> point_matches -> learning_evidence -> learner_memory_event
-> weakness/read-model projection -> next action -> retest condition/result.
```

M35 may stop at shadow/readback. M36/M37/M38 must carry the convergence forward without creating a second RAG, second learner memory, second WebSocket route, or standalone GBrain runtime.

## 1. Current Foundation

This is not from zero. The following files are already the right foundation:

| Existing file | Current role | M35 role |
|---|---|---|
| `deeptutor/services/construction_grading/question_grading_artifacts.py` | runtime-readable question artifact projection from 20 golden cases | Promote to the first POC artifact surface; harden version, source, and gate reporting |
| `deeptutor/services/construction_grading/rubric_compiler.py` | validates LLM-extracted scored rubrics and signs `case_rubric_scored` release candidates | Keep as deterministic compiler spine; extend provenance and negative evidence |
| `deeptutor/services/construction_grading/rubric_grader_v1.py` | point-level LLM-adjudicated grading with deterministic score sum and learning-evidence projection | Keep as the artifact-first runtime grader; connect to A/B and writeback gates |
| `deeptutor/services/construction_grading/case_kernel.py` | current case grading kernel and compatibility surface | Add shadow/controlled artifact-first path without regressing existing grading |
| `deeptutor/services/construction_grading/learning_evidence.py` | converts grading result into Learning Brain evidence payload | Carry artifact version, point matches, mistake taxonomy, and provenance |
| `deeptutor/services/construction_grading/writeback.py` | writes learning evidence and mistake-book entries | Keep write authority; only high-confidence / governed evidence may persist |
| `deeptutor/services/construction_grading/compiled_context.py` | `LubanContextPack` schema and context pack builder | Scoring artifacts become one source of rubric/source context, not a second pack schema |
| `deeptutor/services/construction_grading/canonical_resolution.py` | canonical path resolution | The only chapter/topic resolver; no new taxonomy |
| `deeptutor/services/construction_grading/canonical_knowledge_runtime.py` | canonical knowledge resolver | Source and teaching context resolver; no second RAG/registry |
| `tests/services/construction_grading/test_question_grading_artifacts.py` | 20-case artifact shape and source invariants | Expand into M35 artifact quality gate |
| `tests/services/construction_grading/test_rubric_grader_v1.py` | point-level grading behavior | Expand into A/B and Learning Brain evidence assertions |
| `tests/services/source_compiler/test_scoring_point_asset_compiler.py` | source compiler scoring-point tests | Reuse for compiler-source pollution fixes |

### 1.0 Implementation Assumptions, Boundary, and Verification Target

**Assumptions**

- M35 improves case-question scoring artifacts only. It does not change objective grading, general TutorBot knowledge answers, billing, BI, account state, or WeChat renderer behavior.
- Existing v0 artifact names and statuses may remain for backward compatibility, but M35 must introduce a runtime-facing status mapping so future workers cannot confuse v0 artifact `published` with production `published registry`.
- If the 100-answer pack is AI-generated or only single-reviewer directional, the gate may still run, but the verdict ceiling is `WEAK-GO / directional shadow` until a governed teacher or PO spot-check validates it.

**Simplest path**

Keep the work inside existing files and runners:

```text
question_grading_artifacts.py
  -> rubric_compiler.py
  -> rubric_grader_v1.py
  -> case_kernel/deep_question shadow attachment
  -> learning_evidence/writeback preview
  -> existing compiler_feedback candidate/work_order namespace
```

Do not add a generic knowledge platform, second rubric store, second learner memory, second RAG, second WebSocket route, or new product UI in the POC.

**Change boundary**

- Allowed: `deeptutor/services/construction_grading/*`, focused test fixtures, focused pytest files, M35 scripts, and this plan/INDEX entry.
- Not allowed without a separate authorization: production DB writes, remote/Aliyun writes, published registry, production broad default, canonical learner truth write, WeChat true-entry release claim, or a new frontend surface.

**Verification target**

M35 is only complete when all three are true:

1. artifact quality gates pass on the fixture;
2. A/B runner reports point precision/recall, score MAE, source validity, wrong-path, fail-open, token/latency, and prior-failure comparison;
3. `/api/v1/ws` shadow and Learning Brain readback prove append-only behavior with production writes `0` and canonical learner truth `false`.

### 1.1 Capability Inventory and Gap Matrix

This matrix is the execution inventory. If a later worker cannot point to a row here, the work is probably drifting into a second platform.

| Capability | Current status | Existing module / artifact | Gap | Completion path | Acceptance |
|---|---|---|---|---|---|
| Status semantics | Partially conflicting | `question_grading_artifacts.py` v0 uses `published/draft/blocked`; master plan uses `release_candidate/published` | Future workers can confuse v0 artifact `published` with production published registry | Task 0A maps v0 status to M35 runtime status and tests forbidden promotion | v0 `published` never grants production official-score authority; M35 POC emits `release_candidate/shadow_candidate/blocked` explicitly |
| Golden label authority | Missing as M35 fixture | prior PO/human validation artifacts exist under `artifacts/luban_human_validation_v1/` | No proof that 100 answers are governed labels rather than generated self-labels | Task 0B audits available label sources; Task 1 freezes fixture only after labeling level is explicit | every answer has `label_authority`, `label_scope`, bucket tags, and verdict ceiling derived from label quality |
| 20-case question artifact projection | Exists as v0 | `question_grading_artifacts.py`, `test_question_grading_artifacts.py` | Only 20 golden cases; gates do not yet expose full M35 score-sum/source-pollution/negative-evidence surface | Task 2 hardens gates; Task 1 freezes explicit M35 eval fixture | 20 artifacts build; each has schema/version/content_hash/scoring_points/source gates; missing case never auto-certifies |
| Scored rubric compiler | Exists as deterministic spine | `rubric_compiler.py`, `test_rubric_compiler.py` | Negative evidence and source-pollution work orders are not first-class enough | Task 3 preserves negative evidence; Task 7 routes pollution to compiler feedback | score sum gate passes; negative evidence survives normalization/signing; polluted source produces non-runtime work_order |
| Point-level grader | Exists as v1 spine | `rubric_grader_v1.py`, `test_rubric_grader_v1.py` | Not yet the measured M35 A/B default; point result shape needs release-gate metrics | Task 4 A/B runner; Task 5 shadow attachment | point_matches include hit/partial/miss, awarded_score, evidence_span, mistake_type; total score is deterministic sum |
| Legacy case grading compatibility | Exists | `case_kernel.py`, `CaseGradingSkillKernel` tests | Artifact-first path must not disturb existing grading | Task 5 append-only shadow block | legacy result remains available; artifact_missing falls back; no byte-regression outside controlled/shadow path |
| Learning evidence projection | Exists | `learning_evidence.py`, `writeback.py`, M32 tests | Artifact version and point-level match metadata can be dropped or flattened | Task 6 preserves M35 fields | Learning evidence carries artifact_version, point_id, hit/miss, evidence_span, mistake_code, source refs |
| Long-term learner truth | Exists as separate authority | Learning Brain claim lifecycle, `learner_memory_events` | M35 must not write canonical truth directly | Task 6 writeback gate and Task 8 safety gate | `canonical_truth_written=false`; point evidence is append-only/preview unless separate authorized gate promotes it |
| Source substrate | Exists | KB v5/RAG/source compiler refs | Source validity currently needs explicit M35 source-level audit | Task 4 metrics; Task 7 work orders; Task 9 decision package | source_validity >= 0.95 for POC GO; RAG chunk as answer key = 0 |
| Canonical path / taxonomy | Exists | `canonical_resolution.py`, `canonical_knowledge_runtime.py` | No new taxonomy allowed; wrong-path guard must be measured | Task 4 wrong_path metric; Task 7 reanchor/detach work orders | wrong_path_rate <= 0.03; query/path/source mismatch fails open and generates work_order |
| A/B evaluation | Missing | no M35 runner yet | No 20/100 Artifact-first vs baseline vs RAG-only gate; stub-only quality would overclaim | Task 1 fixture; Task 4 three-tier runner | report includes tier=shape/cached/live, point_precision, point_recall, score_mae, source_validity, wrong_path_rate, token_cost, fail_open_rate, prior-failure comparison |
| Live `/api/v1/ws` shadow | Missing for M35 | M32/M34 WS patterns exist | M35 not proven through real streaming entry | Task 8 integration test and gate runner | existing `/api/v1/ws` only; shadow block gated; safety all zero |
| Production decision package | Missing | M33 authorization package pattern exists | No M35-specific GO/WEAK-GO/NO-GO release decision | Task 9 decision package | explicit verdict with sample size, metrics, manual spot-check, rollback, stop conditions |
| Artifact ownership and lifecycle | Missing as explicit M35 gate | release package patterns exist, but no M35 RACI | Candidates can accumulate without a clear maintainer, reviewer, supersede rule, or rollback owner | Task 10 adds governance evaluator and lifecycle contract | every runtime-consumable artifact has owner_role, review_authority, lifecycle_status, supersede/rollback path, and no orphan release_candidate |
| Data lifecycle and 50k capacity | Missing as M35 artifact/evidence gate | deployment/capacity plans exist elsewhere | Workers may copy artifacts per user or keep unlimited trace payloads in the hot store | Task 11 capacity estimator and lifecycle contract | artifacts are global/versioned, attempts reference artifact_version, trace TTL/cold-store policy exists, synthetic 50k estimate identifies attempts/logs as the growth driver |
| Typed artifact query protocol | Missing as named M35 interface | `question_grading_artifacts.py`, `compiled_context.py` | Runtime can drift back to ad-hoc helper calls and prompt assembly | Task 12 adds a narrow KnowQL-inspired query surface | `retrieveRubric` returns shape/ground/confidence/budget fields; it never returns chunks as answer keys |
| Teacher review and compiler flywheel | Partial | `compiler_feedback.py`, teacher-final patterns | Low-confidence/override/source-conflict cases may die in logs instead of improving artifacts | Task 13 queues review outcomes into compiler feedback | teacher override produces candidate/work_order only; no direct release truth promotion |
| Grading-to-Brain closure gate | Partial | M32 Learning Brain loop and Task 6 readback | M35 may prove point evidence shape but not full action/retest loop | Task 14 adds end-to-end loop gate | same attempt traces artifact -> evidence -> memory event -> weakness -> next action -> retest condition with canonical truth still gated |
| Product-facing explanation | Not in POC | renderer/report surfaces exist elsewhere | UI must not be built before scoring artifact quality is proven | Post-M35 MVP only | point table can show score, miss reason, source/provenance, review action without leaking hidden answer key |

## 2. Product Outcomes

M35 must produce these product changes:

1. **Point-level grading:** every case answer can show which scoring points were hit, partially hit, missed, or contradicted.
2. **Stable mistake diagnosis:** lost points map to a controlled mistake taxonomy such as `omitted`, `wrong_subject`, `vague_expression`, `near_synonym_not_exact`, `list_incomplete`, `wrong_rule`.
3. **Traceable scoring:** every displayed point can carry `artifact_version`, `source_refs`, and student `evidence_span`.
4. **Learner evidence:** grading results become durable evidence events for Learning Brain without creating a second learner truth.
5. **Executable review plans:** repeated point misses aggregate into concrete review actions: chapter, scoring pattern, practice target, retest.
6. **Eval-driven compiler loop:** runtime misses and source pollution flow back into the compiler instead of being patched at prompt time.
7. **Nexus + GBrain bridge:** every high-confidence scoring result can become learner evidence, every learner weakness can point back to scoring artifacts, and every retest/improvement can feed compiler or review decisions.

## 3. Non-Goals

- Do not directly integrate Pinecone Nexus into the scoring core.
- Do not build a new generic Knowledge Engine platform.
- Do not create a second RAG, registry, taxonomy, learner memory, context schema, or WebSocket route.
- Do not create a standalone GBrain runtime or Obsidian-like notebook authority inside M35. User-visible notes and Learning Brain projections are consumers, not scoring truth.
- Do not let KB chunks, RAG answers, LLM votes, or generated candidates become official answer keys.
- Do not write production DB, published registry, canonical learner truth, or remote state in this plan.
- Do not flip system-wide default compiled context based on M35 POC. Default decisions require separate release gates.

## 4. Single Authority Contract

### 4.1 One Business Fact

The single business fact is:

> For a one-build-construction-practice case answer, every score, lost point, diagnosis, and review suggestion must be traceable to a versioned scoring artifact, a source-backed scoring point, and the student's answer evidence span.

### 4.2 Authority Table

| Fact | Sole authority | LLM role | Deterministic role |
|---|---|---|---|
| Canonical chapter/path | `canonical_resolution.to_canonical` | help interpret wording only | canonical id/path selection and fail-open |
| Source retrieval | KB v5 / existing RAG / source compiler refs | retrieve and summarize | provenance, hash, source-laundering guard |
| Scoring point artifact | `rubric_compiler.py` + release gate + runtime supply | propose candidate wording and acceptable expressions | validate score sum, policy, provenance, version, signature |
| Runtime point judgment | `rubric_grader_v1.grade_with_rubric` via injected judge | decide hit/partial/miss from student language | score sum, exact-required binary policy, high-risk routing |
| Legacy compatibility | `CaseGradingSkillKernel` | unchanged | existing behavior must remain byte-stable outside controlled path |
| Learning evidence | `learning_evidence.py` + `writeback.py` | synthesize explanation | append-only evidence; no canonical truth write |
| Long-term learner truth | Learning Brain claim lifecycle | candidate synthesis | teacher/governed gates, retest proof |
| Next action / retest | Learning Brain `PersonalizationContextPack` + `NextBestAction` + retest runner | propose explanation and wording | action selection must reference evidence; mastery promotion requires retest/teacher gate |
| Artifact lifecycle | M35 governance evaluator + release gate | propose maintenance work orders | owner/reviewer/status/supersede/rollback checks before runtime consumption |

### 4.3 Canonical Runtime Flow

```text
question_id
  -> retrieve published/release_candidate scoring artifact
  -> build LubanContextPack rubric/source block
  -> grade student answer point-by-point
  -> deterministic score sum
  -> point match result + mistake code + evidence span
  -> Learning Brain evidence preview/writeback gate
  -> weakness/read-model/review-plan projection
```

If the artifact is missing, low-confidence, source-invalid, or off-syllabus:

```text
fail-open to existing grading/RAG/open-world diagnostic
  -> label as unverified/formative
  -> generate compiler work_order
  -> do not contaminate prompt with wrong artifact context
```

### 4.4 Status Semantics Reconciliation

M35 must treat status words as contract-sensitive. Existing v0 code and future release governance use overlapping words with different authority. The implementation must freeze this mapping before runtime wiring:

| Source field | Allowed values | Meaning in M35 | Forbidden interpretation |
|---|---|---|---|
| `question_grading_artifacts.py` v0 `status` | `published`, `draft`, `blocked` | local artifact readiness inside the old v0 artifact surface | production published registry, official score, broad default |
| M35 runtime artifact `status` | `release_candidate`, `shadow_candidate`, `blocked` | POC/shadow consumability under explicit flag | canonical learner truth, production DB write, published registry |
| Production registry status | `release_candidate`, `published`, `superseded` | governed release lifecycle only after separate release gate | inferred from v0 artifact status or client request config |

Required implementation rule:

```text
v0 status may be copied into `legacy_artifact_status`.
M35 status must be computed separately.
`official_score_allowed` remains false unless a governed server-side release authority explicitly sets it.
Client-supplied status, request metadata, RAG chunks, or LLM candidates must never flip release truth.
```

### 4.5 Deterministic vs LLM Boundary

M35 should not replace LLM judgment with brittle rules, and it should not let LLMs mint truth. The boundary is:

| Work | LLM allowed? | Deterministic gate |
|---|---|---|
| interpret student wording against a signed point | yes | score sum, exact-required binary policy, low-confidence routing |
| propose rubric wording / acceptable expressions | yes | schema, score-sum, source, policy, attack tests |
| decide canonical chapter/path | only as helper | `canonical_resolution.to_canonical` and fail-open |
| create official answer key | no, unless governed source supplies it | answer-key laundering guard |
| promote learner mastery | no | Learning Brain claim lifecycle + governed retest/teacher gate |

### 4.6 Narrow KnowQL-Inspired Query Contract

M35 should learn from KnowQL's shape, not clone it. The first Luban query protocol is deliberately narrow:

```text
retrieveRubric(question_id, purpose, shape, citation_required, budget_tier)
```

Mapping:

| KnowQL primitive | Luban M35 equivalent | Boundary |
|---|---|---|
| `ask` | `purpose=grading/explanation/review_plan` | only case-question scoring artifacts in M35 |
| `where` | `question_id`, canonical path, runtime status, cohort flag | deterministic filters; no client-controlled release status |
| `ground` | `source_refs`, quote hashes, source validity | field-level citations required for score-bearing points |
| `shape` | rubric table, point matches, mistake taxonomy, review action | typed output; no raw chunk dumping |
| `confidence` | point confidence, source confidence, verdict ceiling | uncertain cases fail open or queue review |
| `budget` | context/token/latency tier | runtime must not re-run broad retrieval loops for every grading attempt |

The M35 runtime may call existing helpers underneath, but all caller-facing artifact retrieval should converge toward this contract before production default. If a future worker needs a different query shape, it must extend this narrow contract instead of adding a second retrieval interface.

### 4.7 Artifact Maintenance Responsibility Model

Artifacts are maintained by role, not by every engineer or every teacher manually editing JSON.

| Asset | Candidate writer | Reviewer / approver | Runtime authority | Maintenance trigger |
|---|---|---|---|---|
| Question scoring artifact | compiler worker / LLM candidate | teacher, PO, or governed reviewer | deterministic release gate + runtime supply | new source, failed eval, teacher override, source conflict |
| Scoring point | compiler worker | teacher/PO spot-check for high-risk points | signed artifact version | point residual, vague-answer overaccept, exact-term dispute |
| Common mistake taxonomy | scoring service + review queue | teaching/product owner | controlled mistake-code registry | repeated miss pattern, confusing feedback, new mistake class |
| Knowledge point edge | source compiler | source/provenance gate | canonical path resolver | wrong-path audit, chapter reanchor, textbook revision |
| Learner evidence | runtime grading/writeback gate | Learning Brain governs promotion | `learner_memory_events` ledger | every accepted grading attempt |
| Learner claim / mastery | Learning Brain claim lifecycle | teacher/governed promotion | stable learner truth | retest improvement, teacher final, decay/synthesis |

No human maintains all artifacts. Humans maintain the high-leverage decisions: disputed labels, high-frequency misses, source conflicts, rubric changes, and promotion policy. Everything else is candidate generation, deterministic validation, append-only evidence, and aggregate read models.

## 5. Artifact Shapes

M35 must converge the existing artifacts to this minimum runtime shape. Use existing modules where possible instead of creating new schema authorities.

```json
{
  "schema_version": "luban_case_scoring_artifact.v1",
  "artifact_version": "m35_case_scoring_202606xx",
  "question_id": "Q1-NA",
  "status": "release_candidate",
  "published": false,
  "total_score": 10.0,
  "stem_hash": "sha256:...",
  "source_inventory_hash": "sha256:...",
  "scoring_points": [
    {
      "point_id": "Q1-NA::P1",
      "criterion": "指出需要组织专家论证",
      "max_score": 2.0,
      "policy_type": "qualitative",
      "acceptable_expressions": ["专家论证", "组织专家论证"],
      "negative_evidence": ["仅写专项方案但未写专家论证"],
      "common_mistake_codes": ["E02", "E05"],
      "knowledge_point_refs": ["1A432000/..."],
      "source_refs": [
        {
          "source_type": "exam_reference_answer",
          "source_id": "2026_case_set_x",
          "quote_hash": "sha256:...",
          "verified": true
        }
      ],
      "source_status": "ok",
      "auto_certifiable": true
    }
  ],
  "quality_gates": {
    "score_sum_ok": true,
    "source_validity": 1.0,
    "negative_evidence_present": true,
    "source_pollution_count": 0
  }
}
```

Point-level grading result shape:

```json
{
  "schema_version": "luban_case_point_grading_result.v1",
  "question_id": "Q1-NA",
  "artifact_version": "m35_case_scoring_202606xx",
  "awarded_score": 6.0,
  "max_score": 10.0,
  "official_score_allowed": false,
  "point_matches": [
    {
      "point_id": "Q1-NA::P1",
      "status": "hit",
      "awarded_score": 2.0,
      "max_score": 2.0,
      "student_evidence_span": "需要组织专家论证",
      "mistake_code": "",
      "confidence": 0.92,
      "source_ref_ids": ["2026_case_set_x#p1"]
    },
    {
      "point_id": "Q1-NA::P2",
      "status": "miss",
      "awarded_score": 0.0,
      "max_score": 2.0,
      "student_evidence_span": "",
      "mistake_code": "E02",
      "confidence": 0.88,
      "source_ref_ids": ["2026_case_set_x#p2"]
    }
  ]
}
```

## 6. Required Evaluation Design

The POC is invalid without a 20-question / 100-answer golden set.

The fixture must declare one of these label levels:

| Label level | Allowed verdict ceiling | Requirements |
|---|---|---|
| `teacher_validated` | can support POC GO if metrics pass | teacher/PO labels, blinded to model outputs, point-level labels and score labels present |
| `po_directional_single_reviewer` | at most WEAK-GO unless spot-check passes | one reviewer labels all rows; report no inter-rater reliability |
| `ai_council_directional` | directional shadow only | at least two independent model/jury labels plus deterministic reconciliation |
| `generated_self_label` | shape gate only | cannot be used for precision/recall GO |

| Arm | Description | Required output |
|---|---|---|
| A baseline | Current `CaseGradingSkillKernel` / current runtime behavior | total score, rubric items, learning evidence payload |
| B RAG-only | Existing RAG evidence plus current grader/prompt | score, sources, token/latency |
| C artifact-first | M35 artifact + point-level adjudication | point matches, score, mistakes, sources, evidence |

Metrics:

| Metric | POC GO threshold |
|---|---:|
| scoring point recall | `>= 0.90` |
| scoring point precision | `>= 0.90` |
| score MAE vs human/golden | `<= 1.0` or `>= 20%` better than baseline |
| source validity | `>= 0.95` |
| hallucinated scoring points | `0` |
| RAG chunk used as answer key | `0` |
| wrong chapter/path rate | `<= 0.03` |
| answer-quality blind judge preference | artifact-first beats or ties baseline |
| token cost | report absolute and delta, no hidden regressions |
| fail-open correctness | low-confidence cases stay unpolluted |
| production writes | `0` |
| canonical learner truth writes | `false` |
| prior red failure comparison | artifact-first must beat the old `0.5267` point-hit agreement / `4.6091` MAE failure, or verdict stays NO-GO |

### 6.1 Three-Tier Evaluation Rule

Task 4 must report evaluation tier explicitly:

| Tier | What it proves | What it cannot prove |
|---|---|---|
| `shape_stub` | payload shape, deterministic score sum, no-write safety | scoring quality, semantic correctness, product readiness |
| `cached_judge_replay` | stable comparison on reviewed cached outputs | provider drift, latency/cost realism |
| `live_provider_sample` | real model behavior, latency/cost, fail-open under live judging | broad production readiness unless sample and labels are governed |

Any report generated only from `shape_stub` must set:

```json
{
  "quality_claim_allowed": false,
  "verdict_ceiling": "NO-GO_OR_SHAPE_ONLY"
}
```

## 7. Work Plan

### 7.0 Phase Goals

| Phase | Goal | Tasks | Exit criteria |
|---|---|---|---|
| Phase 0: Authority lock | Keep Nexus-like scope on scoring artifacts and prevent second platforms | This plan + INDEX entry + Task 0A | Plan names current modules, non-goals, authority table, status mapping, and stop conditions |
| Phase 0B: Label truth lock | Prove the eval pack can support the verdict being claimed | Task 0B | label sources audited; verdict ceiling derived before Task 1 fixture is frozen |
| Phase 1: Golden pack | Make evaluation real before runtime wiring | Task 1 | 20 real case questions and at least 100 answer samples with gold point matches |
| Phase 2: Artifact quality | Harden compiled scoring artifacts before they touch runtime | Task 2, Task 3 | artifacts expose score-sum/source/negative-evidence gates; compiler preserves negative evidence |
| Phase 3: Measurement | Prove artifact-first can beat or match baseline before product claims | Task 4 | A/B report covers baseline, RAG-only, artifact-first with required metrics |
| Phase 4: Runtime shadow | Attach artifact-first grading without changing official behavior | Task 5, Task 8 | `/api/v1/ws` shadow carries point_matches; legacy grading remains intact; safety zero |
| Phase 5: Learning loop | Make point matches usable by Learning Brain | Task 6 | evidence payload preserves artifact_version, point_id, mistake, source, evidence_span |
| Phase 6: Compiler feedback | Fix compiler outputs rather than prompt-patching runtime misses | Task 7 | source pollution and wrong-path cases generate detach/reanchor work orders |
| Phase 7: Release decision | Decide NO-GO / WEAK-GO / GO honestly | Task 9 | decision package lists sample size, metrics, manual spot-check, blockers, rollback |

### Task 0A: Reconcile M35 Status Semantics

**Files:**
- Create: `deeptutor/services/construction_grading/m35_status.py`
- Create: `tests/services/construction_grading/test_m35_status.py`

- [ ] **Step 1: Write RED tests for status mapping**

```python
from deeptutor.services.construction_grading.m35_status import (
    m35_runtime_status_from_v0,
    official_score_allowed_for_m35,
)


def test_v0_published_does_not_grant_m35_official_score():
    mapped = m35_runtime_status_from_v0({"status": "published", "version_id": "qga_v0_20260604"})
    assert mapped["legacy_artifact_status"] == "published"
    assert mapped["m35_runtime_status"] == "release_candidate"
    assert mapped["official_score_allowed"] is False
    assert mapped["published_registry_authority"] is False


def test_client_supplied_release_status_is_ignored():
    mapped = official_score_allowed_for_m35(
        server_governed_registry_status="",
        client_supplied_status="published",
        artifact_status="release_candidate",
    )
    assert mapped is False


def test_only_server_governed_published_registry_can_allow_official_score():
    mapped = official_score_allowed_for_m35(
        server_governed_registry_status="published",
        client_supplied_status="draft",
        artifact_status="release_candidate",
    )
    assert mapped is True
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/services/construction_grading/test_m35_status.py -q
```

Expected: FAIL because `m35_status.py` does not exist.

- [ ] **Step 3: Implement the minimal mapping module**

```python
from __future__ import annotations

from typing import Any


_V0_TO_M35 = {
    "published": "release_candidate",
    "draft": "shadow_candidate",
    "blocked": "blocked",
}


def m35_runtime_status_from_v0(artifact: dict[str, Any]) -> dict[str, Any]:
    legacy = str(artifact.get("status") or "").strip()
    return {
        "legacy_artifact_status": legacy,
        "m35_runtime_status": _V0_TO_M35.get(legacy, "blocked"),
        "official_score_allowed": False,
        "published_registry_authority": False,
    }


def official_score_allowed_for_m35(
    *,
    server_governed_registry_status: str,
    client_supplied_status: str,
    artifact_status: str,
) -> bool:
    _ = client_supplied_status, artifact_status
    return str(server_governed_registry_status or "").strip() == "published"
```

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/services/construction_grading/test_m35_status.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/construction_grading/m35_status.py \
        tests/services/construction_grading/test_m35_status.py
git commit -m "test: lock M35 status semantics"
```

### Task 0B: Audit M35 Label Authority Before Freezing Fixture

**Files:**
- Create: `scripts/audit_luban_m35_label_authority.py`
- Create: `tests/scripts/test_luban_m35_label_authority.py`

- [ ] **Step 1: Write RED test for label-audit output**

```python
import json
import subprocess
from pathlib import Path


def test_m35_label_authority_audit_derives_verdict_ceiling(tmp_path):
    fixture = tmp_path / "student_answers.jsonl"
    fixture.write_text(
        "\n".join([
            json.dumps({
                "answer_id": "A1",
                "question_id": "Q1-NA",
                "label_authority": "generated_self_label",
                "gold_point_matches": [{"point_id": "P1", "status": "hit"}],
                "sample_bucket": "hit",
            }, ensure_ascii=False)
        ]),
        encoding="utf-8",
    )
    out = tmp_path / "label_audit.json"
    subprocess.run(
        ["python", "scripts/audit_luban_m35_label_authority.py", "--answers", str(fixture), "--output", str(out)],
        check=True,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["answer_count"] == 1
    assert payload["verdict_ceiling"] == "SHAPE_ONLY"
    assert payload["quality_claim_allowed"] is False
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/scripts/test_luban_m35_label_authority.py -q
```

Expected: FAIL because the audit script does not exist.

- [ ] **Step 3: Implement the audit script**

```python
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


LEVELS = {
    "teacher_validated": ("POC_GO_ALLOWED", True),
    "po_directional_single_reviewer": ("WEAK_GO_MAX", True),
    "ai_council_directional": ("DIRECTIONAL_SHADOW", False),
    "generated_self_label": ("SHAPE_ONLY", False),
}


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def audit(path: Path) -> dict[str, Any]:
    rows = _rows(path)
    by_level = Counter(str(row.get("label_authority") or "missing") for row in rows)
    by_bucket = Counter(str(row.get("sample_bucket") or "missing") for row in rows)
    missing = [
        row.get("answer_id")
        for row in rows
        if not row.get("label_authority") or not row.get("gold_point_matches") or not row.get("sample_bucket")
    ]
    if missing:
        ceiling, quality = "NO_GO_LABEL_CONTRACT", False
    elif by_level.get("teacher_validated"):
        ceiling, quality = LEVELS["teacher_validated"]
    elif by_level.get("po_directional_single_reviewer"):
        ceiling, quality = LEVELS["po_directional_single_reviewer"]
    elif by_level.get("ai_council_directional"):
        ceiling, quality = LEVELS["ai_council_directional"]
    else:
        ceiling, quality = LEVELS["generated_self_label"]
    return {
        "answer_count": len(rows),
        "label_authority_counts": dict(by_level),
        "sample_bucket_counts": dict(by_bucket),
        "missing_contract_answer_ids": missing,
        "verdict_ceiling": ceiling,
        "quality_claim_allowed": quality,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--answers", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = audit(Path(args.answers))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/scripts/test_luban_m35_label_authority.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_luban_m35_label_authority.py \
        tests/scripts/test_luban_m35_label_authority.py
git commit -m "test: add M35 label authority audit"
```

### Task 1: Freeze M35 Golden Eval Pack

**Files:**
- Create: `tests/fixtures/luban_m35_case_scoring/manifest.json`
- Create: `tests/fixtures/luban_m35_case_scoring/student_answers.jsonl`
- Create: `tests/services/construction_grading/test_m35_eval_fixture_contract.py`

- [ ] **Step 1: Write the fixture contract test**

```python
import json
from pathlib import Path

ROOT = Path("tests/fixtures/luban_m35_case_scoring")

def test_m35_manifest_has_twenty_questions_and_hundred_answers():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    answers = [
        json.loads(line)
        for line in (ROOT / "student_answers.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(manifest["questions"]) == 20
    assert len(answers) >= 100
    assert {q["question_id"] for q in manifest["questions"]}
    assert all(a["question_id"] for a in answers)
    assert all("gold_point_matches" in a for a in answers)
    assert all(a.get("label_authority") in {
        "teacher_validated",
        "po_directional_single_reviewer",
        "ai_council_directional",
        "generated_self_label",
    } for a in answers)
    assert all(a.get("sample_bucket") in {
        "hit",
        "partial",
        "miss",
        "wrong_content",
        "near_synonym_not_exact",
        "list_incomplete",
        "calculation",
        "stem_fact",
        "external_source_required",
        "off_path",
    } for a in answers)
    assert all("label_scope" in a for a in answers)
```

- [ ] **Step 2: Run RED**

Run:

```bash
pytest tests/services/construction_grading/test_m35_eval_fixture_contract.py -q
```

Expected: FAIL because the fixture files do not exist.

- [ ] **Step 3: Add the fixture files**

`manifest.json` must contain 20 real case questions with `question_id`, `stem`, `total_score`, `source_refs`, and expected artifact lane. `student_answers.jsonl` must contain at least 100 answers with `answer_id`, `question_id`, `student_answer`, `gold_score`, `gold_point_matches`, `label_authority`, `label_scope`, and `sample_bucket`.

Minimum bucket coverage:

```text
hit >= 20
partial >= 10
miss >= 10
wrong_content >= 10
near_synonym_not_exact >= 5
list_incomplete >= 5
calculation >= 5
stem_fact >= 5
external_source_required >= 3
off_path >= 3
```

If the available rows do not meet the bucket target, the fixture may still be committed only when `manifest.json` declares:

```json
{
  "verdict_ceiling": "WEAK_GO_OR_BELOW",
  "known_label_gap": true
}
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
pytest tests/services/construction_grading/test_m35_eval_fixture_contract.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/luban_m35_case_scoring/manifest.json \
        tests/fixtures/luban_m35_case_scoring/student_answers.jsonl \
        tests/services/construction_grading/test_m35_eval_fixture_contract.py
git commit -m "test: add M35 case scoring golden eval fixture"
```

### Task 2: Harden Question Scoring Artifact Quality Gates

**Files:**
- Modify: `deeptutor/services/construction_grading/question_grading_artifacts.py`
- Test: `tests/services/construction_grading/test_question_grading_artifacts.py`

- [ ] **Step 1: Write RED tests for M35 gates**

Add tests asserting:

```python
def test_m35_artifact_reports_score_sum_source_and_negative_evidence_gates():
    art = qga.build_question_grading_artifact("Q1-NA")
    gates = art["quality_gates"]
    assert "score_sum_ok" in gates
    assert "source_refs_verified_rate" in gates
    assert "source_pollution_count" in gates
    assert "negative_evidence_present" in gates
    assert gates["source_pollution_count"] == 0

def test_m35_artifact_version_is_explicit_and_runtime_readable():
    art = qga.build_question_grading_artifact("Q1-NA")
    assert art["schema_version"].startswith("question_grading_artifact")
    assert art["version_id"]
    assert art["content_hash"]
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/services/construction_grading/test_question_grading_artifacts.py -q
```

Expected: FAIL on missing M35 gate fields.

- [ ] **Step 3: Implement minimal gate fields**

Extend `_quality_gates()` to include:

```python
"score_sum_ok": abs(sum(float(sp.get("max_score") or 0) for sp in scoring_points) - expected_total) <= 0.01,
"source_pollution_count": len([...]),
"negative_evidence_present": any(sp.get("negative_evidence") for sp in scoring_points),
```

If the current artifact does not yet carry `expected_total`, use the case's official total score from the golden fixture as the deterministic source; do not infer total score from LLM text.

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/services/construction_grading/test_question_grading_artifacts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/construction_grading/question_grading_artifacts.py \
        tests/services/construction_grading/test_question_grading_artifacts.py
git commit -m "feat: harden M35 question scoring artifact gates"
```

### Task 3: Add Compiled Rubric Negative Evidence

**Files:**
- Modify: `deeptutor/services/construction_grading/rubric_compiler.py`
- Test: `tests/services/construction_grading/test_rubric_compiler.py`

- [ ] **Step 1: Write RED tests**

```python
from deeptutor.services.construction_grading.rubric_compiler import validate_rubric

def test_validate_rubric_accepts_negative_evidence_list():
    rubric = {
        "qid": "QX",
        "total_score": 2,
        "scoring_points": [
            {
                "point_id": "P1",
                "text": "写明总时差不影响总工期",
                "score": 2,
                "policy": "qualitative",
                "required_terms": ["总时差"],
                "negative_evidence": ["水泥代号", "混凝土强度等级"],
            }
        ],
    }
    out = validate_rubric(rubric)
    assert out["ok"] is True
    assert out["normalized"]["scoring_points"][0]["negative_evidence"] == ["水泥代号", "混凝土强度等级"]
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/services/construction_grading/test_rubric_compiler.py::test_validate_rubric_accepts_negative_evidence_list -q
```

Expected: FAIL because `negative_evidence` is not preserved.

- [ ] **Step 3: Preserve negative evidence in normalized points**

In `validate_rubric()`, add:

```python
negative_evidence = [
    str(item).strip()
    for item in (p.get("negative_evidence") or [])
    if str(item).strip()
]
```

and include `"negative_evidence": negative_evidence` in each normalized point.

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/services/construction_grading/test_rubric_compiler.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/construction_grading/rubric_compiler.py \
        tests/services/construction_grading/test_rubric_compiler.py
git commit -m "feat: preserve negative evidence in compiled rubrics"
```

### Task 4: Add Artifact-First A/B Runner

**Files:**
- Create: `scripts/run_luban_m35_scoring_artifact_ab.py`
- Test: `tests/scripts/test_luban_m35_scoring_artifact_ab.py`

- [ ] **Step 1: Write RED test for three-tier runner output**

```python
import json
import subprocess
from pathlib import Path

def test_m35_ab_runner_writes_required_metrics(tmp_path):
    out = tmp_path / "m35_ab.json"
    subprocess.run(
        [
            "python",
            "scripts/run_luban_m35_scoring_artifact_ab.py",
            "--output",
            str(out),
            "--fixture-limit",
            "3",
            "--tier",
            "shape_stub",
        ],
        check=True,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["evaluation_tier"] == "shape_stub"
    assert payload["quality_claim_allowed"] is False
    assert payload["verdict_ceiling"] == "NO-GO_OR_SHAPE_ONLY"
    for key in [
        "compiled_hit_rate",
        "wrong_path_rate",
        "source_validity",
        "answer_improvement",
        "token_cost",
        "fail_open_rate",
        "point_precision",
        "point_recall",
        "score_mae",
    ]:
        assert key in payload["metrics"]
    assert payload["safety"]["production_write_count"] == 0
    assert payload["safety"]["canonical_truth_written"] is False


def test_m35_ab_runner_rejects_quality_claim_without_label_authority(tmp_path):
    out = tmp_path / "m35_ab.json"
    subprocess.run(
        [
            "python",
            "scripts/run_luban_m35_scoring_artifact_ab.py",
            "--output",
            str(out),
            "--fixture-limit",
            "3",
            "--tier",
            "cached_judge_replay",
        ],
        check=True,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "prior_failure_comparison" in payload
    assert "old_human_vs_artifact_first_point_hit_agreement" in payload["prior_failure_comparison"]
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/scripts/test_luban_m35_scoring_artifact_ab.py -q
```

Expected: FAIL because the runner does not exist.

- [ ] **Step 3: Implement hermetic runner**

Runner responsibilities:

```text
load M35 fixture
run baseline A using current kernel or recorded baseline adapter
run RAG-only B if an existing adapter or recorded trace exists; otherwise mark B as not_exercised
run artifact-first C using question_grading_artifacts + rubric_grader_v1
support --tier shape_stub / cached_judge_replay / live_provider_sample
compute point precision / recall / score_mae / source validity
compare against prior artifact-first red failure: point_hit_agreement=0.5267, mean_abs_score_delta=4.6091
write JSON report under requested --output
never write DB or remote state
```

Tier behavior:

```text
shape_stub:
  - deterministic stub allowed
  - quality_claim_allowed=false
  - verdict_ceiling=NO-GO_OR_SHAPE_ONLY

cached_judge_replay:
  - use recorded judge outputs or committed fixtures
  - quality_claim_allowed=true only if label audit allows it
  - report provider/model/cache provenance

live_provider_sample:
  - opt-in only; use a small fixture limit by default
  - report real latency, token, cost, provider, model, failure modes
  - never runs in CI by default
```

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/scripts/test_luban_m35_scoring_artifact_ab.py -q
python scripts/run_luban_m35_scoring_artifact_ab.py \
  --output artifacts/luban_grading_artifacts/m35_scoring_artifact_ab_local/report_shape.json \
  --fixture-limit 20 \
  --tier shape_stub
```

Expected: PASS and report exists. The shape report may not claim scoring quality.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_luban_m35_scoring_artifact_ab.py \
        tests/scripts/test_luban_m35_scoring_artifact_ab.py
git commit -m "feat: add M35 scoring artifact A/B runner"
```

### Task 5: Connect Artifact-First Grading in Shadow Mode

**Files:**
- Modify: `deeptutor/services/construction_grading/case_kernel.py`
- Modify: `deeptutor/services/construction_grading/rubric_grader_v1.py`
- Test: `tests/services/construction_grading/test_case_grading_kernel.py`
- Test: `tests/services/construction_grading/test_rubric_grader_v1.py`

- [ ] **Step 1: Write RED tests**

Assertions:

```text
artifact shadow path emits point_matches
legacy output remains available
artifact missing falls back to legacy path
official_score_allowed remains false unless governed release truth exists
```

Minimal test shape:

```python
def test_case_kernel_shadow_artifact_path_keeps_legacy_score_and_adds_point_matches():
    result = grade_case_with_fixture_config("Q1-NA", "需要组织专家论证，并进行安全技术交底。", artifact_shadow=True)
    assert result["construction_grading_result"]["score_awarded"] is not None
    assert result["luban_m35_artifact_shadow"]["point_matches"]
    assert result["luban_m35_artifact_shadow"]["official_score_allowed"] is False
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/services/construction_grading/test_case_grading_kernel.py tests/services/construction_grading/test_rubric_grader_v1.py -q
```

Expected: FAIL until the shadow adapter exists.

- [ ] **Step 3: Implement append-only shadow attachment**

The case kernel must not replace legacy grading by default. It may attach:

```python
result.extra["luban_m35_artifact_shadow"] = {
    "artifact_version": artifact["version_id"],
    "legacy_artifact_status": artifact["status"],
    "m35_runtime_status": status_map["m35_runtime_status"],
    "point_matches": event["scoring_points"],
    "official_score_allowed": status_map["official_score_allowed"],
    "source_validity": artifact["quality_gates"]["source_refs_verified_rate"],
}
```

Use `m35_status.m35_runtime_status_from_v0()` plus the existing `rubric_grader_v1.grade_with_rubric()` spine and injected judge function. Do not add a new WebSocket route or a second RAG lookup.

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/services/construction_grading/test_case_grading_kernel.py tests/services/construction_grading/test_rubric_grader_v1.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/construction_grading/case_kernel.py \
        deeptutor/services/construction_grading/rubric_grader_v1.py \
        tests/services/construction_grading/test_case_grading_kernel.py \
        tests/services/construction_grading/test_rubric_grader_v1.py
git commit -m "feat: attach M35 artifact-first grading shadow"
```

### Task 6: Project Point Matches into Learning Evidence

**Files:**
- Modify: `deeptutor/services/construction_grading/learning_evidence.py`
- Modify: `deeptutor/services/construction_grading/writeback.py`
- Test: `tests/services/construction_grading/test_learning_evidence.py`
- Test: `tests/services/construction_grading/test_audit_and_writeback.py`
- Create: `tests/services/learner_state/test_m35_learning_evidence_readback.py`

- [ ] **Step 1: Write RED tests**

```python
def test_learning_evidence_carries_m35_artifact_version_and_point_matches():
    payload = build_learning_evidence_payload({
        "type": "case",
        "question_id": "Q1-NA",
        "score_awarded": 6,
        "max_score": 10,
        "rubric": {
            "artifact_version": "m35_case_scoring_202606xx",
            "scoring_point_hits": [
                {"point_id": "Q1-NA::P1", "hit": True, "awarded_score": 2, "evidence_span": "专家论证"},
                {"point_id": "Q1-NA::P2", "hit": False, "awarded_score": 0, "error_code": "E02"},
            ],
        },
    })
    assert payload["rubric"]["artifact_version"] == "m35_case_scoring_202606xx"
    assert payload["rubric"]["scoring_point_hits"][0]["point_id"] == "Q1-NA::P1"
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/services/construction_grading/test_learning_evidence.py tests/services/construction_grading/test_audit_and_writeback.py -q
```

Expected: FAIL if artifact metadata is dropped.

- [ ] **Step 3: Preserve metadata**

`learning_evidence.py` must preserve:

```text
artifact_version
point_id
hit / partial / miss
awarded_score
evidence_span
error_code / mistake_type
source_ref ids
high_risk_review
```

`writeback.py` must keep existing write gates. M35 evidence does not write canonical learner truth.

- [ ] **Step 3B: Add Learning Brain readback proof**

The readback test must prove the point-level evidence is not only serialized but usable:

```python
import json


def test_m35_point_evidence_reads_back_as_weakness_projection(fake_learner_state_service):
    payload = build_learning_evidence_payload({
        "type": "case",
        "question_id": "Q1-NA",
        "score_awarded": 6,
        "max_score": 10,
        "rubric": {
            "artifact_version": "m35_case_scoring_202606xx",
            "rubric_mode": "curated_rubric",
            "scoring_point_hits": [
                {
                    "point_id": "Q1-NA::P2",
                    "hit": False,
                    "awarded_score": 0,
                    "error_code": "E02",
                    "mistake_type": "omitted",
                    "evidence_span": "",
                    "source_ref_ids": ["2026_case_set_x#p2"],
                }
            ],
        },
    })
    fake_learner_state_service.append_memory_event(
        user_id="qa_m35",
        memory_kind="learning_evidence",
        payload_json=payload,
        dedupe_key="m35-q1-p2",
    )
    projection = fake_learner_state_service.synthesize_learning_truth(user_id="qa_m35")
    assert projection["canonical_truth_written"] is False
    assert "Q1-NA::P2" in json.dumps(projection, ensure_ascii=False)
    assert "omitted" in json.dumps(projection, ensure_ascii=False)
```

If the existing fake service does not expose `synthesize_learning_truth`, use the existing Learning Brain read-model helper already used by M32 tests; do not create a second learner-memory projection.

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/services/construction_grading/test_learning_evidence.py tests/services/construction_grading/test_audit_and_writeback.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/construction_grading/learning_evidence.py \
        deeptutor/services/construction_grading/writeback.py \
        tests/services/construction_grading/test_learning_evidence.py \
        tests/services/construction_grading/test_audit_and_writeback.py \
        tests/services/learner_state/test_m35_learning_evidence_readback.py
git commit -m "feat: preserve M35 point matches in learning evidence"
```

### Task 7: Add Compiler Feedback for Source Pollution

**Files:**
- Modify: `deeptutor/services/construction_grading/compiler_feedback.py`
- Modify: `deeptutor/services/construction_grading/rubric_compiler.py`
- Test: `tests/services/construction_grading/test_compiler_feedback.py`

- [ ] **Step 1: Write RED tests**

```python
def test_source_pollution_generates_reanchor_work_order():
    work_order = cf.work_order_from_source_path_conflict(
        question_id="Q-schedule-total-float",
        failed_path="cement_code",
        reason="query_path_source_mismatch",
        evidence={"query": "总时差怎么计算", "source_text": "水泥代号 P.O 42.5"},
    )
    assert work_order["namespace"] == cf.NAMESPACE
    assert work_order["kind"] == cf.KIND_WORK_ORDER
    assert work_order["reason"] == "query_path_source_mismatch"
    assert work_order["promote_to_release"] is False
    assert work_order["is_release_truth"] is False
    assert work_order["payload"]["work_order_type"] == "scoring_artifact_reanchor"
    assert work_order["payload"]["runtime_usable_as_truth"] is False
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/services/construction_grading/test_compiler_feedback.py -q
```

Expected: FAIL until the existing compiler-feedback module exposes the source/path conflict helper.

- [ ] **Step 3: Implement work-order generation**

Rules:

Extend `compiler_feedback.py`; do not create a parallel work-order module.

```python
def work_order_from_source_path_conflict(
    *,
    question_id: str,
    failed_path: str,
    reason: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return make_candidate(
        kind=KIND_WORK_ORDER,
        origin="m35_scoring_artifact_gate",
        payload={
            "work_order_type": "scoring_artifact_reanchor",
            "question_id": question_id,
            "failed_path": failed_path,
            "evidence": evidence,
            "runtime_usable_as_truth": False,
        },
        reason=reason,
    )
```

Rules:

```text
query/path/source mismatch -> scoring_artifact_reanchor work_order
source text supports sibling node only -> scoring_artifact_detach work_order
low confidence but plausible -> scoring_artifact_needs_review work_order
runtime_usable_as_truth always false
promote_to_release always false
namespace stays luban_compiler_candidate
```

- [ ] **Step 4: Run GREEN**

```bash
pytest tests/services/construction_grading/test_compiler_feedback.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/construction_grading/compiler_feedback.py \
        deeptutor/services/construction_grading/rubric_compiler.py \
        tests/services/construction_grading/test_compiler_feedback.py
git commit -m "feat: route M35 source pollution into compiler feedback"
```

### Task 8: Live `/api/v1/ws` Shadow Drill

**Files:**
- Modify: `deeptutor/capabilities/deep_question.py` only if the existing case-grading path needs an append-only metadata hook
- Modify: `deeptutor/services/session/turn_runtime.py` only if `grading_engine_m35_artifact_shadow` must be added to the existing runtime-only allowlist
- Create: `tests/integration/test_luban_m35_scoring_artifact_ws_shadow.py`
- Create: `scripts/run_luban_m35_scoring_artifact_release_gate.py`

- [ ] **Step 1: Write RED integration test**

Use the same real `/api/v1/ws` pattern as existing Luban WS tests: TestClient, TurnRuntime, fake external provider, no new route.

Assertions:

```text
flag name is grading_engine_m35_artifact_shadow
env kill switch is LUBAN_M35_ARTIFACT_SHADOW_ENABLED=false
case grading turn returns legacy grading result
shadow artifact block appears only when enabled
non-qa/non-operator users do not receive the block unless explicitly authorized
artifact block contains point_matches and artifact_version
artifact block contains legacy_artifact_status and m35_runtime_status
official_score_allowed=false
production_write_count=0
canonical_truth_written=false
```

- [ ] **Step 2: Run RED**

```bash
pytest tests/integration/test_luban_m35_scoring_artifact_ws_shadow.py -q
```

Expected: FAIL until shadow config and release gate exist.

- [ ] **Step 3: Implement release gate runner**

Runner must output:

```json
{
  "verdict": "GO|NO-GO",
  "evaluation_tier": "shape_stub|cached_judge_replay|live_provider_sample",
  "quality_claim_allowed": false,
  "verdict_ceiling": "NO-GO_OR_SHAPE_ONLY",
  "metrics": {
    "point_precision": 0.0,
    "point_recall": 0.0,
    "score_mae": 0.0,
    "source_validity": 0.0,
    "wrong_path_rate": 0.0,
    "fail_open_rate": 0.0
  },
  "safety": {
    "production_write_count": 0,
    "canonical_truth_written": false,
    "rag_chunk_as_answer_key": 0,
    "candidate_used_as_release_truth": 0,
    "client_status_promoted_to_release_truth": 0,
    "shadow_changed_legacy_result": 0
  }
}
```

Hooking rule:

```text
Prefer the existing deep_question case-grading metadata attachment pattern.
The wrapper may only read flag/env/cohort and append a block.
All point judgment stays in rubric_grader_v1 / artifact services.
The wrapper must not inspect student answer semantics beyond routing to the existing case grading path.
```

- [ ] **Step 4: Run GREEN and gate**

```bash
pytest tests/integration/test_luban_m35_scoring_artifact_ws_shadow.py -q
python scripts/run_luban_m35_scoring_artifact_release_gate.py --fixture tests/fixtures/luban_m35_case_scoring --output artifacts/luban_grading_artifacts/m35_scoring_artifact_gate/go_no_go_m35.json
```

Expected: tests PASS; gate may honestly return NO-GO until thresholds are met.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_luban_m35_scoring_artifact_ws_shadow.py \
        scripts/run_luban_m35_scoring_artifact_release_gate.py
git commit -m "feat: add M35 scoring artifact WS shadow gate"
```

### Task 9: Production Default Decision Package

**Files:**
- Create: `docs/plan/2026-06-xx-luban-m35-scoring-artifact-production-decision.md`

- [ ] **Step 1: Generate decision package from gate artifacts**

The decision package must list:

```text
20/100 or 100/500 sample size
label_authority distribution and verdict ceiling
evaluation_tier distribution: shape_stub / cached_judge_replay / live_provider_sample
baseline vs artifact-first point precision/recall
source validity audit
wrong path audit
fail-open audit
blind answer quality judge
teacher/manual spot-check result
token and latency deltas
prior red failure comparison against 0.5267 point-hit agreement / 4.6091 score MAE
Learning Brain readback proof: point weakness -> projection -> review action, canonical_truth_written=false
safety invariants
remaining blockers
recommended rollout cohort
rollback switch
```

- [ ] **Step 2: Explicitly choose one verdict**

Allowed verdicts:

```text
NO-GO: keep shape/cached shadow only; no user-facing quality claim
WEAK-GO: QA/operator cohort only, no real-student default, manual review required
GO: controlled cohort default for case grading only, still no published registry/canonical truth unless separately authorized
```

- [ ] **Step 3: Keep stop conditions**

Do not flip:

```text
published registry
canonical learner truth write
production broad default
remote/Aliyun deployment
```

without a separate explicit user authorization and release runbook.

### Task 10: Add Artifact Ownership and Lifecycle Governance

**Files:**
- Create: `deeptutor/services/construction_grading/m35_artifact_governance.py`
- Create: `tests/services/construction_grading/test_m35_artifact_governance.py`
- Create: `docs/plan/2026-06-09-luban-m35-artifact-ownership-and-data-lifecycle-contract.md`

- [ ] **Step 1: Write governance tests**

```python
from deeptutor.services.construction_grading.m35_artifact_governance import (
    evaluate_m35_artifact_governance,
)


def test_release_candidate_requires_owner_and_review_authority():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "lifecycle_status": "release_candidate",
        "source_refs": [{"verified": True}],
        "quality_gates": {"score_sum_ok": True, "source_validity": 1.0},
    }

    report = evaluate_m35_artifact_governance(artifact)

    assert report["runtime_consumable"] is False
    assert report["blocking_reasons"] == [
        "missing_owner_role",
        "missing_review_authority",
        "missing_supersede_policy",
        "missing_rollback_policy",
    ]


def test_shadow_candidate_with_owner_and_review_path_is_consumable_for_shadow_only():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "shadow_candidate",
        "lifecycle_status": "shadow_candidate",
        "owner_role": "construction_grading_artifact_owner",
        "review_authority": "po_directional_single_reviewer",
        "supersede_policy": "supersede_by_artifact_version",
        "rollback_policy": "disable_m35_artifact_shadow_flag",
        "source_refs": [{"verified": True}],
        "quality_gates": {"score_sum_ok": True, "source_validity": 1.0},
    }

    report = evaluate_m35_artifact_governance(artifact)

    assert report["runtime_consumable"] is True
    assert report["official_score_allowed"] is False
    assert report["blocking_reasons"] == []


def test_controlled_default_lifecycle_is_valid_but_does_not_grant_official_score():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "lifecycle_status": "controlled_default",
        "owner_role": "construction_grading_artifact_owner",
        "review_authority": "teacher_validated",
        "supersede_policy": "supersede_by_artifact_version",
        "rollback_policy": "disable_m35_artifact_shadow_flag",
        "source_refs": [{"verified": True}],
        "quality_gates": {"score_sum_ok": True, "source_validity": 1.0},
    }

    report = evaluate_m35_artifact_governance(artifact)

    assert report["runtime_consumable"] is True
    assert report["official_score_allowed"] is False
    assert "invalid_lifecycle_status" not in report["blocking_reasons"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/services/construction_grading/test_m35_artifact_governance.py -q
```

Expected: FAIL because `m35_artifact_governance.py` does not exist.

- [ ] **Step 3: Implement governance evaluator**

```python
from __future__ import annotations

from typing import Any


REQUIRED_RUNTIME_FIELDS = (
    "owner_role",
    "review_authority",
    "supersede_policy",
)


def evaluate_m35_artifact_governance(artifact: dict[str, Any]) -> dict[str, Any]:
    status = str(artifact.get("status") or "")
    lifecycle_status = str(artifact.get("lifecycle_status") or status)
    blocking_reasons: list[str] = []

    for field in REQUIRED_RUNTIME_FIELDS:
        if not artifact.get(field):
            blocking_reasons.append(f"missing_{field}")

    if status not in {"release_candidate", "shadow_candidate", "blocked"}:
        blocking_reasons.append("invalid_m35_status")

    if lifecycle_status not in {"candidate", "reviewed", "shadow_candidate", "release_candidate", "controlled_default", "superseded", "blocked"}:
        blocking_reasons.append("invalid_lifecycle_status")

    if not artifact.get("rollback_policy"):
        blocking_reasons.append("missing_rollback_policy")

    quality_gates = artifact.get("quality_gates") or {}
    if quality_gates.get("score_sum_ok") is not True:
        blocking_reasons.append("score_sum_not_verified")

    if float(quality_gates.get("source_validity") or 0.0) < 0.95:
        blocking_reasons.append("source_validity_below_gate")

    runtime_consumable = not blocking_reasons and status in {"release_candidate", "shadow_candidate"}

    return {
        "runtime_consumable": runtime_consumable,
        "official_score_allowed": False,
        "lifecycle_status": lifecycle_status,
        "blocking_reasons": blocking_reasons,
    }
```

- [ ] **Step 4: Write the lifecycle contract doc**

The contract doc must contain this exact lifecycle:

```text
candidate -> reviewed -> shadow_candidate -> release_candidate -> controlled_default -> superseded
```

It must also state:

```text
No artifact may be runtime-consumable without owner_role, review_authority,
supersede_policy, rollback_policy, artifact_version, source_refs, and quality_gates.
Teachers maintain disputed and high-impact decisions; compiler workers maintain
candidates; deterministic gates maintain release eligibility.
```

- [ ] **Step 5: Run tests**

Run:

```bash
pytest tests/services/construction_grading/test_m35_artifact_governance.py -q
```

Expected: PASS.

### Task 11: Add Data Lifecycle and 50k Capacity Gate

**Files:**
- Create: `scripts/estimate_luban_m35_artifact_capacity.py`
- Create: `tests/scripts/test_luban_m35_artifact_capacity.py`
- Modify: `docs/plan/2026-06-09-luban-m35-artifact-ownership-and-data-lifecycle-contract.md`

- [ ] **Step 1: Write capacity estimator tests**

```python
from scripts.estimate_luban_m35_artifact_capacity import (
    estimate_m35_capacity,
    estimate_m35_capacity_scenarios,
)


def test_50k_capacity_identifies_attempt_events_not_artifacts_as_growth_driver():
    estimate = estimate_m35_capacity(
        member_count=50_000,
        active_rate=0.20,
        attempts_per_active_member_per_month=10,
        avg_points_per_attempt=8,
        evidence_bytes_per_point=360,
        prompt_trace_bytes_per_attempt=12_000,
        global_artifact_count=500,
        avg_artifact_bytes=14_000,
    )

    assert estimate["monthly_attempts"] == 100_000
    assert estimate["global_artifact_storage_mb"] < 10
    assert estimate["primary_growth_driver"] == "attempt_evidence_and_trace_not_global_artifacts"
    assert estimate["per_user_artifact_copy_allowed"] is False
    assert estimate["requires_partitioning"] is True
    assert estimate["trace_retention_policy"] == "ttl_or_cold_storage"


def test_50k_capacity_matrix_covers_100k_1m_and_3m_attempts():
    report = estimate_m35_capacity_scenarios()

    assert set(report["scenario_results"]) == {"standard_100k", "heavy_1m", "peak_3m"}
    assert report["scenario_results"]["standard_100k"]["monthly_attempts"] == 100_000
    assert report["scenario_results"]["heavy_1m"]["monthly_attempts"] == 1_000_000
    assert report["scenario_results"]["peak_3m"]["monthly_attempts"] == 3_000_000
    assert report["max_monthly_attempts"] == 3_000_000
    assert report["per_user_artifact_copy_allowed"] is False
    assert report["readiness_claim"] == "estimate_only_not_load_test"
    assert report["next_required_gate"] == "load_test_hot_read_models_and_storage"
```

- [ ] **Step 2: Implement estimator**

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path


SCENARIO_PRESETS = {
    "standard_100k": {
        "member_count": 50_000,
        "active_rate": 0.20,
        "attempts_per_active_member_per_month": 10,
    },
    "heavy_1m": {
        "member_count": 50_000,
        "active_rate": 0.50,
        "attempts_per_active_member_per_month": 40,
    },
    "peak_3m": {
        "member_count": 50_000,
        "active_rate": 0.75,
        "attempts_per_active_member_per_month": 80,
    },
}


def estimate_m35_capacity(
    *,
    member_count: int,
    active_rate: float,
    attempts_per_active_member_per_month: int,
    avg_points_per_attempt: int,
    evidence_bytes_per_point: int,
    prompt_trace_bytes_per_attempt: int,
    global_artifact_count: int,
    avg_artifact_bytes: int,
) -> dict[str, object]:
    active_members = int(member_count * active_rate)
    monthly_attempts = active_members * attempts_per_active_member_per_month
    monthly_evidence_bytes = monthly_attempts * avg_points_per_attempt * evidence_bytes_per_point
    monthly_trace_bytes = monthly_attempts * prompt_trace_bytes_per_attempt
    global_artifact_bytes = global_artifact_count * avg_artifact_bytes

    return {
        "active_members": active_members,
        "monthly_attempts": monthly_attempts,
        "monthly_evidence_storage_mb": round(monthly_evidence_bytes / 1024 / 1024, 2),
        "monthly_trace_storage_mb": round(monthly_trace_bytes / 1024 / 1024, 2),
        "global_artifact_storage_mb": round(global_artifact_bytes / 1024 / 1024, 2),
        "primary_growth_driver": "attempt_evidence_and_trace_not_global_artifacts",
        "per_user_artifact_copy_allowed": False,
        "requires_partitioning": monthly_attempts >= 100_000,
        "trace_retention_policy": "ttl_or_cold_storage",
    }


def estimate_m35_capacity_scenarios() -> dict[str, object]:
    scenario_results = {}
    for name, preset in SCENARIO_PRESETS.items():
        scenario_results[name] = estimate_m35_capacity(
            member_count=preset["member_count"],
            active_rate=preset["active_rate"],
            attempts_per_active_member_per_month=preset["attempts_per_active_member_per_month"],
            avg_points_per_attempt=8,
            evidence_bytes_per_point=360,
            prompt_trace_bytes_per_attempt=12_000,
            global_artifact_count=500,
            avg_artifact_bytes=14_000,
        )

    return {
        "scenario_results": scenario_results,
        "max_monthly_attempts": max(row["monthly_attempts"] for row in scenario_results.values()),
        "per_user_artifact_copy_allowed": False,
        "readiness_claim": "estimate_only_not_load_test",
        "next_required_gate": "load_test_hot_read_models_and_storage",
    }


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--member-count", type=int, default=50_000)
    parser.add_argument("--scenario", choices=["standard_100k", "heavy_1m", "peak_3m", "all"], default="all")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.scenario == "all":
        estimate = estimate_m35_capacity_scenarios()
    else:
        preset = dict(SCENARIO_PRESETS[args.scenario])
        preset["member_count"] = args.member_count
        estimate = estimate_m35_capacity(
            member_count=preset["member_count"],
            active_rate=preset["active_rate"],
            attempts_per_active_member_per_month=preset["attempts_per_active_member_per_month"],
            avg_points_per_attempt=8,
            evidence_bytes_per_point=360,
            prompt_trace_bytes_per_attempt=12_000,
            global_artifact_count=500,
            avg_artifact_bytes=14_000,
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(estimate, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 3: Document hot/cold data lifecycle**

Add this policy to the lifecycle contract doc:

```text
Global scoring artifacts are stored once per artifact_version and never copied per learner.
Student attempts store references to artifact_version and point_id, not full rubric copies.
Hot store keeps compact point evidence and current projections.
Prompt, raw LLM trace, and verbose review logs require TTL or cold object storage.
Read models aggregate learner_point_stats, learner_weaknesses, and review_plan_projection.
50k readiness is blocked until synthetic capacity covers 100k, 1M, and 3M attempts/month.
```

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/scripts/test_luban_m35_artifact_capacity.py -q
```

Expected: PASS.

### Task 12: Add Narrow Typed Artifact Query Protocol

**Files:**
- Create: `deeptutor/services/construction_grading/m35_artifact_query.py`
- Create: `tests/services/construction_grading/test_m35_artifact_query.py`

- [ ] **Step 1: Write query protocol tests**

```python
from deeptutor.services.construction_grading.m35_artifact_query import (
    M35ArtifactQuery,
    retrieve_m35_scoring_context,
)


def test_retrieve_rubric_returns_typed_grounded_shape_without_raw_chunks():
    artifact = {
        "artifact_version": "m35_case_scoring_20260609",
        "question_id": "Q1-NA",
        "status": "release_candidate",
        "scoring_points": [{"point_id": "P1", "criterion": "指出需要专家论证", "source_refs": ["s1"]}],
        "quality_gates": {"source_validity": 1.0},
    }

    result = retrieve_m35_scoring_context(
        M35ArtifactQuery(
            question_id="Q1-NA",
            purpose="grading",
            shape="rubric_table",
            citation_required=True,
            budget_tier="low",
        ),
        artifact_store={"Q1-NA": artifact},
    )

    assert result["artifact_version"] == "m35_case_scoring_20260609"
    assert result["shape"] == "rubric_table"
    assert result["ground"]["source_ref_count"] == 1
    assert result["confidence"]["source_validity"] == 1.0
    assert "raw_chunks" not in result
```

- [ ] **Step 2: Implement minimal query protocol**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class M35ArtifactQuery:
    question_id: str
    purpose: Literal["grading", "explanation", "review_plan"]
    shape: Literal["rubric_table", "point_matches", "review_action"]
    citation_required: bool
    budget_tier: Literal["low", "medium", "high"]


def retrieve_m35_scoring_context(
    query: M35ArtifactQuery,
    *,
    artifact_store: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    artifact = artifact_store.get(query.question_id)
    if artifact is None:
        return {
            "found": False,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "artifact_missing",
        }

    source_ref_count = sum(
        len(point.get("source_refs") or [])
        for point in artifact.get("scoring_points") or []
    )

    if query.citation_required and source_ref_count == 0:
        return {
            "found": True,
            "question_id": query.question_id,
            "fail_open": True,
            "reason": "citation_required_but_missing",
        }

    return {
        "found": True,
        "question_id": query.question_id,
        "artifact_version": artifact.get("artifact_version"),
        "purpose": query.purpose,
        "shape": query.shape,
        "budget": {"tier": query.budget_tier},
        "ground": {"source_ref_count": source_ref_count},
        "confidence": {
            "source_validity": float((artifact.get("quality_gates") or {}).get("source_validity") or 0.0)
        },
        "scoring_points": artifact.get("scoring_points") or [],
    }
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/services/construction_grading/test_m35_artifact_query.py -q
```

Expected: PASS.

### Task 13: Add Teacher Review Queue and Compiler Feedback Flywheel

**Files:**
- Modify: `deeptutor/services/construction_grading/compiler_feedback.py`
- Create: `tests/services/construction_grading/test_m35_teacher_review_feedback.py`

- [ ] **Step 1: Write feedback tests**

```python
from deeptutor.services.construction_grading.compiler_feedback import (
    work_order_from_teacher_override,
)


def test_teacher_override_becomes_compiler_candidate_not_release_truth():
    work_order = work_order_from_teacher_override(
        {
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_id": "Q1-NA::P2",
            "override_type": "miss_should_be_partial",
            "teacher_evidence": "学生写到组织专家但主体不完整，应部分给分",
            "source_ref_ids": ["exam_2026#p2"],
        }
    )

    assert work_order["namespace"] == "luban_compiler_candidate"
    assert work_order["payload"]["work_order_type"] == "teacher_override_review"
    assert work_order["payload"]["promote_to_release"] is False
    assert work_order["payload"]["question_id"] == "Q1-NA"
```

- [ ] **Step 2: Implement teacher override work order**

Add this function to the existing `compiler_feedback.py` module, reusing local work-order conventions already present there:

```python
from typing import Any


def work_order_from_teacher_override(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "namespace": "luban_compiler_candidate",
        "origin": "m35_teacher_review",
        "payload": {
            "work_order_type": "teacher_override_review",
            "promote_to_release": False,
            "question_id": event["question_id"],
            "artifact_version": event["artifact_version"],
            "point_id": event["point_id"],
            "override_type": event["override_type"],
            "teacher_evidence": event["teacher_evidence"],
            "source_ref_ids": list(event.get("source_ref_ids") or []),
        },
    }
```

- [ ] **Step 3: Run tests**

Run:

```bash
pytest tests/services/construction_grading/test_m35_teacher_review_feedback.py \
       tests/services/construction_grading/test_compiler_feedback.py -q
```

Expected: PASS.

### Task 14: Add Grading-to-Brain Closure Gate

**Files:**
- Create: `scripts/run_luban_m35_grading_to_brain_loop_gate.py`
- Create: `tests/scripts/test_luban_m35_grading_to_brain_loop_gate.py`

- [ ] **Step 1: Write closure gate tests**

```python
from scripts.run_luban_m35_grading_to_brain_loop_gate import build_m35_loop_trace


def test_m35_hermetic_loop_trace_cannot_claim_convergence():
    trace = build_m35_loop_trace(
        attempt={
            "attempt_id": "attempt_m35_001",
            "user_id": "qa_m35",
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_matches": [
                {"point_id": "Q1-NA::P1", "status": "hit", "mistake_code": ""},
                {"point_id": "Q1-NA::P2", "status": "miss", "mistake_code": "E02"},
            ],
        }
    )

    assert trace["artifact_version"] == "m35_case_scoring_20260609"
    assert trace["learning_evidence"]["point_count"] == 2
    assert trace["learner_memory_event"]["event_type"] == "m35_point_grading_evidence"
    assert trace["weakness_projection"]["mistake_codes"] == ["E02"]
    assert trace["next_action"]["action_type"] == "targeted_retest"
    assert trace["retest_condition"]["required"] is True
    assert trace["canonical_truth_written"] is False
    assert trace["mode"] == "hermetic_trace"
    assert trace["convergence_claim_allowed"] is False


def test_m35_live_readback_loop_trace_can_claim_convergence_when_all_readbacks_exist():
    trace = build_m35_loop_trace(
        attempt={
            "attempt_id": "attempt_m35_002",
            "user_id": "qa_m35",
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_matches": [
                {"point_id": "Q1-NA::P2", "status": "miss", "mistake_code": "E02"},
            ],
        },
        mode="live_readback",
        live_readback={
            "learner_memory_event_id": "evt_m35_001",
            "weakness_projection_id": "weak_m35_001",
            "next_action_id": "nba_m35_001",
            "retest_condition_id": "retest_m35_001",
        },
    )

    assert trace["mode"] == "live_readback"
    assert trace["convergence_claim_allowed"] is True
    assert trace["required_readbacks_present"] is True
    assert trace["canonical_truth_written"] is False
```

- [ ] **Step 2: Implement closure trace builder**

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REQUIRED_LIVE_READBACK_KEYS = (
    "learner_memory_event_id",
    "weakness_projection_id",
    "next_action_id",
    "retest_condition_id",
)


def build_m35_loop_trace(
    *,
    attempt: dict[str, Any],
    mode: str = "hermetic_trace",
    live_readback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    point_matches = list(attempt.get("point_matches") or [])
    mistake_codes = sorted(
        {
            str(point.get("mistake_code"))
            for point in point_matches
            if point.get("mistake_code")
        }
    )

    learning_evidence = {
        "artifact_version": attempt["artifact_version"],
        "question_id": attempt["question_id"],
        "point_count": len(point_matches),
        "point_matches": point_matches,
    }

    trace = {
        "attempt_id": attempt["attempt_id"],
        "user_id": attempt["user_id"],
        "question_id": attempt["question_id"],
        "artifact_version": attempt["artifact_version"],
        "learning_evidence": learning_evidence,
        "learner_memory_event": {
            "event_type": "m35_point_grading_evidence",
            "payload": learning_evidence,
        },
        "weakness_projection": {
            "mistake_codes": mistake_codes,
            "source": "point_matches",
        },
        "next_action": {
            "action_type": "targeted_retest",
            "basis": "missed_scoring_points",
        },
        "retest_condition": {
            "required": bool(mistake_codes),
            "must_reference_artifact_version": attempt["artifact_version"],
        },
        "canonical_truth_written": False,
    }

    live_readback = live_readback or {}
    required_readbacks_present = all(live_readback.get(key) for key in REQUIRED_LIVE_READBACK_KEYS)
    trace["mode"] = mode
    trace["live_readback"] = live_readback
    trace["required_readbacks_present"] = required_readbacks_present
    trace["convergence_claim_allowed"] = mode == "live_readback" and required_readbacks_present
    return trace


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--mode", choices=["hermetic_trace", "live_readback"], default="hermetic_trace")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    live_readback = None
    if args.mode == "live_readback":
        live_readback = {
            "learner_memory_event_id": "evt_m35_live_fixture",
            "weakness_projection_id": "weak_m35_live_fixture",
            "next_action_id": "nba_m35_live_fixture",
            "retest_condition_id": "retest_m35_live_fixture",
        }

    trace = build_m35_loop_trace(
        attempt={
            "attempt_id": "attempt_m35_gate_001",
            "user_id": "qa_m35",
            "question_id": "Q1-NA",
            "artifact_version": "m35_case_scoring_20260609",
            "point_matches": [
                {"point_id": "Q1-NA::P1", "status": "hit", "mistake_code": ""},
                {"point_id": "Q1-NA::P2", "status": "miss", "mistake_code": "E02"},
            ],
        },
        mode=args.mode,
        live_readback=live_readback,
    )

    payload = {
        "ok": args.mode == "hermetic_trace" or trace["convergence_claim_allowed"],
        "mode": args.mode,
        "fixture": str(Path(args.fixture)),
        "trace": trace,
        "convergence_claim_allowed": trace["convergence_claim_allowed"],
        "canonical_truth_written": False,
        "production_write_count": 0,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 3: Wire to existing Learning Brain helpers before production use**

The script may start with the hermetic trace builder above, but that mode proves shape only and must output `convergence_claim_allowed=false`. Production promotion requires `--mode live_readback` and replacing the fixture IDs with existing Learning Brain helpers used by M32 tests:

```text
learning_evidence.py -> writeback.py preview/QA gate -> learner_memory_events
-> synthesize/read-model helper -> PersonalizationContextPack -> NextBestAction
-> retest runner/result
```

Do not create a second learner-memory projection.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/scripts/test_luban_m35_grading_to_brain_loop_gate.py -q
```

Expected: PASS.

## 8. Required Commands

During implementation, each task runs its focused tests. Before claiming M35 complete, run:

```bash
pytest tests/services/construction_grading/test_m35_status.py \
       tests/services/construction_grading/test_question_grading_artifacts.py \
       tests/services/construction_grading/test_rubric_compiler.py \
       tests/services/construction_grading/test_rubric_grader_v1.py \
       tests/services/construction_grading/test_learning_evidence.py \
       tests/services/construction_grading/test_compiler_feedback.py \
       tests/services/construction_grading/test_m35_artifact_governance.py \
       tests/services/construction_grading/test_m35_artifact_query.py \
       tests/services/construction_grading/test_m35_teacher_review_feedback.py \
       tests/services/learner_state/test_m35_learning_evidence_readback.py \
       tests/services/source_compiler/test_scoring_point_asset_compiler.py \
       tests/services/source_compiler/test_scoring_point_recall_calibration.py \
       tests/integration/test_luban_m35_scoring_artifact_ws_shadow.py \
       tests/scripts/test_luban_m35_label_authority.py \
       tests/scripts/test_luban_m35_artifact_capacity.py \
       tests/scripts/test_luban_m35_grading_to_brain_loop_gate.py \
       tests/scripts/test_luban_m35_scoring_artifact_ab.py -q

python scripts/audit_luban_m35_label_authority.py \
  --answers tests/fixtures/luban_m35_case_scoring/student_answers.jsonl \
  --output artifacts/luban_grading_artifacts/m35_label_authority_audit/report.json

python scripts/run_luban_m35_scoring_artifact_ab.py \
  --output artifacts/luban_grading_artifacts/m35_scoring_artifact_ab/report_shape.json \
  --tier shape_stub

python scripts/run_luban_m35_scoring_artifact_ab.py \
  --output artifacts/luban_grading_artifacts/m35_scoring_artifact_ab/report_cached.json \
  --tier cached_judge_replay

python scripts/run_luban_m35_scoring_artifact_release_gate.py \
  --fixture tests/fixtures/luban_m35_case_scoring \
  --output artifacts/luban_grading_artifacts/m35_scoring_artifact_gate/go_no_go_m35.json

python scripts/estimate_luban_m35_artifact_capacity.py \
  --member-count 50000 \
  --scenario all \
  --output artifacts/luban_grading_artifacts/m35_capacity/estimate_50k_scenarios.json

python scripts/run_luban_m35_grading_to_brain_loop_gate.py \
  --fixture tests/fixtures/luban_m35_case_scoring \
  --mode hermetic_trace \
  --output artifacts/luban_grading_artifacts/m35_grading_to_brain_loop/report_hermetic.json

python scripts/run_luban_m35_grading_to_brain_loop_gate.py \
  --fixture tests/fixtures/luban_m35_case_scoring \
  --mode live_readback \
  --output artifacts/luban_grading_artifacts/m35_grading_to_brain_loop/report_live_readback.json
```

If `scripts/check_contract_guard.py` applies to the touched contracts or `/api/v1/ws` request shape, run:

```bash
python scripts/check_contract_guard.py
```

## 9. Rollout Gates

### POC GO

```text
questions >= 20
answers >= 100
label_authority in {teacher_validated, po_directional_single_reviewer, ai_council_directional}
generated_self_label_count = 0 for any quality GO
bucket coverage includes hit/partial/miss/wrong_content/near_synonym/list/calculation/stem_fact/off_path
evaluation_tier includes cached_judge_replay; shape_stub-only cannot GO
point_precision >= 0.90
point_recall >= 0.90
score_mae <= 1.0 or >=20% improvement over baseline
source_validity >= 0.95
wrong_path_rate <= 0.03
prior_artifact_first_failure_beaten = true
hallucinated_scoring_points = 0
rag_chunk_as_answer_key = 0
candidate_used_as_release_truth = 0
client_status_promoted_to_release_truth = 0
orphan_release_candidate_count = 0
per_user_artifact_copy_allowed = false
production_write_count = 0
canonical_truth_written = false
```

### MVP GO

```text
questions >= 100
answers >= 500
at least one teacher/manual spot-check slice is blinded and filled
blind answer-quality judge: artifact-first >= baseline
manual teacher spot-check passes
Learning Brain evidence reads back point-level weaknesses
review-plan output contains chapter, mistake pattern, practice action, retest condition
source-pollution work orders reduced between compiler runs
typed artifact query protocol is used by runtime-facing M35 retrieval
teacher review queue converts overrides into compiler work_orders, not release truth
Grading-to-Brain loop gate runs mode=live_readback with convergence_claim_allowed=true
```

### Production Default GO

```text
controlled cohort only
case grading only
kill switch documented
rollback tested
observability dashboard fresh
teacher/manual review escape hatch available
live_provider_sample has bounded cost/latency report
50k capacity gate covers 100k/1M/3M attempts per month scenarios
hot/cold data lifecycle is documented and tested
prompt/trace retention is TTL or cold-storage backed
Learning Brain / GBrain convergence path is live-readback verified
no canonical learner truth write unless separately authorized
no published registry unless separately authorized
```

## 10. Workload

| Scope | Estimate |
|---|---:|
| M35 POC: status lock, label audit, 20 questions / 100 answers, three-tier A/B, artifact-first shadow | 12-18 person-days |
| M35 bridge hardening addendum: ownership governance, typed query, 50k capacity estimate, teacher review queue, Grading-to-Brain closure gate | 10-16 person-days |
| M36 governance/flywheel MVP: 100 questions / 500 answers, teacher queue, compiler feedback loop, source-pollution reduction | 18-28 person-days |
| M37 learner product loop: Learning Brain readback, review-plan projection, `compareAttempts`, `explainScoringPoint`, retest outcome | 22-35 person-days |
| M38 production-grade: governed cohort, UI explanation, monitoring, 50k capacity, release package | 35-55 person-days |

With subagent-driven development, the POC can fit into 1-2 calendar weeks if the 20-question / 100-answer fixture is already label-audited and owner review is fast. If label authority is missing, spend the first iteration only on Task 0B and Task 1; do not start runtime shadow.

## 11. Open Risks

| Risk | Handling |
|---|---|
| Golden answers are not teacher-reviewed | Keep verdict at NO-GO or WEAK-GO; do not claim official scoring |
| Source refs are keyword-matched but not actually supportive | Source-level provenance audit is required before GO |
| Negative evidence too sparse | Treat as review blocker for near-neighbor topics |
| LLM judge over-accepts vague answers | Add adversarial answers and high-risk review gate |
| Artifact-first lowers answer quality | Keep shadow; feed misses back to compiler |
| M35 stops at offline artifacts and never changes learner outcomes | Task 14 must prove artifact evidence reaches Learning Brain, next action, and retest condition |
| GBrain/Learning Brain integration becomes a third learner memory | Keep `learner_memory_events` and Learning Brain claim lifecycle as the only learner-memory authority |
| Artifacts are copied per user and data grows linearly with membership | Task 11 forbids per-user artifact copies; attempts reference `artifact_version` and `point_id` |
| Trace/prompt logs overwhelm hot storage at 50k members | Keep verbose traces under TTL or cold storage; hot read models store compact evidence and aggregates |
| Teachers become a bottleneck by reviewing every answer | Queue only low-confidence, high-frequency, source-conflict, override, and high-impact samples |
| Existing dirty worktree mixes unrelated changes | Stage task files explicitly; never use `git add -A` |

## 12. Execution Handoff

Plan complete. Execution options:

1. **Subagent-Driven (recommended)**: one fresh subagent per task, two-stage review after each task, narrow commits.
2. **Inline Execution**: run tasks in this session using `superpowers:executing-plans`, with checkpoint reviews after Task 1, Task 4, Task 8, and Task 9.

Recommended first execution batch:

```text
Task 0A: Reconcile M35 status semantics
Task 0B: Audit label authority
Task 1: Freeze M35 golden eval pack
Task 2: Harden question artifact gates
Task 4: Add three-tier A/B runner
```

Do not start Task 5 runtime attachment until Task 0A, Task 0B, Task 1, and Task 2 are green; otherwise the runtime will encode status ambiguity or fixture weakness instead of compiler truth.

Recommended second execution batch after Task 8/9 produces an honest verdict:

```text
Task 10: Add artifact ownership and lifecycle governance
Task 11: Add data lifecycle and 50k capacity gate
Task 12: Add narrow typed artifact query protocol
Task 13: Add teacher review queue and compiler feedback flywheel
Task 14: Add Grading-to-Brain closure gate
```

Do not claim "Nexus + GBrain convergence" until Task 14 proves the same attempt can be traced from scoring artifact through Learning Brain readback to next action and retest condition. Do not claim "50k-ready" until Task 11 reports at least 100k, 1M, and 3M attempts/month scenarios with hot/cold storage and partitioning decisions.
