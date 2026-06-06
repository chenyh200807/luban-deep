# Luban M26 Compiled Context + Open-world Diagnostic Closure Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement task by task. Before code, use `plan-eng-review`, `root-cause-debugging`, and `llm-data-organization`.

**Goal:** Complete the master-control §0.26 target: Luban becomes an authority-aware open-world architecture-practice expert, not a narrow registry lookup grader.

**Architecture:** Build one fat-skill `CompiledContextService` / `LubanContextPack` authority that unifies question identity, answer keys, case rubric/spec/source slices, KB v5 retrieval, learner context, and diagnostic policy. Thin wrappers (`/api/v1/ws`, TutorBot, `deep_question`) only pass request context, flags, and append results.

**Tech Stack:** Python, FastAPI `/api/v1/ws`, TutorBot, construction grading services, RAG `kbv5`, Learning Brain read models, pytest, hermetic fixtures, optional live-gated DeepSeek/Qwen/KB v5 checks.

---

## 1. Canonical Gap

This is not another registry gate. M26 closes the gap between:

- **Luban scoring engine:** this answer is right/wrong/partial, why, with evidence span and risk labels.
- **Learning Brain / GBrain:** learner profile, weakness evolution, retest, next action.
- **Nexus-style Knowledge Engine:** fine-grained, provenance-rich, scoped context that makes the LLM stronger.

Current implementation is strong but incomplete:

| Area | Current state | Gap |
|---|---|---|
| Case v1 LLM adjudication | Runtime LLM packet + validator exists. | Mostly consumes signed registry/rubric slices, not a unified compiled context. |
| Objective lane | Candidate and real-source candidate exist. | Governed `questions_bank` release-candidate signing is not complete. |
| KB v5 / RAG | KB v5 direct Postgres pipeline exists as WIP and benchmark evidence exists. | Needs clean runtime integration and contract closure, not benchmark-only authority. |
| Open-world diagnostic | `open_world_fail_open` exists in packet builder/adapter. | Needs true TutorBot/deep_question answer quality, candidate/work-order generation, and no-refusal testing. |
| Compiler | M20/M20.1/M20.2 delta artifacts exist. | No full-scope continuous compiler -> signed context pack -> runtime consumer loop. |
| Learning Brain | Evidence/claim/PCP preview and dry-run proofs exist. | Needs to consume the same context pack and keep canonical truth gated. |

## 2. Expert Team Split

Run as coordinated expert work. If multiple agents implement in parallel, use isolated worktrees.

| Role | Scope | Must not do |
|---|---|---|
| Release Commander | Git status, dirty/WIP audit, no-clobber, final package, test matrix. | Do not reset/stash/overwrite user or parallel-agent files. |
| Context Architect | Define `LubanContextPack` schema and `CompiledContextService` fat skill. | Do not add policy to thin wrappers. |
| Knowledge/RAG Lead | Absorb KB v5 runtime WIP, RAGService provider path, read-only guard, contract tests. | Do not make RAG a grading authority. |
| Objective Authority Lead | Extract governed answer keys from `questions_bank`, validate/sign runtime supply v2 release candidate. | Do not let LLM or RAG override answer keys. |
| Case Grading Lead | Make case LLM adjudicator consume compiled context. | Do not loosen validator or source/spec/list guards. |
| Open-world Lead | Build non-refusal diagnostic path and compiler work-order ledger. | Do not claim official score or official answer for unknown questions. |
| Learning Brain Lead | Consume compiled evidence into claim/PCP preview. | Do not write canonical learner truth from candidate/shadow evidence. |
| QA/Benchmark Lead | `/api/v1/ws`, TutorBot, WeChat-style QA, A/B quality, latency, cost, satisfaction evidence. | Do not call local stub results live or production. |

## 3. Design Gates Before Coding

Every implementation agent must write these five answers in its local FINDING before code changes:

1. **One business fact:** What unique fact is this task protecting?
2. **One authority:** Who writes, stores, verifies, and reads that fact?
3. **Concepts to delete or demote:** Which duplicate states, aliases, fallback decisions, or wrapper policies are removed or downgraded?
4. **Why not old pattern:** Why is this not another registry-only gate, regex classifier, or wrapper special case?
5. **LLM vs deterministic split:** What does the LLM organize/diagnose, and what does deterministic validation sign or block?

If these cannot be answered, stop and write a blocker note instead of patching.

## 4. Runtime Modes

