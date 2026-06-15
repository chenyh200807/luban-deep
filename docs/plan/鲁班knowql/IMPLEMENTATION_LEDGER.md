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
| L3 real/cohort learning A/B | `live-readback` | `scripts/run_luban_knowql_nexus_l3_cohort_ab.py`; `tests/scripts/test_luban_knowql_nexus_l3_cohort_ab.py`; test2 artifact `knowql_nexus_l3_cohort_ab_20260615T140840Z` after deploy SHA `16dbb13dcc2be1ed5ac40feec7682283fd098620` | GO for authorized QA/operator cohort only: A0/B1/B2 each 5 distinct learners, 30 WS rows, B2 PGO/KnowQL/G3 10/10, NBA 5/5, primary lift `5.0`, B2 p95 latency -44.902579% vs B1, payload +9.982498%; canonical/official/unsafe writes 0. No real-student or production learner claim. |
| L4 production authorization readiness package | `landed-local` | `scripts/run_luban_knowql_nexus_l4_authorization_readiness.py`; `tests/scripts/test_luban_knowql_nexus_l4_authorization_readiness.py`; local artifact `knowql_nexus_l4_authorization_readiness_20260615T143645Z` with `summary.json` + `negative_evidence.jsonl` | Consumes L1/L2/L3 summaries and reports `L4_LIVE_READBACK_READY`, but verdict remains `BLOCKED_FOR_PRODUCTION_AUTHORIZATION`: real-student cohort authorization, privacy consent boundary, sample-size plan, production default authorization, official score authorization, published registry authorization, and canonical truth authorization are all missing. No runtime flag flip, no remote write, no canonical/official write. |
| L4.1 authorization readiness hardening | `landed-local` | `scripts/run_luban_knowql_nexus_l4_authorization_readiness.py`; artifact `knowql_nexus_l4_1_authorization_readiness_20260615T152027Z` with `source_manifest.json`, `deployment_probe.json`, `negative_evidence.jsonl` | Consumes PGO supply verification, Stage5 canary, G4 canonical policy verification, current deployment lineage, and L2/L3 negative runs. Live-readback remains ready, but production remains blocked: Stage5 human-gold over-credit blocker is preserved, host/container SHA is `bda905590831c697df74ec1d97c80729f7350606`, health/ready pass, canonical/official/production/unsafe writes 0. |
| Stage5 human-gold over-credit hardening | `shadow-verified` | `scripts/run_luban_pgo_stage5_canary_gate.py`; artifact `knowql_nexus_stage5_human_boundary_repair_20260615T154400Z/stage5_canary_gate_report.json`; tests `test_luban_pgo_stage5_canary_gate.py` | Stage5 blocks at source when human-boundary over-credit exists instead of relying on L4 to reinterpret a GO report. The first blocker was two Q4 human-boundary pairs (`S4`, `S5`) over-crediting against po_slice human gold. |
| Runtime penalty/list-shape consumption repair | `runtime-consumed` | `rubric_grader_v1._grade_with_pgo_coverage`; `case_rubric_scored_pgo.json` content hash `7e403e05c56c3afc25d02d23c3db66888522ad7b859f81c1c7d051c2090f22f0`; artifact `knowql_nexus_runtime_penalty_list_shape_repair_20260615T164013Z/human_boundary_repair.json`; tests `test_pgo_coverage_consumes_multi_answer_penalty_and_list_shape_weights` / `test_pgo_stage5_human_boundary_repair_evidence_is_built_from_runtime_scorer` | Q4 `2023::EXAM_1A434000_P0010_02::E0` runtime supply records now carry `multi_answer_no_score` + list total-items constraints into the actual PGO coverage scorer. Repair evidence consumes tracked runtime supply (`tracked_runtime_supply=true`), maps S4 `7.0 -> 3.0`, maps S5 `1.167 -> 0.0`, applies `penalty_rules_applied=["multi_answer_no_score"]`, and keeps canonical/official writes 0. |
| Stage5 repaired canary gate | `shadow-verified` | `knowql_nexus_runtime_penalty_list_shape_repair_20260615T164013Z/stage5_canary_gate_report.json`; `pgo_supply_verification.json`; `source_manifest.json`; `negative_evidence.jsonl` | Stage5 returns `qa_operator_canary_go` with blockers `[]`; repair gate records original blocker true and resolved true. L4 re-run has hardening passed 4/4 and `L4_LIVE_READBACK_READY`, but production remains `BLOCKED_FOR_PRODUCTION_AUTHORIZATION` because consent/cohort authorization, production default authorization, official score authorization, published registry authorization, and canonical truth authorization remain missing. |
| L5 production default gate | `landed-local` | `scripts/run_luban_knowql_nexus_l5_production_default_gate.py`; `tests/scripts/test_luban_knowql_nexus_l5_blocked_gates.py`; artifact `knowql_nexus_l4_1_authorization_readiness_20260615T152027Z/l5_production_default_gate.json` | Verdict `BLOCKED_PENDING_SIGNED_AUTHORIZATION`; blockers include signed authorization missing plus L4/Stage5 blockers. Env mutation, production default flip, published registry write, official score, remote write all remain false. |
| L5 canonical learner truth gate | `landed-local` | `scripts/run_luban_knowql_nexus_l5_canonical_truth_gate.py`; `tests/scripts/test_luban_knowql_nexus_l5_blocked_gates.py`; artifact `knowql_nexus_l4_1_authorization_readiness_20260615T152027Z/l5_canonical_truth_gate.json` | Verdict `BLOCKED_PENDING_SIGNED_AUTHORIZATION`; blockers include signed canonical authorization missing, same-point real retest proof missing, teacher-final/certified policy proof missing, stable learner claim missing, and L4 production authorization blocked. Canonical learner truth write remains false. |
| L5 signed authorization package draft | `landed-local` | `scripts/run_luban_knowql_nexus_l5_signed_authorization_package.py`; `tests/scripts/test_luban_knowql_nexus_l5_signed_authorization_package.py`; artifact `knowql_nexus_runtime_penalty_list_shape_repair_20260615T164013Z/signed_authorization_package.json` | Generates consented-pilot, production-default, and canonical-truth authorization forms, but keeps all unsigned and no-write. Current verdict `READY_FOR_HUMAN_SIGNATURE`; this means forms are ready to review, not that any runtime authority has been granted. |
| L5.1 consented pilot gate | `landed-local` | `scripts/run_luban_knowql_nexus_l5_consented_pilot_gate.py`; `tests/scripts/test_luban_knowql_nexus_l5_consented_pilot_gate.py`; artifact `knowql_nexus_runtime_penalty_list_shape_repair_20260615T164013Z/l5_consented_pilot_gate.json` | Splits the next valid real-student step from production default/canonical truth. Current verdict `BLOCKED_PENDING_CONSENTED_PILOT_AUTHORIZATION`: real-student cohort evidence, privacy consent boundary, sample-size plan, and signed consented-pilot authorization are missing. Production default, official score, published registry, canonical truth, and remote write remain false. |
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
- L4 readiness artifact `knowql_nexus_l4_authorization_readiness_20260615T143645Z` confirms live-readback is ready (`live_readback_passed_count=3/3`) while production authorization is blocked (`production_blocker_count=7`, safety violations 0, canonical/official/production/unsafe writes 0).
- L4.1 hardening artifact `knowql_nexus_l4_1_authorization_readiness_20260615T152027Z` confirms source/deployment lineage and negative evidence are captured; it intentionally preserved the Stage5 `stage5_human_gold_over_credit_blocker` before runtime repair.
- Runtime repair artifact `knowql_nexus_runtime_penalty_list_shape_repair_20260615T164013Z` consumes tracked PGO runtime supply and the actual coverage scorer for Q4 `multi_answer_no_score` + list-shape weights. Stage5 now returns `qa_operator_canary_go`; L4 hardening passes 4/4, live-readback remains ready, and canonical/official/production/unsafe writes remain 0.
- L5 signed authorization package is prepared but unsigned: `l5_production_default_gate.json` and `l5_canonical_truth_gate.json` both remain `BLOCKED_PENDING_SIGNED_AUTHORIZATION`. This is now a governance/signature blocker, not the previous Stage5 human-boundary over-credit blocker.
- Stop condition before any broader rollout: L3 is positive only for authorized QA/operator cohort. Real production learner A/B still needs separate consent/cohort source, privacy boundary, sample-size plan, and explicit authorization packages before any broad default, official score, published registry, or learner-truth promotion.

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

