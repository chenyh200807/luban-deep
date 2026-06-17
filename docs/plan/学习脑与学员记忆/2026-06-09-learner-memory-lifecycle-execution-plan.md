# Learner Memory Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every learner signal flow through four explicit stages: Evidence Ledger -> Short-Term Learning Memory -> Stable Learner Claims -> Canonical Learner Truth.

**Architecture:** Keep `learner_memory_events` as the only append-only evidence ledger and `LearnerStateService` as the only long-term learner-truth authority. Add lifecycle vocabulary and promotion rules around existing `learning_evidence`, `learning_synthesis`, `PersonalizationContextPack`, `NextBestAction`, and canonical write gates instead of creating a second memory store.

**Tech Stack:** Python, FastAPI, Supabase/core-store, local learner-state JSONL fallback, pytest, existing `/api/v1/ws` runtime.

---

## Current Baseline

The current live flow already writes grading signals into `learner_memory_events`:

```text
/api/v1/ws
  -> deep_question
  -> construction_grading_result
  -> write_grading_error_events()
  -> LearnerStateService.append_memory_event(memory_kind="learning_evidence")
  -> learning_synthesis
  -> canonical_truth_promotion_decision()
```

What is still weak:

- The product terms are not explicit enough. `L0_observed`, `L1_repeated`, and `L2_confirmed` exist, but the user-facing lifecycle is not named as a first-class contract.
- Teacher-review compatibility fields still dominate the language even though production should be AI-first and policy-first.
- `certified_grading_policy` exists as the preferred production authority, but upstream grading packages still need to attach it consistently.
- Reports and TutorBot personalization should read lifecycle stage semantics instead of guessing from raw quality fields.

## Execution Status — 2026-06-09 Follow-Up

Subagent review found Tasks 1-6 are implemented and locally tested. The remaining high-risk gaps are not another memory store; they are authority and evidence gaps:

- **Producer authority gap closed in this follow-up:** `deep_question` grading producer can now carry sanitized `certified_grading_policy` only when a trusted server caller passes `governed_registry_status` plus a valid certified policy block. `learning_evidence` also refuses to mint or consume `trusted_adjudication.source=certified_grading_policy` unless the caller explicitly passes `governed_certified_authority=True` and the grading payload already has governed release authority (`release_truth=true`, `official_release_score=true`, `answer_key_authority=governed_signed_registry`, and compiled-context official scoring allowed). Client/context-injected `registry_status`, `certified_grading_policy`, `trusted_adjudication`, or forged authority fields still cannot mint trusted adjudication.
- **Canonical gate hardening closed in this follow-up:** broad production canonical promotion now requires both `trusted_adjudication` and at least one stable learner claim (`stable_learner_claim` or L1/L2/L3 equivalent). `certified_grading_policy` sources must also carry `policy_id`, `rubric_hash`, and `grader_version`. L0-only projections cannot write canonical truth even if a malformed projection includes a trusted block.
- **Repeatable soak artifact contract added:** `scripts/run_learner_memory_lifecycle_test2_cohort_soak.py` generates `artifacts/luban_grading_artifacts/learner_memory_lifecycle_<timestamp>/`-shaped evidence locally without network/SSH/remote writes. Its status is explicitly `LOCAL_ARTIFACT_GO`, with `evidence_scope=local_core_store_artifact_contract`, so it cannot be mistaken for deployed test2 proof. It proves the evidence format for `grading -> learning_evidence -> stable claim -> PCP -> NBA -> retest -> certified trusted_adjudication -> canonical write/readback`.
- **Remote test2 runner contract closed:** the same runner now supports `--mode remote-test2-ws`. It authenticates against test2, verifies a `qa_`/`operator_` cohort identity, sends two real authenticated `/api/v1/ws` `deep_question` turns, optionally triggers authorized remote synthesis inside `Aliyun-ECS-2:/root/deeptutor`, then reads back `GET /api/v1/learning-brain/projection` and `GET /api/v1/mobile/learning-report?schema_version=2`. It emits `REMOTE_TEST2_WS_GO` only when both WS turns produce `construction_grading_result`, canonical synthesis/readback succeeds, and both read models expose the same non-empty `output_projection_hash`.
- **Deployed test2 proof captured:** `artifacts/luban_grading_artifacts/learner_memory_lifecycle_test2_remote_20260609_182651/` returned `REMOTE_TEST2_WS_GO`: `ws_grading_ok=true`, `remote_synthesis.payload.canonical_truth_promotion.reason=production_cohort_authorized`, `requires_human=false`, and Learning Brain/report readback shared `sha256:9515e22869a3c40d18138d4cd6f73e444c2df42eaad20424f1597b71f73517a8`.
- **Canonical taxonomy binding closed:** `learning_evidence` now attaches `canonical_topic` via the existing taxonomy resolver before report/synthesis consumers run. The resolver validates classifier picks against canonical options and then resolves them back to compiled taxonomy node codes, so learner-facing reports and long-term claims do not get pulled to a wrong legacy `node_code`.
- **Evidence idempotency/read-model dedupe closed:** `LearnerStateService.append_memory_event()` remains the write authority for dedupe; the learning-report read model now also folds same `dedupe_key`/fingerprint events so local+remote replay cannot show one attempt twice. Same-question real retests remain separate when their dedupe keys differ.
- **Automatic synthesis trigger added:** when `LUBAN_LEARNING_EVIDENCE_AUTO_SYNTHESIS_ENABLED=1`, new `learning_evidence` appends trigger `synthesize_learning_truth(..., dry_run=False)` once per new deduped event. In production this auto path is cohort-gated to the existing `qa_`/`operator_` canonical cohort; broad users still require explicit promotion gates.
- **Real long-case soak scenario added:** the remote runner now supports `--scenario construction-long-case`, sending the commodity-residential long case through the same authenticated `/api/v1/ws` initial/retest flow and writing the scenario id/question id into the artifact manifest.
- **Real long-case deployed proof captured:** `artifacts/luban_grading_artifacts/learner_memory_lifecycle_remote_1781003089/` returned `REMOTE_TEST2_WS_GO` for `scenario_id=construction-long-case`: both WS turns had `construction_grading_result`, remote synthesis was triggered, `canonical_truth_promotion.reason=production_cohort_authorized`, `requires_human=false`, and Learning Brain/report readback shared `sha256:3fab684bcbdb341a52f69e3ab6c47521cf9a0b2333b27c735557a24179311380`.

## Non-Goals

- Do not create a second learner memory table, second RAG, second WebSocket, or second profile.
- Do not let raw chat text become long-term truth without a learning-signal extractor.
- Do not let LLM-only subjective judgement write canonical truth.
- Do not remove teacher-final compatibility fields in one step; demote them behind `trusted_adjudication`.
- Do not present `teacher_final` / `teacher_reviewed` as the external or main-chain authority; they are legacy aliases only. AI-first trusted adjudication is the production naming and policy surface.
- Do not enable broad production canonical writes until test2 evidence proves write/readback safety.

## Single Authority

| Business Fact | Single Authority |
| --- | --- |
| Raw learner signal happened | `learner_memory_events` |
| Evidence payload schema | `construction_grading.learning_evidence` and learner-state event builders |
| Short-term candidate memory | `learning_synthesis.observed_candidates` |
| Stable learner claim | `learning_synthesis.weak_points` / claim lifecycle |
| Long-term canonical truth | `LearnerStateService.write_compiled_learning_truth` + core-store gate |
| Production promotion decision | `canonical_truth_promotion_decision` |

## Lifecycle Contract

### Stage 1: Evidence Ledger

Every learner-relevant signal is appended as an event:

```text
chat learning signal
answer submission
grading result
training started/completed
retest outcome
mistake-book action
product behavior event
```

Minimum event fields:

```python
{
    "memory_kind": "learning_evidence",
    "source_feature": "...",
    "source_id": "...",
    "payload_json": {
        "event_type": "learning_evidence",
        "quality": {"evidence_level": "L0_observed"},
        "memory_lifecycle_stage": "evidence_ledger"
    }
}
```