| Mode | Trigger | Output | Guard |
|---|---|---|---|
| Official grading | Canonical question, signed answer key, signed rubric/source/spec/list, release-candidate registry. | Score or controlled score, point hits, evidence span, blocked reason, Learning Brain evidence draft. | LLM/RAG/model vote cannot change signed truth. |
| Open-world diagnostic | Unknown question, user-pasted question, variant, missing authority, broad architecture practice question. | Non-formal diagnosis, concept explanation, likely scoring dimensions, next practice, uncertainty label, work-order. | No official score, no official answer claim, no auto mastery. |
| Compiler feedback | High-value unknown, repeated misses, RAG evidence, review queue, disagreement. | Candidate ledgers: question, answer key, rubric, source, spec/list/calc, rejected, work-order. | Candidate never enters runtime as release truth. |

## 5. Implementation Tasks

### Task 1: No-clobber Audit + M26 Package Skeleton

**Files:**
- Create: `scripts/run_luban_compiled_context_open_world_m26.py`
- Create: `tests/scripts/test_luban_compiled_context_open_world_m26.py`
- Output: `artifacts/luban_grading_artifacts/compiled_context_open_world_m26_YYYYMMDD/`

**Steps:**
- [ ] Record `git status --short --branch`, realpath, current HEAD, dirty groups, and parallel WIP.
- [ ] Classify dirty files as `owned_by_m26`, `parallel_wip`, `pre_existing`, or `unresolved`.
- [ ] Generate artifact skeleton and required filenames.
- [ ] Add a smoke test that fails until required artifact files are generated.

**Acceptance:**
- Artifact package lists all required M26 outputs.
- No unrelated file is modified.
- No reset/stash/checkout is used.

### Task 2: Compiled Context Fat Skill

**Files:**
- Create: `deeptutor/services/construction_grading/compiled_context.py`
- Test: `tests/services/construction_grading/test_compiled_context.py`

**Steps:**
- [ ] Define `LubanContextPack` with `question_context`, `source_context`, `rubric_context`, `learner_context`, `diagnostic_policy`, `budget_policy`, and `provenance`.
- [ ] Implement `build_luban_context_pack(...)` as the only context assembly authority.
- [ ] Support resolved official question, resolved case rubric, retrieval-only, and unresolved open-world prompts.
- [ ] Add hash/provenance fields for supply bundle, KB refs, answer-key manifest, and learner pack.
- [ ] Add deterministic guards: unknown => no official score; candidate => no formal score; signed release candidate => controlled official mode allowed.

**Acceptance:**
- Same context shape works for objective, case, retrieval-only, and open-world.
- No secrets or hidden official answer leakage.
- Unit tests cover all four context modes.

### Task 3: KB v5 Runtime RAG Closure

**Files:**
- Review/modify if needed: `deeptutor/services/rag/pipelines/kbv5.py`
- Review/modify if needed: `deeptutor/services/rag/factory.py`
- Review/modify if needed: `deeptutor/services/config/knowledge_base_config.py`
- Test: `tests/services/rag/test_kbv5_pipeline.py`
- Update if contract changes: `contracts/rag.md`

**Steps:**
- [ ] Absorb existing KB v5 WIP; do not rewrite from scratch.
- [ ] Verify `RAGService -> factory -> KbV5Pipeline`.
- [ ] Enforce read-only direct Postgres retrieval and failure contract.
- [ ] Ensure returned sources include `source_table=kb_v5.chunks`, stable chunk id, provenance, and content hash.
- [ ] Ensure KB v5 is retrieval/context only.

**Acceptance:**
- Hermetic tests prove provider selection, source projection, read-only metadata, and fail-closed behavior.
- Optional live-gated check can query `public.search_chunks_v2` without writing.
- RAG never emits grading decisions.

### Task 4: Objective Governed Release Candidate

**Files:**
- Create: `deeptutor/services/construction_grading/objective_governed_registry_extractor.py`
- Create: `deeptutor/services/construction_grading/runtime_supply/v2_objective_release_candidate/`
- Test: `tests/services/construction_grading/test_objective_governed_registry_extractor.py`

**Steps:**
- [ ] Read `questions_bank` as governed source in read-only mode.
- [ ] Extract objective rows with question id, type, stem/options hash, answer key, source metadata, content hash, and version lineage.
- [ ] Validate conflicts, missing answers, malformed options, duplicate ids, unsupported types.
- [ ] Sign records and manifest.
- [ ] Keep namespace separate from case registry.

**Acceptance:**
- If live source is available, answer-key count should exceed the current 62 fixture rows.
- If live source is unavailable, hermetic fixture passes and live blocker is precise.
- `answer_key_override=0`, `LLM_changed_key=0`, `rag_chunk_as_answer_key=0`.
- Tamper/missing/malformed bundle fails closed.
- Status is `release_candidate`, not `published`.

### Task 5: Context Consumers

