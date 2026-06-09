# M35 Scoring Artifact Production Decision

Date: 2026-06-09

Status: NO-GO

Scope: M35 Nexus-like scoring artifact engine, shadow / release-candidate only.

## Decision

M35 must remain `shadow` / `release_candidate` only. Do not enable production default, published registry, canonical learner truth write, remote deployment, or user-facing quality claims.

The implementation has enough evidence to continue QA/operator shadow drills, but it does not have governed labels, live provider quality evidence, manual spot-check approval, or source-validity proof needed for WEAK-GO or GO.

## Evidence Summary

| Gate | Result | Evidence |
| --- | --- | --- |
| Sample size | 20 questions / 100 answers | `tests/fixtures/luban_m35_case_scoring/student_answers.jsonl` |
| Label authority | `generated_self_label=100` | `/tmp/m35_label_audit_task9.json` |
| Verdict ceiling | `SHAPE_ONLY` | label audit: `quality_claim_allowed=false`, `poc_go_allowed=false`, `weak_go_allowed=false` |
| Shape evaluation | NO-GO | `/tmp/m35_ab_shape_parent.json`, `quality_claim_allowed=false` |
| Cached replay evaluation | NO-GO | `/tmp/m35_ab_cached_parent.json`, `quality_claim_allowed=false` |
| Live provider sample tier | NO-GO | `/tmp/m35_ab_live_parent.json`, `provider_call_count=0`; tier shape exercised only |
| WS shadow route | Pass as shadow only | `/api/v1/ws` integration tests pass; no new WebSocket route |
| Release gate artifact | NO-GO | `artifacts/luban_grading_artifacts/m35_scoring_artifact_gate/go_no_go_m35.json` |
| Learning Brain readback | Shape proof only | point evidence can project to read model; `canonical_truth_written=false` |
| Safety invariants | Pass | production/db/remote/RAG/provider/published/canonical writes all zero |

## Metrics

The current fixture cannot support precision/recall, score MAE, blind answer quality, or product-readiness claims because all 100 labels are generated/self labels.

| Metric | Current result | Production threshold | Decision |
| --- | ---: | ---: | --- |
| point precision | not claimable | >= 0.90 | NO-GO |
| point recall | not claimable | >= 0.90 | NO-GO |
| score MAE | not claimable | <= 1.0 or 20% better than baseline | NO-GO |
| source validity | 0.71134 shape/cached; 0.866667 live-tier sample | >= 0.95 | NO-GO |
| hallucinated scoring points | 0 in shape runner | 0 | not sufficient alone |
| RAG chunk as answer key | 0 | 0 | pass |
| wrong path rate | 0.0 in shape runner | <= 0.03 | shape-only |
| fail-open rate | 0.0 in shape runner | must stay unpolluted | shape-only |
| token / latency delta | 0 / not exercised | report absolute and delta | pending live sample |
| prior red failure comparison | not beaten | beat 0.5267 point-hit agreement / 4.6091 MAE | NO-GO |

## Manual Review

Manual teacher / PO spot-check is absent. Because the fixture is `generated_self_label`, there is no governed human truth source to validate point hits, score deltas, high-risk cases, or source conflicts.

## Learning Brain Readback Boundary

Task 6 proves that M35 point-level evidence can preserve:

- `artifact_version`
- `point_id`
- `match_status`
- `awarded_score`
- `error_code` / `mistake_type` / `miss_reason`
- `evidence_span`
- `source_refs`

It also proves readback into the existing learner-state projection without adding a second learner memory. This is still a shape/readback proof, not a production learner-truth write. `canonical_truth_written=false` remains mandatory.

## Safety Invariants

The current M35 package did not perform:

- production DB writes
- remote / Aliyun writes
- published registry writes
- canonical learner truth writes
- provider calls in release gate
- RAG lookups for answer-key construction
- WebSocket route creation
- legacy `construction_grading_result` replacement

`official_score_allowed=false` remains mandatory for every M35 shadow payload.

## Remaining Blockers

1. Replace generated/self labels with governed teacher or PO labels.
2. Run a real `live_provider_sample` with provider calls, latency, cost, fail-open behavior, and quality metrics.
3. Complete manual teacher/PO spot-check for high-risk and disputed cases.
4. Raise source validity to >= 0.95 with source-level audit.
5. Prove artifact-first beats the prior red baseline: `0.5267` point-hit agreement and `4.6091` score MAE.
6. Produce a governed release package that explicitly authorizes any broader cohort.

## Allowed Rollout

Allowed now:

- QA/operator shadow drill only.
- `shape_stub` and cached replay artifacts for contract/safety testing.
- Append-only `luban_m35_scoring_artifact_shadow` metadata for server-controlled `qa_`, `test_`, or `operator_` cohorts.

Not allowed now:

- real-student default
- public quality claim
- official score
- production broad default
- published registry
- canonical learner truth write
- Aliyun / remote deployment

Rollback switch:

```bash
LUBAN_M35_ARTIFACT_SHADOW_ENABLED=false
```

## Stop Conditions

Stop immediately if any of these appear:

- `official_score_allowed=true` without governed registry authorization
- `canonical_truth_written=true`
- production/db/remote write count above zero
- provider/RAG activity hidden inside shape gate
- client config self-authorizes a real student into M35 shadow
- shadow block replaces or mutates legacy grading result

## Next Decision Point

Reopen WEAK-GO consideration only after a governed label pack and live provider sample exist. Reopen GO consideration only after WEAK-GO evidence, manual review, source validity, capacity gate, governance gate, and Grading-to-Brain live readback closure all pass.
