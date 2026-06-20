# Luban No-Human v1.5 Textbook-Anchored Golden

- status: `textbook_anchored_auditable_no_human_v1_5_shadow`
- claim boundary: pure literal textbook-term points are auditable; residual points remain directional.
- not human IRR; not production gate.

## Fixture Summary

- cases: `20`
- samples: `100`
- point_labels: `485`
- deterministic_point_labels: `410`
- deterministic_ratio: `0.8454`
- residual_counts: `{"boundary": 75}`
- resolution_counts: `{"A": 410, "B": 75}`
- po_workload_ratio: `0.1546`
- external_expert_necessity_ratio: `0.0`
- R7a_PO_self_decision_queue: `75`
- R7b_external_expert_last_resort_queue: `0`
- unanchored_root_cause_counts: `{"genuinely_absent": 16, "rubric_is_paraphrase": 27, "junk_non_term": 5, "label_subterms_anchored_to_official_sources": 4, "non_textbook_cross_subject": 2, "official_answer_weak_repaired_to_content_markdown": 2}`
- independent_triage_counts: `{}`
- point_type_counts: `{"calculation": 17, "figure_label": 3, "non_textbook": 4, "text_term": 73}`
- anchor_source_counts: `{"calculation": 17, "exam_figure": 1, "non_textbook": 4, "official_answer_weak": 8, "textbook": 67}`
- textbook_anchor_point_ratio: `0.6907`

## v0 vs v1.5 Deterministic Subset

| arm | samples | mean abs delta v1.5 | mean abs delta v0 same subset |
|---|---:|---:|---:|
| artifact_first | 100 | 1.4259 | 1.4968 |
| baseline | 100 | 3.1619 | 3.3771 |
| rag | 100 | 3.1619 | 3.3771 |

## Three Golden Layers

| layer | anchor | can claim | cannot claim |
|---|---|---|---|
| v0 AI-ledger | AI construction ledger | directional grader-vs-construction-intent signal | accuracy / production gate |
| no-human v1.5 | textbook / standard exact spans | auditable literal-term subset metrics | human IRR / production gate |
| human v1 | double-blind expert IRR | production-gate evidence after reliability gate | unavailable until humans label |