**Files:**
- Modify minimally: `deeptutor/services/construction_grading/runtime_llm_adjudicator.py`
- Modify minimally: `deeptutor/services/construction_grading/objective_runtime_adapter.py`
- Modify minimally: TutorBot/deep_question integration point already used for grading.
- Test: related tests under `tests/services/construction_grading/`, `tests/core/`, and `tests/tutorbot/`.

**Steps:**
- [ ] Case adjudicator consumes `LubanContextPack.rubric_context/source_context/learner_context`.
- [ ] Objective runtime consumes `LubanContextPack.question_context/diagnostic_policy`.
- [ ] TutorBot or deep_question can request a context pack for explanation/diagnosis.
- [ ] Learning Brain preview receives evidence refs derived from the same context.

**Acceptance:**
- At least three surfaces consume the same context pack: TutorBot, runtime grading, Learning Brain.
- Wrapper tests assert wrappers do not assemble policy themselves.
- Existing behavior remains backward-compatible when flags are off.

### Task 6: Open-world Diagnostic Runtime

**Files:**
- Create: `deeptutor/services/construction_grading/open_world_diagnostic.py`
- Test: `tests/services/construction_grading/test_open_world_diagnostic.py`
- Integration: `/api/v1/ws` or TutorBot unknown-prompt tests.

**Steps:**
- [ ] Implement diagnostic answer over `LubanContextPack` + KB v5 refs + DeepSeek/Qwen when live enabled.
- [ ] Output `status=unverified_diagnostic`, `formal_score_allowed=false`, `official_answer_claimed=false`, `uncertainty_label`, `likely_scoring_dimensions`, `evidence_refs`, `next_practice`, and `candidate_work_order`.
- [ ] Fail closed only for unsafe/unrelated input; otherwise fail open with useful diagnosis.

**Acceptance:**
- Unknown/not-in-bank refusal rate = 0 for construction-related prompts.
- Every output has status and uncertainty label.
- No formal score is emitted.
- High-value unknown candidate/work-order generation rate >= 90%.

### Task 7: Compiler Feedback Loop

**Files:**
- Create: `deeptutor/services/construction_grading/compiler_feedback.py`
- Test: `tests/services/construction_grading/test_compiler_feedback.py`

**Steps:**
- [ ] Convert open-world diagnostics, repeated misses, review queue items, and RAG evidence into candidate ledgers.
- [ ] Produce ledgers: `question_candidate`, `answer_key_candidate`, `rubric_candidate`, `source_candidate`, `machine_spec_candidate`, `rejected`, `work_order`, `release_candidate_delta`.
- [ ] Keep candidate artifacts and release artifacts in separate namespaces.

**Acceptance:**
- Source laundering = 0.
- Candidate never enters runtime as release truth.
- Rejected and work-order items include reason and next action.

### Task 8: Learning Brain Integration

**Files:**
- Modify only through existing learner-state authority modules.
- Test: Learning Brain evidence/claim/PCP tests.

**Steps:**
- [ ] Official grading produces evidence draft.
- [ ] Open-world diagnostic produces diagnostic evidence draft.
- [ ] Gate claim promotion: release/teacher/retest proof may become claim proposal; candidate/shadow/open-world stays preview/needs_retest.
- [ ] Preserve subject/user isolation.

**Acceptance:**
- Learning Brain evidence coverage >= 0.95.
- `shadow_promoted_to_mastery=0`.
- `candidate_promoted_to_mastery=0`.
- `canonical_truth_written=false`.
- No second learner memory or personalization authority.

### Task 9: M26 A/B + Real-chain QA

**Files:**
- Create: `scripts/run_luban_m26_ab_and_real_chain_qa.py`
- Test: `tests/scripts/test_luban_m26_ab_and_real_chain_qa.py`

**Steps:**
- [ ] Build scenario matrix: historical objective, governed objective invalid, case answer in registry, case variant, open construction concept question, user-pasted unknown question, retest/next-action scenario.
- [ ] Compare v0, old RAG/KB v5 context, v1 official mode, and v1 open-world diagnostic mode.
- [ ] Record quality, correctness, latency, cost, fallback, evidence span validity, and satisfaction proxy.

**Acceptance:**
- Same scenario batch produces comparable metrics.
- Safety invariants all zero.
- Latency and token/cost are reported.
- Any live blocker is explicit and not replaced by fake data.

### Task 10: Final M26 Canonical Package + Docs

**Files:**
- Output: `artifacts/luban_grading_artifacts/compiled_context_open_world_m26_YYYYMMDD/`
- Update: `docs/plan/2026-06-04-luban-grading-engine-master-control-plan.md`
- Update: `docs/plan/INDEX.md`