## 2026-06-15 L3 Real/Cohort Runner Ledger

L3 upgrades L2 from repeated scripted loops to distinct learner subjects. It still uses authorized QA/operator identities on test2, so the result is cohort-shaped live evidence, not a production real-student claim.

| Arm | Subjects | Runtime | Learning-effect eligibility |
|---|---:|---|---|
| A0 | 5 | Original `/api/v1/ws` baseline | Yes |
| B1 | 5 | Nexus V1 shape without KnowQL/PGO/GBrain | Yes, shape-isolation ablation |
| B2 | 5 | Nexus V1 + KnowQL/PGO + Grading-to-Brain preview + NBA targeted retest | Yes, integrated-loop main arm |
| B3 | n/a | Direct `retrieve_rubric` microbenchmark, 30 iterations | No |

### 2026-06-15 L3 Runs

| Artifact | Result | Key finding |
|---|---|---|
| `knowql_nexus_l3_cohort_ab_20260615T132850Z` | NO-GO / not evaluable | Auth/login failures and one WS 502; preserved as negative true-entry evidence. |
| `knowql_nexus_l3_cohort_ab_20260615T133511Z` | NO-GO / B2 cohort gate missing | 15 subjects registered, A0/B1/B2 mostly succeeded, but B2 PGO/KnowQL/G3/NBA readback was 0/10 because server-authenticated UUID was not being projected to the external-auth `auth_*` member/username cohort identity. |
| `knowql_nexus_l3_cohort_ab_20260615T140840Z` | **GO / safety GO / effect positive** | Deployed SHA `16dbb13dcc2be1ed5ac40feec7682283fd098620`; A0/B1/B2 subjects 5/5/5, distinct learners 15/15, 30 WS rows; B2 PGO shadow 10/10, KnowQL runtime consumed 10/10, PGO-G3 preview 10/10, NBA 5/5; canonical/official/unsafe writes 0; primary lift `b2_real_cohort_outcome_miss_reduction_lift_vs_b1=5.0`; B2 p95 latency -44.902579% vs B1, payload +9.982498%; B3 p95 11.378 ms. |

