# QuestionGradingArtifact Registry v0 (2026-06-04)

## Canonical artifact dir (single publish authority)

- canonical: `artifacts/luban_grading_artifacts/registry_v0_20260604/`
- superseded: `artifacts/luban_consensus_gold/question_grading_registry_v0_20260604/` (kept only as a stale snapshot; never read/written as authority).

## Scope

- File-based publish gate. No DB, no production runtime, no kernel change, no RAG authority.
- Compiled from golden fixture + cached typed-policy packets; version `qga_v0_20260604`.

## Publish counts

- published: **18**
- draft: **1**  (Q20-1A413000)
- blocked: **1**  (Q15-NA)
- total scoring points: 97

## Source quality

- weak-source points (auto_certifiable=False): **28**
- auto-certifiable points: **69**
- non-auto-certifiable points: **28**
- missing-policy points: 0
- typed_policy coverage (typed policy_type points): 93/97

## Was any textbook source fabricated?

- **NO.** A `textbook` source_ref (verified=True) is emitted only from a real `evidence_policy.textbook_quote` + chunk_id. Points without a real textbook anchor are marked `source_status=missing_or_weak` and `auto_certifiable=False`. No anchor is invented to raise the published count.

## How the registry serves runtime

- `get_question_grading_artifact(question_id)` returns `ArtifactLookupResult(found, status, artifact, auto_certification_allowed)`.
- published -> `auto_certification_allowed=True` (may enter auto_certified flow).
- draft / blocked -> `auto_certification_allowed=False` (AI-Draft / high_risk only).
- unknown -> `found=False, status=artifact_missing` (no auto-grading).

## Next step (20 -> full bank)

- Two choices only: (1) extend the same projection to the full question bank, or (2) wire this registry gate into the AI-Draft runtime test chain. No new DB table either way.

## Top risks

- none flagged