**Required reports:**
- `compiled_context_schema_m26.json`
- `context_consumer_ledger_m26.json`
- `open_world_qa_ledger_m26.jsonl`
- `compiler_feedback_ledger_m26.jsonl`
- `learning_brain_evidence_report_m26.json`
- `ab_quality_latency_cost_report_m26.json`
- `safety_invariant_report_m26.json`
- `go_no_go_m26.json`
- `FINDING_compiled_context_open_world_m26_YYYYMMDD.md`

**Acceptance:**
- M26 GO only if all hard gates pass.
- If not GO, verdict must be WEAK-GO or NO-GO with exact blockers.
- Docs do not overclaim production default, published registry, or canonical truth write.

## 6. Hard Safety Invariants

The M26 package must compute:

| Invariant | Required value |
|---|---|
| unknown/not-in-bank construction refusal rate | 0 |
| official_score_laundering | 0 |
| answer_key_override | 0 |
| source_laundering | 0 |
| model_vote_as_source | 0 |
| council_vote_as_source | 0 |
| rag_chunk_as_answer_key | 0 |
| candidate_used_as_release_truth | 0 |
| list_partial_auto | 0 |
| false_positive | 0 |
| source_mismatch | 0 |
| production_write_count | 0 |
| canonical_truth_written | false |
| shadow_or_candidate_promoted_to_mastery | 0 |
| non-cohort leakage, if cohort flags are used | 0 |

## 7. Test Matrix

Minimum final command set:

```bash
python -m pytest \
  tests/scripts/test_luban_compiled_context_open_world_m26.py \
  tests/scripts/test_luban_m26_ab_and_real_chain_qa.py \
  tests/services/construction_grading/test_compiled_context.py \
  tests/services/construction_grading/test_open_world_diagnostic.py \
  tests/services/construction_grading/test_compiler_feedback.py \
  tests/services/rag/test_kbv5_pipeline.py \
  tests/services/construction_grading/test_objective_grader.py \
  tests/services/construction_grading/test_objective_runtime_adapter.py \
  tests/services/construction_grading/test_objective_answer_key_compiler.py \
  tests/services/construction_grading/test_objective_real_source_extractor.py \
  tests/scripts/test_luban_runtime_llm_adjudicator_m17a.py \
  tests/tutorbot/test_agent_loop_question_lifecycle.py \
  tests/services/learner_state/test_learning_brain_read_model.py \
  -q
```

Optional live-gated checks must be explicit, resumable, and cost-accounted:

```bash
python scripts/run_luban_compiled_context_open_world_m26.py --run-live-kbv5 --run-live-llm
python scripts/run_luban_m26_ab_and_real_chain_qa.py --run-live
```

## 8. Unexpected Condition Policy

When something unexpected appears, classify it before acting:

| Condition | Required response |
|---|---|
| User or parallel-agent dirty file | No-clobber. Read if needed, do not overwrite. Record owner/mtime/status. |
| Missing live credentials | Run hermetic tests, record exact live blocker, do not fake live result. |
| Existing WIP solves part of task | Absorb with minimal edits; do not rewrite from scratch. |
| Test harness artifact disagrees with runtime | Reproduce through `/api/v1/ws` or the real service path before declaring product failure. |
| Candidate looks useful but unverified | Keep candidate/work-order; do not promote to release truth. |
| Wrapper starts growing policy logic | Stop and move policy into fat skill. |
| Broad production/default/canonical write question appears | Stop. Requires separate explicit user authorization. |

## 9. Final Report Requirements

The final M26 report must answer:

1. Which master-control §0.26 goals are completed?
2. Which surfaces consume `LubanContextPack`?
3. How does the system handle in-bank, out-of-bank, historical, variant, open Q&A, grading, and retest scenarios?
4. What compiler candidates/work-orders were generated?
5. What knowledge/rubric/evidence coverage remains incomplete?
6. What Learning Brain evidence was produced, and what did not become canonical truth?
7. What tests were run, with exact commands and results?
8. What still blocks production default, published registry, or canonical learner truth?

## 10. Definition of Done

M26 is complete only when:

- `LubanContextPack` exists and is consumed by at least three runtime surfaces.
- KB v5 runtime retrieval is cleanly integrated or a precise blocker is recorded.
- Governed objective release-candidate extraction is implemented or precisely blocked by missing source access.
- Open-world diagnostic is non-refusing, useful, labeled, and safe.
- Compiler feedback creates candidate/work-order ledgers.
- Learning Brain consumes evidence without unsafe promotion.
- A/B and real-chain QA report quality, latency, cost, and satisfaction proxy.
- All hard invariants pass.
- Docs and artifacts are updated.