L3 implementation note: `MemberConsoleService.get_auth_identity_projection()` is now a side-effect-free server-side projection from authenticated canonical UUID to an existing external-auth member (`auth_<uuid-prefix>`, `external_auth_user_id`, or alias). The runner records non-secret `auth_user_id/auth_mode/auth_attempt` per row so future cohort-gate failures can be diagnosed without client-supplied identity authority.

Interpretation: L3 proves the integrated Nexus/KnowQL/GBrain/NBA loop can improve same-cohort retest outcomes through the real test2 `/api/v1/ws` entry while preserving write safety. It does **not** authorize real-student claims, broad production default, official scoring, published registry, or canonical learner truth.

## 2026-06-15 L4 Authorization Readiness Ledger

L4 is a no-write decision package, not a runtime executor. It consumes the already-produced L1/L2/L3 summaries and separates "live readback ready" from "production authorized".

| Artifact | Result | Key finding |
|---|---|---|
| `knowql_nexus_l4_authorization_readiness_20260615T143645Z` | `BLOCKED_FOR_PRODUCTION_AUTHORIZATION` / live-readback ready | L1/L2/L3 gates passed 3/3; `canonical_truth_write_count=0`, `official_score_write_count=0`, `production_write_count=0`, `unsafe_write_signal_count=0`; production blockers are `real_student_cohort_authorization_missing`, `privacy_consent_boundary_missing`, `sample_size_plan_missing`, `production_default_authorization_missing`, `official_score_authorization_missing`, `published_registry_authorization_missing`, `canonical_truth_authorization_missing`. |

Allowed claim after L4: KnowQL/Nexus/GBrain/NBA has QA/operator live-readback evidence through `/api/v1/ws` and can enter a production authorization review.

Still forbidden after L4: real-student efficacy claim, broad production default, official score, published registry, canonical learner truth write, remote write, or any single switch that bundles these authorities together.

## 2026-06-15 L4.1 / L5 Hardening Ledger

L4.1 extends L4 from "summary-only readiness" into an evidence-locked decision package. It still performs no writes and does not authorize production.

| Artifact | Result | Key finding |
|---|---|---|
| `knowql_nexus_l4_1_authorization_readiness_20260615T152027Z` | `BLOCKED_FOR_PRODUCTION_AUTHORIZATION` / live-readback ready | Source manifest captures L1/L2/L3, PGO supply verification, Stage5 canary, G4 policy verification, and 8 L2/L3 negative summary inputs. Deployment probe records host/container SHA both `bda905590831c697df74ec1d97c80729f7350606`, `/healthz` 200, `/readyz` ready. Stage5 fails hardening due `stage5_human_gold_over_credit_blocker`; production blockers increase to 9. |
| `l5_production_default_gate.json` | `BLOCKED_PENDING_SIGNED_AUTHORIZATION` | Blocks on signed production-default authorization missing, L4 production authorization blocked, Stage5 canary not ready, Stage5 human-gold over-credit blocker, official score authorization missing, published registry authorization missing, production default authorization missing. |
| `l5_canonical_truth_gate.json` | `BLOCKED_PENDING_SIGNED_AUTHORIZATION` | Blocks on signed canonical authorization missing, same-point real retest proof missing, teacher-final/certified policy missing, stable learner claim missing, L4 production authorization blocked, canonical truth authorization missing, real-student cohort authorization missing. |