### Stage 2: Short-Term Learning Memory

Single observations become candidate memory:

```python
{
    "memory_lifecycle_stage": "short_term_learning_memory",
    "evidence_level": "L0_observed",
    "use_for": ["immediate_feedback", "today_task", "retest_candidate", "next_best_action_hint"],
    "not_for": ["canonical_learner_truth_without_promotion"]
}
```

### Stage 3: Stable Learner Claims

Evidence is promoted to stable claims when at least one condition is true:

```text
L1_repeated: same concept + same error repeated across eligible attempts
L2_confirmed: trusted_adjudication exists and conflict is resolved
L2_real_retest: real non-preview retest validates improvement/regression
```

### Stage 4: Canonical Learner Truth

Only stable claims that pass `canonical_truth_promotion_decision()` can write long-term truth:

```text
production cohort user -> allowed by cohort gate
real broad user -> requires trusted_adjudication
trusted source -> certified_grading_policy / llm_jury / golden_label / operator / teacher_final compat
confidence -> >= configured minimum
conflict_status -> resolved / no_conflict
requires_human -> false
```

## Implementation Tasks

### Task 1: Add First-Class Lifecycle Vocabulary

**Files:**
- Create: `deeptutor/services/learner_state/memory_lifecycle.py`
- Test: `tests/services/learner_state/test_memory_lifecycle.py`

- [ ] **Step 1: Write failing tests**

```python
from deeptutor.services.learner_state.memory_lifecycle import (
    LIFECYCLE_STAGE_CANONICAL_TRUTH,
    LIFECYCLE_STAGE_EVIDENCE_LEDGER,
    LIFECYCLE_STAGE_SHORT_TERM,
    LIFECYCLE_STAGE_STABLE_CLAIM,
    lifecycle_stage_for_evidence_level,
)


def test_lifecycle_stage_for_evidence_levels() -> None:
    assert lifecycle_stage_for_evidence_level("L0_observed") == LIFECYCLE_STAGE_SHORT_TERM
    assert lifecycle_stage_for_evidence_level("L1_repeated") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("L2_confirmed") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("L3_mastery_signal") == LIFECYCLE_STAGE_STABLE_CLAIM
    assert lifecycle_stage_for_evidence_level("") == LIFECYCLE_STAGE_EVIDENCE_LEDGER


def test_canonical_truth_stage_is_reserved_for_write_gate() -> None:
    assert LIFECYCLE_STAGE_CANONICAL_TRUTH == "canonical_learner_truth"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
python -m pytest tests/services/learner_state/test_memory_lifecycle.py -q
```

Expected: import failure because `memory_lifecycle.py` does not exist.

- [ ] **Step 3: Implement vocabulary**

Add:

```python
from __future__ import annotations

from typing import Any

LIFECYCLE_STAGE_EVIDENCE_LEDGER = "evidence_ledger"
LIFECYCLE_STAGE_SHORT_TERM = "short_term_learning_memory"
LIFECYCLE_STAGE_STABLE_CLAIM = "stable_learner_claim"
LIFECYCLE_STAGE_CANONICAL_TRUTH = "canonical_learner_truth"

_STABLE_LEVELS = {"L1_repeated", "L2_confirmed", "L2_real_retest", "L3_mastery_signal"}


def lifecycle_stage_for_evidence_level(level: Any) -> str:
    text = str(level or "").strip()
    if text == "L0_observed":
        return LIFECYCLE_STAGE_SHORT_TERM
    if text in _STABLE_LEVELS:
        return LIFECYCLE_STAGE_STABLE_CLAIM
    return LIFECYCLE_STAGE_EVIDENCE_LEDGER
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
python -m pytest tests/services/learner_state/test_memory_lifecycle.py -q
```

Expected: pass.

### Task 2: Stamp Learning Evidence With Lifecycle Stage

