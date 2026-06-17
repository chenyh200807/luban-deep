# 鲁班 v1 人锚定校验切片 + Artifact Versioning 启动计划

Status: Human gate ready / awaiting PO labels. Not a production gate.

## 0. Decision Boundary

This plan starts v1, but it does not promote runtime, build a Nexus-like platform, or let RAG enter scoring authority.

The current stopping point is intentional: the PO / human reviewer must now label the validation slice. No AI agent may fill this role.

## 1. Why v1 Exists

v0 evidence is directional because its gold source is AI-anchored `ground_truth_ledger`. It measures grader-vs-construction-intent consistency, not human-grounded correctness.

v1 adds a human/PO label layer to test whether the v0 ledger is itself credible:

- v0 gold remains `ground_truth_ledger` for comparability.
- human labels are added as a higher-authority validation layer.
- the metrics compare human-vs-ledger and human-vs-artifact-first separately.

## 2. PO Slice Package

Location:

- `artifacts/luban_human_validation_v1/po_slice_20260601/`

Files:

- `po_review_packet.json`: public blind packet for PO review.
- `po_labels_template.csv`: low-friction label sheet.
- `po_labels_template.json`: equivalent JSON template.
- `internal_slice_manifest.json`: internal manifest with ledger/artifact references and artifact hashes; do not show this while labeling.
- `human_validation_protocol.md`: reviewer protocol and metric command.

Slice summary:

- 24 samples.
- 12 cases.
- 131 point-label rows.
- Deterministic sample selection.
- Includes all current positive-score frontier samples first, penalty-rule cases, then largest under-score samples.

Blindness rule:

- PO sees only question, official answer, scoring points, and student answer.
- PO must not see baseline/RAG/artifact-first predictions.
- PO must not see `ground_truth_ledger` or `blind_grade`.

## 3. Deterministic Sampling Policy

Priority order:

1. All artifact-first positive score delta samples, covering false positives and overmatch frontier.
2. Penalty-rule cases, so global coupling rules are human-checked.
3. Largest remaining under-score deltas, covering recall gaps.

This keeps the slice small enough for PO review while concentrating on the highest-value uncertainty boundary.

## 4. Metrics

After PO fills `po_labels_template.csv`, run:

```bash
python scripts/score_luban_human_validation_slice.py \
  --manifest artifacts/luban_human_validation_v1/po_slice_20260601/internal_slice_manifest.json \
  --labels artifacts/luban_human_validation_v1/po_slice_20260601/po_labels_filled.csv \
  --output artifacts/luban_human_validation_v1/po_slice_20260601/human_validation_metrics.json
```

The script computes:

- `human_vs_ledger`: tests whether v0 AI-ledger is credible.
- `human_vs_artifact_first`: tests grader accuracy against human labels.
- disagreement rows: root-cause backlog for v1.

## 5. Artifact Versioning Seed

The internal manifest now snapshots derived artifact assets with:

- `schema_version`: currently `grading_artifact.v1`.
- `version_id`: `{case_id}:{content_hash_prefix}`.
- `content_hash`: sha256 over `scoring_points + penalty_rules`.
- `source_authority`: `golden.gold_scoring_points + golden.penalty_rule`.
- compiled scoring-point count.
- penalty-rule count.

This is a seed, not the full production versioning system. It is enough to prevent the PO slice from becoming an untraceable one-off packet. Full artifact versioning should start after PO labels return.

## 6. Next Gates

Stop here until PO labels are collected.

After labels return:

1. Run human validation metrics.
2. Decide whether v0 ledger is credible enough for broader expansion.
3. If credible, proceed to full artifact versioning and source compiler expansion.
4. If not credible, repair golden production before expanding coverage.

## 7. Explicit Non-Actions

- No kernel authority change.
- No runner-side score correction.
- No RAG scoring authority.
- No production runtime promotion.
- No generic Nexus-like platform.
