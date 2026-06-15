# 鲁班 KnowQL Implementation Ledger

> Ledger status vocabulary: `planned` / `stub` / `landed-local` / `runtime-consumed` / `shadow-verified` / `live-readback` / `production-authorized`.
> 本账本只记录 implementation truth；不把 shadow/live-readback 自动升级为 production default、official score 或 canonical learner truth 授权。

## 2026-06-15 Snapshot

| Work item | Status | Evidence | Boundary |
|---|---:|---|---|
| Phase A canonical typed object / PGO scoring object | `landed-local` | `luban_per_question_grading_object.v1`; `UNIFIED_GRADING_OBJECT_SCHEMA.md`; protected tests | 仍非 broad production default。 |
| Phase B verdict-coverage scorer | `shadow-verified` | `per_question_grading_judge.py`; `verdict_coverage_awarded_score`; `detect_over_credit`; 2026-06-13 live LLM A/B / RAG comparison | official total remains the only numeric score authority; per-point score remains non-canonical. |
| Phase C narrow KnowQL query executor `retrieve_rubric` | `runtime-consumed` | `m35_artifact_query.retrieve_rubric`; hash-pinned PGO runtime supply; `knowql_query.runtime_consumed=true` in live `/api/v1/ws` rows | Query executor is read-only and may not become a second grading policy engine. |
| G2 true-entry KnowQL shadow readback | `live-readback` | `tests/integration/test_luban_pgo_knowql_ws_readback.py`; live artifact `artifacts/luban_grading_artifacts/pgo_l1_live_shadow_ab_20260615T095041Z` shows B shadow effective 30/30 | `official_score_allowed=false`; `canonical_truth_written=false`; A arm has 0 PGO shadow. |
| G3 same-attempt PGO Grading-to-Brain preview readback | `live-readback` | Same final L1 artifact shows `pgo_g3_preview_readback_count=30`; local test `test_pgo_grading_to_brain_writeback.py` | Writes preview `learning_evidence`; does not promote canonical learner truth. |
| L1 live shadow performance A/B | `live-readback` | Final run `pgo_l1_live_shadow_ab_20260615T095041Z`: 30 pairs, A/B success 30/30, B p95 +76.945 ms / +2.0807%, fail-open 0, canonical writes 0, official score writes 0 | GO for qa/operator shadow performance only; no production default flip. |
| Grading shape ground gate hardening | `shadow-verified` | `ground_gate_contract_for_scoring`; PGO supply now carries `authority_source/span_hash`; `retrieve_rubric` fail-opens on ungrounded records; `tests/services/construction_grading` = 761 passed / 16 skipped; runtime supply verifier ok | Ungrounded points may be explanation-only; they cannot award/deduct score or enter PGO GBrain writeback. |
| Score-first grading shape | `landed-local` | `deep_question.grading_shape.score_first`; `tests/core/test_deep_question_case_rubric_v1.py`; L2 runner observes `score_first_observed_rate` | Current WS still emits one final `result`; sealed score block event is not yet a public stream event. |
| L2 true-entry three-arm runner v3 prereg | `live-readback` | `scripts/run_luban_knowql_nexus_l2_learning_ab.py`; `tests/scripts/test_luban_knowql_nexus_l2_learning_ab.py`; formal live artifact `knowql_nexus_l2_learning_ab_20260615T125634Z` | GO for qa/operator scripted same-session learning-efficiency shadow evidence only: 5 scenarios, loops 10, B2 PGO/KnowQL/G3 20/20, NBA 10/10, canonical/official/unsafe writes 0, primary effect `b2_outcome_miss_reduction_lift_vs_b1=5.0`. No production default, official score, published registry, or canonical learner truth authorization. |
| Learner truth promotion preview | `landed-local` | `build_learner_truth_promotion_preview(rows)` | Same-point weakness must improve on retest before a stable-claim candidate appears; `canonical_truth_written=false`. |
| Compiler feedback loop preview | `landed-local` | `build_compiler_feedback_loop(rows)` | High-dispute, low-confidence, teacher correction, common-miss signals become artifact work orders only; no artifact publish or production authorization. |

## 2026-06-15 L1 Run Ledger

| Artifact | Runner mode | Result | Key finding |
|---|---|---:|---|
| `pgo_l1_live_shadow_ab_20260615T091742Z` | 1-pair activation smoke | GO | B `shadow_status=ok`; KnowQL consumed; G3 preview readback present; writes 0. |
| `pgo_l1_live_shadow_ab_20260615T091817Z` | per-turn no delay | NO-GO | Triggered `/api/v1/ws` 1013 Too many requests after early rows; invalid for performance conclusion. |
| `pgo_l1_live_shadow_ab_20260615T092434Z` | single connection, no delay | NO-GO | Still 1013 after about 9 turns; turn-level limit, not merely connection count. |
| `pgo_l1_live_shadow_ab_20260615T092759Z` | single connection, 5s delay | NO-GO | Server closed long-lived WS after several turns; later rows reused closed socket. |
| `pgo_l1_live_shadow_ab_20260615T095041Z` | per-turn, 8s delay | **GO** | Valid L1: 30/30 pairs complete; B p95 latency +2.0807%; payload +2730 bytes avg; fail-open 0; canonical/official writes 0. |

## Production Authorization State

- `production-authorized`: none for broad default, official score, published registry, or canonical learner truth.
- Current authorized surface: qa/operator shadow readback on test2 with `LUBAN_CASE_RUBRIC_PGO_SHADOW_ENABLED=true` and request/config opt-in.
- Stop condition before any broader rollout: repeat L1 on a larger sample set and complete L2 only after #21 retest delta exists.