**Files:**
- Modify: `deeptutor/services/construction_grading/learning_evidence.py`
- Modify: `deeptutor/services/construction_grading/writeback.py`
- Test: `tests/services/construction_grading/test_learning_evidence.py`
- Test: `tests/services/construction_grading/test_audit_and_writeback.py`

- [ ] **Step 1: Write failing assertions**

Add assertions that ordinary grading evidence carries:

```python
assert payload["memory_lifecycle_stage"] == "short_term_learning_memory"
assert payload["quality"]["evidence_level"] == "L0_observed"
```

Add assertions that certified grading evidence carries:

```python
assert payload["memory_lifecycle_stage"] == "stable_learner_claim"
assert payload["quality"]["evidence_level"] == "L2_confirmed"
```

For V1 case event preview evidence, assert:

```python
assert payload["memory_lifecycle_stage"] == "short_term_learning_memory"
assert payload["claim_promotion_allowed"] is False
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/services/construction_grading/test_learning_evidence.py tests/services/construction_grading/test_audit_and_writeback.py -q
```

Expected: fail because `memory_lifecycle_stage` is absent.

- [ ] **Step 3: Implement lifecycle stage stamping**

In `build_learning_evidence_payload()`, after `quality` is computed:

```python
from deeptutor.services.learner_state.memory_lifecycle import lifecycle_stage_for_evidence_level

result["memory_lifecycle_stage"] = lifecycle_stage_for_evidence_level(
    result["quality"].get("evidence_level")
)
```

In `write_case_grading_event_learning_evidence()`, set:

```python
payload_json["memory_lifecycle_stage"] = "short_term_learning_memory"
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python -m pytest tests/services/construction_grading/test_learning_evidence.py tests/services/construction_grading/test_audit_and_writeback.py -q
```

Expected: pass.

### Task 3: Stamp Synthesis Claims With Lifecycle Stage

**Files:**
- Modify: `deeptutor/services/learner_state/learning_synthesis.py`
- Test: `tests/services/learner_state/test_learning_synthesis.py`

- [ ] **Step 1: Write failing assertions**

For one L0 event:

```python
assert projection["observed_candidates"][0]["memory_lifecycle_stage"] == "short_term_learning_memory"
```

For repeated L1:

```python
assert projection["weak_points"][0]["memory_lifecycle_stage"] == "stable_learner_claim"
```

For certified L2:

```python
assert projection["weak_points"][0]["memory_lifecycle_stage"] == "stable_learner_claim"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m pytest tests/services/learner_state/test_learning_synthesis.py -q
```

Expected: fail because claim objects lack lifecycle stage.

- [ ] **Step 3: Implement claim lifecycle stage**

In `_candidate()`, set:

```python
claim["memory_lifecycle_stage"] = lifecycle_stage_for_evidence_level(evidence_level)
```

