# FINDING Registry v1 Candidate Compile Dry-Run M6 20260604 (M5R overlay)

1. M5 counts match exactly: YES. M5 authority input is 34 questions / 150 points, with 25 auto-certifiable, 112 official-weak review, and 13 rewrite-needed points.
2. Formal Registry v1 generated: NO. `formal_registry_emitted=false`; no `registry_v1.json`, `question_grading_registry_v1.json`, or formal `question_grading_artifacts_v1.jsonl` is emitted.
3. Candidate counts: questions=34, points=150, auto_certifiable_points=25, statuses={'draft_review': 5, 'po_review_required': 28, 'candidate_dry_run': 1}.
4. Weak/rewrite blocked from auto-certification: YES. blocked_points=125, decisions={'review_required_official_weak': 112, 'rewrite_needed': 13}; every blocked point has `runtime_auto_certification_allowed=false`.
5. Runtime gate proof: dry-run only. `ArtifactRuntimeGate` was loaded in memory, production_runtime_connected=false, artifact_auto_certification_allowed_count=0, point_auto_certified_after_gate_count=0.
6. v0 not overwritten: YES. v0_read_only_reference=true and v0_overwritten=False.
7. v0 vs v1 candidate diff: v0 has 20 questions / 97 points / 69 auto points; M6 candidate has 34 questions / 150 points / 25 auto points; overlap=0.
8. PO review carryover: question-level po_review_required=28; point-level non-auto carryover=125, decisions={'review_required_official_weak': 112, 'rewrite_needed': 13}.
9. LLM jury / provider status: real LLM jury coverage is 0/150; provider-unavailable advice remains non-authoritative and cannot promote weak sources.
10. M7 verdict: WEAK-GO for candidate-only jury/PO/QA dry-run; NO-GO for formal Registry v1 publish/runtime connection.
11. Next task: run M7 on this sealed candidate package, repair `review_required_official_weak` and `rewrite_needed` points with PO/external evidence, then re-run M6 before any formal publish decision.

## M5R jury overlay (real 3-model heterogeneous jury)

- M5R reviewed: 16 questions; jury_cleared (decision==publish_candidate): ['M2-2015-32-00']; needs_po_review: 15.
- Overlay rule: a question stays `candidate_dry_run` ONLY if M5 publish-ready AND M5R jury-cleared. `candidate_dry_run_after_overlay`=['M2-2015-32-00']; M5 publish-ready questions the jury did not clear are DOWNGRADED to `po_review_required`: ['M2-2016-31-02'].
- **The jury never upgraded a weak source to verified**: source_status_upgraded_by_jury=False. The overlay only narrows the candidate set; auto_certifiable counts come solely from M5 deterministic authority.

## Boundary recap

- package_status: `candidate_dry_run`
- point_decision_counts: {'auto_certifiable': 25, 'review_required_official_weak': 112, 'rewrite_needed': 13}
- no DB, no CaseGradingSkillKernel, no RAG-as-authority, no BI/billing/web path
