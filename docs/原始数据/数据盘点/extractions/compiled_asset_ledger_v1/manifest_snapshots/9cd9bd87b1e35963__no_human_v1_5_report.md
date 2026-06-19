# Luban No-Human v1.5 Textbook-Anchored Golden

- status: `textbook_anchored_auditable_no_human_v1_5_shadow`
- claim boundary: pure literal textbook-term points are auditable; residual points remain directional.
- not human IRR; not production gate.

## Fixture Summary

- cases: `20`
- samples: `100`
- point_labels: `485`
- deterministic_point_labels: `470`
- deterministic_ratio: `0.9691`
- residual_counts: `{"boundary": 15}`
- resolution_counts: `{"A": 470, "B": 15}`
- po_workload_ratio: `0.0309`
- external_expert_necessity_ratio: `0.0`
- R7a_PO_self_decision_queue: `15`
- R7b_external_expert_last_resort_queue: `0`
- unanchored_root_cause_counts: `{"genuinely_absent": 19, "rubric_is_paraphrase": 28, "label_subterms_anchored_to_official_sources": 20, "junk_non_term": 2}`
- independent_triage_counts: `{}`

## v0 vs v1.5 Deterministic Subset

| arm | samples | mean abs delta v1.5 | mean abs delta v0 same subset |
|---|---:|---:|---:|
| artifact_first | 100 | 1.0738 | 1.7671 |
| baseline | 100 | 3.2572 | 3.9321 |
| rag | 100 | 3.2572 | 3.9321 |

## Three Golden Layers

| layer | anchor | can claim | cannot claim |
|---|---|---|---|
| v0 AI-ledger | AI construction ledger | directional grader-vs-construction-intent signal | accuracy / production gate |
| no-human v1.5 | textbook / standard exact spans | auditable literal-term subset metrics | human IRR / production gate |
| human v1 | double-blind expert IRR | production-gate evidence after reliability gate | unavailable until humans label |