## 2026-06-15 L2 Runner Ledger

| Arm | Purpose | Current support | Learning-effect eligibility |
|---|---|---|---|
| A0 | Current baseline grading/NBA path | `/api/v1/ws` frame without PGO shadow | Yes |
| B1 | Nexus V1 scoring shape without KnowQL/PGO | `/api/v1/ws` frame with case-rubric V1 shape and no `grading_engine_pgo_shadow` | Yes, as shape-isolation ablation |
| B2 | Nexus V1 + KnowQL/PGO -> Grading-to-Brain preview -> NBA -> retest delta | `/api/v1/ws` frame with `grading_engine_pgo_shadow=true`; runner applies targeted retest only when PGO G3 emits NBA | Yes, integrated loop main arm |
| B3 | KnowQL query latency/payload microbenchmark | Direct `retrieve_rubric` benchmark with safe summary redaction | No |

Runner output contract:

- `raw_learning_rows.jsonl` contains A0/B1/B2 initial/retest WS rows, independent outcome-score deltas, server score-ratio deltas, PGO miss deltas, TTFT, first-result latency, streaming, sealed-block status, score-first observation, payload, and safety metadata.
- `raw_b3_microbenchmark_rows.jsonl` contains direct KnowQL query latency/payload only; B3 is excluded from learning-effect decision.
- `summary.json` separates `safety_status` from `effect_status`; any canonical truth write, official score write, A0 PGO contamination, B1 PGO contamination, B2 KnowQL/G3 missing, B2 NBA missing, row error, B3 failure, or prereg latency/payload guardrail breach is `L2_SAFETY_NO_GO`.
- Formal prereg qa/operator live evidence is present in `knowql_nexus_l2_learning_ab_20260615T125634Z`; real learner cohort A/B remains a separate authorization/evaluation stage.

### 2026-06-15 L2 Smoke Runs

| Artifact | Result | Key finding |
|---|---|---|
| `knowql_nexus_l2_learning_ab_20260615T104141Z` | NO-GO / not evaluable | Runner sent non-allowlisted L2 config fields; every WS turn failed with `Unable to start turn`; B3 direct KnowQL still 5/5. Preserved as negative transport evidence. |
| `knowql_nexus_l2_learning_ab_20260615T104410Z` | NO-GO / neutral | WS succeeded after config fix; safety GO, but effect gate only considered legacy score delta, so PGO miss reduction signal was not counted. |
| `knowql_nexus_l2_learning_ab_20260615T104707Z` | **GO / smoke positive** | Old arm mapping: A0/B1/B2 WS success 2/2 each; B1/B2 PGO shadow effective 2/2 each; KnowQL consumed 2/2 each; G3 preview readback 2/2 each; canonical/official/unsafe writes 0. B1 PGO miss reduction lift vs B2 = +1.0; legacy score delta lift = 0.0; B3 direct KnowQL 5/5, p95 10.853 ms, payload 671 bytes. |
| `knowql_nexus_l2_learning_ab_20260615T113738Z` | NO-GO / not evaluable | v2 first attempt sent non-allowlisted `ab_arm/runtime_mode` config; all WS turns failed fast; B3 direct KnowQL 5/5. Preserved as negative transport evidence. |
| `knowql_nexus_l2_learning_ab_20260615T113916Z` | NO-GO / not evaluable | Removed `ab_arm/runtime_mode`; A0 succeeded 2/2 and proved score-first/V1 already default on test2, but explicit `grading_engine_case_rubric_v1` still caused B1/B2 start failures; B3 5/5. |
| `knowql_nexus_l2_learning_ab_20260615T114120Z` | NO-GO / B2 closure missing | Only sent historical PGO flag. A0/B1/B2 WS all succeeded 2/2; B3 5/5; canonical/official/unsafe writes 0; TTFT/streaming/score-first captured. B2 PGO shadow effective 0/2, KnowQL runtime consumed 0/2, PGO-G3 preview 0/2, so integrated KnowQL/GBrain loop was not exercised on current test2. |
| `knowql_nexus_l2_learning_ab_20260615T122930Z` | NO-GO / safety GO / effect neutral | A0/B1/B2 WS one-loop smoke succeeded; B2 PGO shadow effective 2/2, KnowQL runtime consumed 2/2, PGO-G3 preview 2/2, NBA intervention 1/1; canonical/official/unsafe writes 0. This closes B2 readback as a blocker, but it is not formal L2 evidence because sample/loops were not preregistered/powered and effect was neutral. |
| `knowql_nexus_l2_learning_ab_20260615T125634Z` | **GO / safety GO / effect positive** | Formal prereg run: 60 WS learning rows + 30 B3 rows; completed loops A0/B1/B2=10/10/10; B2 PGO/KnowQL/G3 readback 20/20; NBA 10/10; canonical/official/unsafe writes 0; primary effect `b2_outcome_miss_reduction_lift_vs_b1=5.0`; B2 retest delta lift vs B1/A0 `+0.746112`; B2 p95 latency +49.752505% vs B1, payload +10.001534%; B3 p95 11.117 ms. |

Interpretation: this proves the new B2 integrated Nexus/KnowQL/GBrain/NBA loop can be observed through the real test2 entry with write safety intact and beats A0/B1 under the preregistered scripted same-session retest design. It still does not prove product-level learning efficiency for uncontrolled real learners; the next stage is a separately preregistered real learner/authorized QA cohort A/B, or compiler/NBA refinement using the work-order evidence.
