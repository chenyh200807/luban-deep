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
| L2 learning-efficiency A/B | `planned` | Blocked until #21 retest delta path exists and can measure PGO weakness -> NextBestAction -> retest delta | Must remain `canonical_truth_written=false` until separate canonical authorization. |

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
