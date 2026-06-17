# M19C Observability Stop Conditions

Immediate rollback if any of these is observed:

- false_positive > 0
- bad_certified > 0
- source_mismatch > 0
- production_write_count > 0
- canonical_truth_written == true
- non_cohort_blocked != true
- kill_switch_works != true
- fallback provider fail-closed path fails
- legacy_equal_rate < 1.0
- p95 latency exceeds the operator-defined M19D soak SLO

Rollback controls:

- Set `LUBAN_V1_LLM_ADJUDICATOR_LIMITED_DEFAULT_ENABLED=false`
- Or set `LUBAN_V1_LLM_ADJUDICATOR_ENABLED=false`
- Or remove `grading_engine_v1_llm_adjudication` request flag for explicit QA paths
- Or make registry unavailable/fail-closed, which must preserve legacy-only behavior for default path