In stale/improvement claim builders, preserve the same helper so reports do not infer stage from raw fields.

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
python -m pytest tests/services/learner_state/test_learning_synthesis.py -q
```

Expected: pass.

### Task 4: Demote Teacher-Final Naming To Compatibility

**Files:**
- Modify: `deeptutor/services/construction_grading/teacher_review_writeback.py`
- Modify: `deeptutor/services/learner_state/canonical_truth_policy.py`
- Test: `tests/services/construction_grading/test_teacher_review_writeback.py`
- Test: `tests/api/test_learning_brain_teacher_review_writeback.py`

- [ ] **Step 1: Write compatibility assertions**

Keep legacy fields present:

```python
assert signal["teacher_final_grading_result"]
```

But assert the primary path is:

```python
assert signal["final_adjudication_result"]
assert signal["trusted_adjudication"]
assert payload["quality"]["adjudication_authority"] == "trusted_adjudication"
assert "teacher_reviewed" not in payload["quality"]
```

For certified policy evidence, assert no teacher fields:

```python
assert "teacher_reviewed" not in payload["quality"]
assert payload["quality"]["adjudication_authority"] == "trusted_adjudication"
```

- [ ] **Step 2: Run tests**

Run:

```bash
python -m pytest tests/services/construction_grading/test_teacher_review_writeback.py tests/api/test_learning_brain_teacher_review_writeback.py tests/services/construction_grading/test_learning_evidence.py -q
```

Expected: pass after Task 2; if failing, fix only naming/quality projection, not write authority.

### Task 5: Make Canonical Write Gate Speak Lifecycle

**Files:**
- Modify: `deeptutor/services/learner_state/canonical_truth_policy.py`
- Modify: `deeptutor/services/learner_state/service.py`
- Test: `tests/services/learner_state/test_canonical_truth_policy.py`
- Test: `tests/services/learner_state/test_service.py`

- [ ] **Step 1: Assert stable claim requirement in policy tests**

Add cases:

```python
projection = {
    "weak_points": [{"memory_lifecycle_stage": "stable_learner_claim"}],
    "synthesis_run": {"trusted_adjudication": {...}},
}
```

Expected: broad production allows only when trusted adjudication passes.

Add L0-only case:

```python
projection = {
    "observed_candidates": [{"memory_lifecycle_stage": "short_term_learning_memory"}],
    "synthesis_run": {"trusted_adjudication": {}},
}
```

Expected: `trusted_adjudication_required`.

- [ ] **Step 2: Keep policy minimal**

Do not add a second gate if existing `trusted_adjudication` gate already blocks L0-only projections. Add only `promotion_decision.to_dict()` observability if missing.

- [ ] **Step 3: Run service tests**

Run:

```bash
python -m pytest tests/services/learner_state/test_canonical_truth_policy.py tests/services/learner_state/test_service.py -q
```

Expected: pass.

### Task 6: Product Read Model Labels

**Files:**
- Modify: `deeptutor/services/learner_state/learning_brain_read_model.py`
- Modify: `deeptutor/services/learner_state/learning_report_read_model.py`
- Test: `tests/services/learner_state/test_learning_brain_read_model.py`
- Test: `tests/services/learner_state/test_learning_report_read_model.py`

- [ ] **Step 1: Surface lifecycle labels**

Expose these labels:

```text
short_term_learning_memory -> 短期观察
stable_learner_claim -> 稳定学情判断
canonical_learner_truth -> 长期画像
```

- [ ] **Step 2: Assert visible read models carry lifecycle stage**

For weak points and observed candidates:

```python
assert item["memory_lifecycle_stage"]
assert item["memory_lifecycle_label"]
```

- [ ] **Step 3: Run read-model tests**

Run:

```bash
python -m pytest tests/services/learner_state/test_learning_brain_read_model.py tests/services/learner_state/test_learning_report_read_model.py -q
```

Expected: pass.

### Task 7: Runtime Smoke Evidence

**Files:**
- Modify or use existing runner under `scripts/` if available.
- Test: `tests/integration/test_luban_m32_grading_to_brain_waterproof_ws.py`

- [ ] **Step 1: Run a live-like local WS/TestClient grading turn**

Run:

```bash
python -m pytest tests/integration/test_luban_m32_grading_to_brain_waterproof_ws.py -q
```

Expected: grading metadata contains `construction_grading_result`; learning evidence preview remains non-canonical for ordinary L0.

- [ ] **Step 2: Add a certified-policy fixture smoke**

Use a hermetic grading payload with `certified_grading_policy.status="published"` and assert:

```python
quality.trusted_adjudication.source == "certified_grading_policy"
memory_lifecycle_stage == "stable_learner_claim"
synthesis_run.trusted_adjudication.source == "certified_grading_policy"
```

Expected: pass.

### Task 8: Test2 Cohort Closure

**Files:**
- Created: `scripts/run_learner_memory_lifecycle_test2_cohort_soak.py`
- Test: `tests/scripts/test_learner_memory_lifecycle_test2_cohort_soak.py`
- Evidence path: `artifacts/luban_grading_artifacts/learner_memory_lifecycle_<timestamp>/`

- [x] **Step 0: Add repeatable local artifact contract**

Run:

```bash
python scripts/run_learner_memory_lifecycle_test2_cohort_soak.py --mode local-core-store
```

Expected: local-only `LOCAL_ARTIFACT_GO` artifact with `evidence_scope=local_core_store_artifact_contract`, `local_canonical_write/readback` stage names, `remote_write_performed=false`, `remote_write_root_if_authorized=/root/deeptutor`, qa_ cohort allowed, non-cohort blocked, same `output_projection_hash` in projection/readback/read model.

- [x] **Step 1: Add remote test2 `/api/v1/ws` runner mode**

Run:

```bash
python scripts/run_learner_memory_lifecycle_test2_cohort_soak.py \
  --mode remote-test2-ws \
  --api-base-url https://test2.yousenjiaoyu.com \
  --auth-token "$DEEPTUTOR_TEST2_COHORT_AUTH_TOKEN" \
  --scenario construction-long-case \
  --remote-synthesis-ssh-host Aliyun-ECS-2 \
  --remote-synthesis-project-root /root/deeptutor \
  --remote-synthesis-container deeptutor
