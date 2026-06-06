# M20 Artifact Version Supersession Matrix

| Artifact | Role in M20 | Supersession status |
|---|---|---|
| M17A runtime_llm_adjudicator | first real `/api/v1/ws` LLM adjudication evidence | retained as baseline |
| M17B/M18 runtime_llm_ai_council_scaleout | scaleout, validator downgrade, council disagreement, artifact feedback inputs | superseded only by candidate delta ledger, not mutated |
| M17C deepseek calibration | live-call gap closure and validator recheck inputs | retained as safety evidence |
| M18C/M18D Learning Brain proof | claim lifecycle and real retest proof inputs | retained; M20 adds dry-run mapping deltas only |
| M13D teacher review ops | review queue and operator feedback input | retained; M20 groups gaps into work orders |
| M20 release_candidate_delta | signed candidate delta package | version `m20_20260604_delta_v1`, hash `0a5d134336a22fd5ebe930e13705cde6af469662721cb5a8d7131c226c18d5e5` |

Rollback pointer: `rollback_to_m17c_m18d_m13d_input_artifacts_no_runtime_change`.

M20 does not alter formal registry, runtime default, production DB, or canonical learner truth.