Allowed claim after L4.1: the QA/operator live-readback evidence package is now source/deployment-versioned and includes preserved negative runs.

Still forbidden after L4.1/L5 blocked gates: production default flip, env mutation, published registry write, official score, canonical learner truth write, learner memory event write, read-model write, DB/remote write.

## 2026-06-15 Stage5 Human-Boundary Hardening

The Stage5 gate now treats human-boundary over-credit as a first-class blocker. This corrects the previous ambiguity where Stage5 could report `qa_operator_canary_go` while L4 later preserved `stage5_human_gold_over_credit_blocker`.

| Artifact | Result | Key finding |
|---|---|---|
| `knowql_nexus_stage5_human_boundary_repair_20260615T154400Z/stage5_canary_gate_report.json` | `blocked` | Runtime supply verifier passes and scaled double gate passes, but human-boundary over-credit remains: new=2, legacy=0. Repair evidence is missing, so `stage5_human_gold_over_credit_blocker` is active. |
| `authorization_readiness.json` | `BLOCKED_FOR_PRODUCTION_AUTHORIZATION` / live-readback ready | L1/L2/L3 live-readback remains 3/3; hardening is 3/4; production blockers remain 9; canonical/official/production/unsafe writes 0. |
| `signed_authorization_package.json` | `BLOCKED_BEFORE_SIGNATURE` | Production-default and canonical-truth forms are generated as unsigned no-write drafts, but package cannot enter signature capture while Stage5 canary is not ready. |

Root-cause note: the two blocking pairs are concentrated in `Q4-1A434000-罚则`, whose official human-gold packet contains a case-level "2 不妥，多答不得分" penalty. PGO supply now preserves `case_shape_constraints` from the factory candidate for future runtime consumption, but the current runtime scoring path still needs a real penalty/list-shape consumption gate before Stage5 can be resolved.

## 2026-06-16 Runtime Penalty/List-Shape Repair

This closes the Stage5 human-boundary blocker by moving Q4 penalty/list-shape constraints into the actual runtime PGO coverage scorer rather than patching the Stage5 report.

| Artifact | Result | Key finding |
|---|---|---|
| `knowql_nexus_runtime_penalty_list_shape_repair_20260615T164013Z/human_boundary_repair.json` | `resolved` | Consumes tracked runtime supply qid `2023::EXAM_1A434000_P0010_02::E0` with content hash `7e403e05c56c3afc25d02d23c3db66888522ad7b859f81c1c7d051c2090f22f0`; S4 repaired score `3.0`, S5 repaired score `0.0`, `tracked_runtime_supply=true`, `multi_answer_no_score=true`, `list_shape_weights=true`, canonical truth write false. |
| `stage5_canary_gate_report.json` | `qa_operator_canary_go` | Stage5 blockers `[]`; original human-boundary blocker recorded as true, repair gate resolved it with covered original pair count 2 and after-repair over-credit pairs new=0 / legacy=0. |
| `authorization_readiness.json` | `BLOCKED_FOR_PRODUCTION_AUTHORIZATION` / live-readback ready | L1/L2/L3 passed 3/3; hardening passed 4/4; safety violations 0; canonical/official/production/unsafe writes 0; production blockers now reduce to the seven expected governance blockers. |
| `l5_production_default_gate.json` / `l5_canonical_truth_gate.json` | `BLOCKED_PENDING_SIGNED_AUTHORIZATION` | No env mutation, no production default flip, no official score write, no published registry write, no canonical learner truth write, no remote write. Signed authorization and consented real-student proof remain outside this repair. |
| `l5_consented_pilot_gate.json` | `BLOCKED_PENDING_CONSENTED_PILOT_AUTHORIZATION` | Consent/pilot gate is now separated from production default: it requires real-student cohort evidence, privacy consent boundary, sample-size plan, and a signed consented-pilot authorization. It still blocks production default, official score, published registry, canonical truth, and remote write. |

Allowed claim after this repair: QA/operator Stage5 canary is again credible because human-boundary repair evidence is sourced from the tracked PGO runtime supply and actual coverage scorer.

Still forbidden: broad production default, official score, published registry, real-student efficacy claim, canonical learner truth promotion, learner memory write, DB/remote write.
