# Asset Gap Map v1

- Generated at: `2026-07-16T14:54:49+08:00`
- Authority: gap map only; not runtime supply, not official score authority.
- Open gap items: **9**
- P1 gap items: **5**

## Action Queues

| Queue | Count | Why it matters |
|---|---:|---|
| `pdf_p1_compile_or_map` | 21 | PDF full text/chunk or PDF->JSON map is still missing. |
| `json_source_claim_review_backlog` | 383 | JSON source claims are indexed but not reviewed. |
| `exam_content_gap` | 139 | Exam JSON still has taxonomy, analysis, and score gaps. |
| `pdf_p2_verify_provenance` | 39 | Candidate derivatives exist but need one-to-one source proof. |
| `okf_case_level_alignment_backfill` | 16 | OKF cases are source-aligned only at case level, not sub-question level. |
| `runtime_published_pointer_consumer_evidence` | 4 | Published pointers need true consumer read evidence. |
| `runtime_policy_conflict_live_reader` | 1 | Runtime reader and pointer policy disagree. |
| `runtime_blocked_or_candidate_pointer_review` | 12 | Candidate/blocked runtime pointers cannot become defaults without signing. |

## Gap Items

| Gap | Priority | Area | Count | Blocks |
|---|---|---|---:|---|
| `exam_content_gap` | P1 | exam_source | 139 | signed_case_rubric_release, deep_exam_context_quality |
| `okf_candidate_not_signed_release` | P1 | okf_release | 25 | official_score_authority, runtime_default_case_grading |
| `okf_case_level_alignment_backfill` | P1 | okf_source_alignment | 16 | signed_case_rubric_release, official_score_candidate_gate |
| `pdf_p1_compile_or_map` | P1 | pdf_source | 21 | full_okf_runtime_release, complete_pdf_context_recall |
| `runtime_policy_conflict_live_reader` | P1 | runtime_supply | 1 | single_runtime_authority, official_score_readiness_claim |
| `json_source_claim_review_gap` | P2 | json_source | 383 | signed_source_lineage, source_laundering_prevention |
| `pdf_p2_verify_provenance` | P2 | pdf_source | 39 | signed_source_lineage, source_laundering_prevention |
| `runtime_candidate_or_blocked_pointers` | P2 | runtime_supply | 12 | runtime_default_claim, single_authority_runtime_supply |
| `runtime_published_pointer_consumer_evidence` | P2 | runtime_supply | 4 | runtime_readiness_claim, production_consumer_claim |

## Guardrails

- This map may route work to compiler/review skills, but it cannot sign release artifacts.
- Candidate OKF scope remains candidate-only until deterministic validators and owner signing pass.
- Published runtime pointers still require consumer-level evidence before production readiness claims.
- PDF derivative links remain candidate evidence until provenance is verified.