```

Expected: the runner fails closed with `REMOTE_AUTH_BLOCKED` unless the resolved identity is `qa_`/`operator_`. For canonical write/readback proof, the canonical authenticated `user_id` must also be cohort-scoped; external-auth QA usernames with UUID canonical ids can prove WS/evidence/report dry-run, but cannot prove G4 canonical write. When authenticated, the runner sends two real `/api/v1/ws` `start_turn` frames, requires `construction_grading_result` in both result metadata, triggers remote synthesis only when explicitly configured, then polls `learning-brain/projection` and `mobile/learning-report` for the same non-empty `output_projection_hash`.

- [ ] **Step 2: Deploy only after main is clean and released**

Required before remote write:

```bash
git status --short --branch
python scripts/check_contract_guard.py
python scripts/verify_runtime_assets.py
```

Expected: clean release worktree, contract guard pass, runtime assets pass.

- [x] **Step 3: Run test2 qa_/operator_ cohort proof**

Execute:

```text
real /api/v1/ws
-> grading
-> learning_evidence
-> L0 short-term memory for ordinary open-world
-> certified policy fixture
-> L2 stable claim
-> canonical write/readback for qa_/operator_
```

Expected evidence:

```text
learning_evidence event id
synthesis_run.output_projection_hash
canonical write decision
core-store readback
Learning Brain/report readback of same output_projection_hash
```

## Verification Matrix

| Scenario | Expected |
| --- | --- |
| Ordinary answer, one observation | L0, short-term memory, no canonical write |
| Same concept/error repeated | L1, stable claim, still gated before canonical |
| Certified grading policy | L2, trusted adjudication, eligible for canonical gate |
| Low confidence certified policy | stays L0/L1 only, no canonical promotion |
| Teacher final legacy path | still works as compatibility trusted adjudication |
| Real retest improvement | clears or decays prior claim only when non-preview and non-simulated |
| Product behavior click | evidence event only, never learner truth by itself |

## Acceptance Criteria

- Every learner signal has a lifecycle stage.
- No new learner memory store exists.
- Teacher-final fields are compatibility, not primary product language.
- `CertifiedGradingPolicy` is the preferred production scoring authority.
- L0 can power immediate UX but cannot write canonical truth alone.
- L1/L2 stable claims can be read by reports, PCP, NBA, and canonical gate.
- test2 cohort proof shows write/readback of canonical truth only for authorized user scope.

## Current Execution Slice

Tasks 1-8 are implemented locally. The follow-up hardens Task 7 producer authority, adds the Task 8 repeatable local artifact contract, closes the deployed test2 proof with `--mode remote-test2-ws` plus explicit remote synthesis trigger, and adds the production-quality follow-ups requested after test2: canonical taxonomy binding, evidence dedupe, auto synthesis trigger, and a real long-case scenario. A live test2 long-case cohort run has emitted `REMOTE_TEST2_WS_GO`. The next execution slice is release hygiene: narrow commit, review, merge/push, Aliyun redeploy if needed, then re-run `--scenario construction-long-case` from released `origin/main` to prove the shipped code still emits `REMOTE_TEST2_WS_GO`.
